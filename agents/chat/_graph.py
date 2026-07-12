"""LangGraph state graph for the chat agent."""

from typing import Literal
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI


def build_graph(
    model: ChatOpenAI,
    tools: list,
    checkpointer=None,
    store=None,
):
    """Build and compile the agent graph."""
    model_with_tools = model.bind_tools(tools)
    tool_node = ToolNode(tools)

    async def agent_node(state: MessagesState):
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile(
        checkpointer=checkpointer,
        store=store,
    )
