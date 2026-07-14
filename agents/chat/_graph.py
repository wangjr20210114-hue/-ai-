"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ._rich_search import search_meta_from_tool_content, should_search


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
):
    model_with_tools = model.bind_tools(tools) if tools else model

    async def prefetch_node(state: MessagesState):
        last_message = state["messages"][-1]
        query = str(getattr(last_message, "content", ""))
        call_id = f"prefetch-{uuid4().hex}"
        content = await tools[0].ainvoke({"query": query})
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "web_search",
                        "args": {"query": query},
                        "id": call_id,
                        "type": "tool_call",
                    }],
                ),
                ToolMessage(
                    content=str(content),
                    name="web_search",
                    tool_call_id=call_id,
                ),
            ]
        }

    async def agent_node(state: MessagesState):
        last_message = state["messages"][-1]
        # A deterministic prefetch guarantees search for substantive prompts.
        # After any tool result, answer with the plain model so thinking-mode
        # providers are never sent an unsupported forced tool_choice.
        selected_model = model if getattr(last_message, "type", "") == "tool" else model_with_tools
        response = await selected_model.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )
        # Attach metadata only to the answer produced immediately after a tool
        # result. Otherwise a later casual turn could inherit stale sources.
        if getattr(last_message, "type", "") == "tool":
            search_meta = search_meta_from_tool_content(getattr(last_message, "content", ""))
            if search_meta:
                response.additional_kwargs = {
                    **getattr(response, "additional_kwargs", {}),
                    "search_results": search_meta,
                }
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    def entry_route(state: MessagesState) -> Literal["prefetch", "agent"]:
        last = state["messages"][-1]
        if tools and getattr(last, "type", "") in {"human", "user"}:
            if should_search(str(getattr(last, "content", ""))):
                return "prefetch"
        return "agent"

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    if tools:
        graph.add_node("prefetch", prefetch_node)
        graph.add_conditional_edges(START, entry_route)
        graph.add_edge("prefetch", "agent")
    else:
        graph.add_edge(START, "agent")
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer, store=store)
