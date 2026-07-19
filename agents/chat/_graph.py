"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ._history import bounded_history, recoverable_history
from ._protocol import dsml_tool_calls, public_content


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
    required_tool: str = "",
):
    model_with_tools = model.bind_tools(tools) if tools else model
    allowed_tool_names = {getattr(tool, "name", "") for tool in tools}
    required_model = (
        model.bind_tools(tools, tool_choice=required_tool)
        if tools and required_tool else None
    )

    async def agent_node(state: MessagesState):
        last = state["messages"][-1] if state["messages"] else None
        first_step = getattr(last, "type", "") in {"human", "user"}
        tools_this_turn = 0
        for message in reversed(state["messages"]):
            if getattr(message, "type", "") in {"human", "user"}:
                break
            if getattr(message, "type", "") == "tool":
                tools_this_turn += 1
        # A model can occasionally keep reformulating the same search. Preserve
        # multi-tool reasoning, but after a generous turn-local budget force a
        # normal answer from the evidence already collected instead of exposing
        # LangGraph's recursion error to the user.
        force_finalize = tools_this_turn >= 4
        if force_finalize:
            active_model = model
        else:
            active_model = required_model if first_step and required_model is not None else model_with_tools
        history = recoverable_history(bounded_history(state["messages"]))
        messages = [SystemMessage(content=system_prompt), *history]
        if force_finalize:
            messages.append(SystemMessage(content=(
                "本轮工具阶段已经结束。不要再描述搜索过程，不要再输出或模拟任何工具调用。"
                "请直接基于已有工具结果回答用户；结果不足时明确说明缺少多少和检索边界。"
            )))
        response = await active_model.ainvoke(messages)
        if not force_finalize and not getattr(response, "tool_calls", None):
            normalized = dsml_tool_calls(getattr(response, "content", ""), allowed_tool_names)
            if normalized:
                response = AIMessage(content="", tool_calls=normalized)
        elif force_finalize and not public_content(getattr(response, "content", "")).strip():
            # Some provider models keep imitating their previous DSML transport
            # after tools are unbound. One clean retry yields prose without
            # exposing a placeholder or inventing results.
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                *history,
                SystemMessage(content=(
                    "现在只输出给用户看的最终回答，禁止 XML、DSML、tool_calls、invoke 或参数。"
                    "若没有满足条件的结果，直接如实说明。"
                )),
            ])
            if not public_content(getattr(response, "content", "")).strip():
                response = AIMessage(content="没有找到足够且满足条件的可靠结果；我没有用不相关内容凑数。你可以放宽年份或指定论文数据库后再查。")
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer, store=store)
