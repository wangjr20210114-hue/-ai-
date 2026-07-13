"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
):
    model_with_tools = model.bind_tools(tools) if tools else model

    async def agent_node(state: MessagesState):
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
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
