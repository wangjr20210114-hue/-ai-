"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Iterable, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ._history import bounded_history
from ._protocol import dsml_tool_calls, public_content
from ._capability_plan import next_required_tool


TOOL_FAILURE_MESSAGE = (
    "工具暂时没有完成。请基于已经获得的信息向用户说明限制，"
    "不要假装操作成功，也不要重复调用同一工具。"
)


def _tool_failure_message(exc: Exception) -> str:
    """Keep safe validation feedback so the model can answer naturally."""
    if isinstance(exc, ValueError):
        detail = str(exc).strip()[:500] or "输入不符合要求"
        return f"操作未完成：{detail}。请自然说明原因和下一步，不要声称已经成功。"
    return TOOL_FAILURE_MESSAGE


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
    required_tool: str = "",
    required_tools: Iterable[str] | None = None,
):
    model_with_tools = model.bind_tools(tools) if tools else model
    allowed_tool_names = {getattr(tool, "name", "") for tool in tools}
    required_sequence = tuple(required_tools or (() if not required_tool else (required_tool,)))

    async def agent_node(state: MessagesState):
        tools_this_turn = 0
        used_tool_names = []
        for message in reversed(state["messages"]):
            if getattr(message, "type", "") in {"human", "user"}:
                break
            if getattr(message, "type", "") == "tool":
                tools_this_turn += 1
                used_tool_names.append(getattr(message, "name", ""))
        # A model can occasionally keep reformulating the same search. Preserve
        # multi-tool reasoning, but after a generous turn-local budget force a
        # normal answer from the evidence already collected instead of exposing
        # LangGraph's recursion error to the user.
        force_finalize = tools_this_turn >= 4
        if force_finalize:
            active_model = model
        else:
            required_name = next_required_tool(
                required_sequence, used_tool_names, allowed_tool_names,
            )
            active_model = (
                model.bind_tools(tools, tool_choice=required_name)
                if required_name else model_with_tools
            )
        history = bounded_history(state["messages"])
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
        response_tool_calls = list(getattr(response, "tool_calls", None) or [])
        if not force_finalize and response_tool_calls:
            rich_search_used = False
            for message in reversed(state["messages"]):
                if getattr(message, "type", "") in {"human", "user"}:
                    break
                if getattr(message, "type", "") == "tool" and getattr(message, "name", "") == "rich_search":
                    rich_search_used = True
                    break
            filtered_tool_calls = []
            suppressed_rich_search = False
            for tool_call in response_tool_calls:
                name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
                if name == "rich_search":
                    if rich_search_used:
                        suppressed_rich_search = True
                        continue
                    rich_search_used = True
                filtered_tool_calls.append(tool_call)
            if suppressed_rich_search:
                if filtered_tool_calls:
                    response = response.model_copy(update={"tool_calls": filtered_tool_calls})
                else:
                    response = await model.ainvoke([
                        SystemMessage(content=system_prompt),
                        *history,
                        SystemMessage(content=(
                            "本轮唯一一次富搜索已经完成。请直接基于已有结果回答，"
                            "不要再次调用 rich_search，也不要描述内部搜索过程。"
                        )),
                    ])
        if force_finalize and not public_content(getattr(response, "content", "")).strip():
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
                response = AIMessage(content="没有获得足够且符合条件的可靠信息；我没有用不相关内容凑数。你可以缩小范围或补充约束后再试。")
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    if tools:
        graph.add_node(
            "tools",
            ToolNode(
                tools,
                handle_tool_errors=_tool_failure_message,
            ),
        )
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer, store=store)
