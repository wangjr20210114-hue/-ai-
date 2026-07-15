"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ._history import bounded_history


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
    required_tool: str = "",
):
    model_with_tools = model.bind_tools(tools) if tools else model
    required_model = (
        model.bind_tools(tools, tool_choice=required_tool)
        if tools and required_tool else None
    )

    async def agent_node(state: MessagesState):
        last = state["messages"][-1] if state["messages"] else None
        first_step = getattr(last, "type", "") in {"human", "user"}
        active_model = required_model if first_step and required_model is not None else model_with_tools
        response = await active_model.ainvoke(
            [SystemMessage(content=system_prompt), *bounded_history(state["messages"])]
        )
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
