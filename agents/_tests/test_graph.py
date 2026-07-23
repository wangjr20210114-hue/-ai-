import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.chat._graph import build_graph


class _BoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="bound answer")


class _RecordingModel:
    def __init__(self):
        self.bound_calls = 0
        self.unbound_calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _BoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        self.unbound_calls += 1
        return AIMessage(content="final answer")


@tool
def rich_search(query: str) -> str:
    """Return search evidence."""
    return query


class GraphFinalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_answer_does_not_call_rich_search(self):
        model = _RecordingModel()
        graph = build_graph(model, [rich_search], "system")
        result = await graph.ainvoke({"messages": [HumanMessage(content="一加一等于几")]})
        self.assertEqual(result["messages"][-1].content, "bound answer")
        self.assertFalse(any(isinstance(message, ToolMessage) for message in result["messages"]))
        self.assertEqual(model.bound_calls, 1)
        self.assertEqual(model.unbound_calls, 0)

    async def test_llm_planned_rich_search_skips_redundant_tool_call_model_round(self):
        model = _RecordingModel()
        graph = build_graph(model, [rich_search], "system", required_tools=["rich_search"])
        result = await graph.ainvoke({"messages": [HumanMessage(content="最近有什么进展")]})
        self.assertEqual(result["messages"][-1].content, "final answer")
        self.assertTrue(any(
            isinstance(message, ToolMessage) and message.name == "rich_search"
            for message in result["messages"]
        ))
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(model.bound_calls, 0)

    async def test_completed_rich_search_finalizes_without_second_tool_bound_call(self):
        model = _RecordingModel()
        graph = build_graph(model, [rich_search], "system")
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="最近有什么进展"),
            AIMessage(content="", tool_calls=[{
                "name": "rich_search", "args": {"query": "AI 进展"}, "id": "search-1",
            }]),
            ToolMessage(content="evidence", name="rich_search", tool_call_id="search-1"),
        ]})
        self.assertEqual(result["messages"][-1].content, "final answer")
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(model.bound_calls, 0)


if __name__ == "__main__":
    unittest.main()
