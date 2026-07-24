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


class _RouteChainBoundModel:
    def __init__(self, owner, tool_choice=""):
        self.owner = owner
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        if self.tool_choice == "plan_route_between_places":
            self.owner.route_calls += 1
            return AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "北京站", "destination_query": "北京301医院"},
                "id": "route-1",
            }])
        self.owner.final_calls += 1
        return AIMessage(content="真实道路距离为 13.8 公里。")


class _RouteChainModel:
    def __init__(self):
        self.route_calls = 0
        self.final_calls = 0

    def bind_tools(self, _tools, **kwargs):
        return _RouteChainBoundModel(self, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        self.final_calls += 1
        return AIMessage(content="真实道路距离为 13.8 公里。")


@tool
def rich_search(query: str) -> str:
    """Return search evidence."""
    return query


@tool
def ask_user_clarification(title: str) -> str:
    """Return one structured clarification."""
    return title


@tool
def plan_route_between_places(origin_query: str, destination_query: str) -> str:
    """Return one verified route."""
    return f"{origin_query}->{destination_query}:13.8km"

@tool
def propose_calendar_changes(summary: str) -> str:
    """Return one calendar proposal."""
    return summary


class _ClarificationChoiceBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.tool_names = {tool.name for tool in self.tools}
        self.owner.tool_choice = self.tool_choice
        return AIMessage(content="", tool_calls=[{
            "name": "ask_user_clarification",
            "args": {"title": "只补充真正缺少的信息"},
            "id": "clarify-global-1",
        }])


class _ClarificationChoiceModel:
    def __init__(self):
        self.tool_names = set()
        self.tool_choice = ""

    def bind_tools(self, tools, **kwargs):
        return _ClarificationChoiceBoundModel(self, tools, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="unexpected")


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

    async def test_clarification_card_ends_turn_without_prose_epilogue(self):
        model = _RecordingModel()
        graph = build_graph(model, [ask_user_clarification], "system")
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="帮我安排一个计划"),
            AIMessage(content="", tool_calls=[{
                "name": "ask_user_clarification",
                "args": {"title": "需要补充时间"},
                "id": "clarify-1",
            }]),
            ToolMessage(content='{"ui_action":"clarification_action"}', name="ask_user_clarification", tool_call_id="clarify-1"),
        ]})
        self.assertEqual(result["messages"][-1].content, "")
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(model.unbound_calls, 0)

    async def test_every_required_qa_tool_can_yield_to_structured_clarification(self):
        model = _ClarificationChoiceModel()
        graph = build_graph(
            model,
            [propose_calendar_changes, ask_user_clarification],
            "system",
            required_tools=["propose_calendar_changes"],
        )
        result = await graph.ainvoke({"messages": [HumanMessage(content="帮我写入日程")]})
        self.assertEqual(
            model.tool_names,
            {"propose_calendar_changes", "ask_user_clarification"},
        )
        self.assertEqual(model.tool_choice, "required")
        self.assertEqual(result["messages"][-1].content, "")

    async def test_rich_search_keeps_required_route_tool_available(self):
        model = _RouteChainModel()
        graph = build_graph(
            model,
            [rich_search, plan_route_between_places],
            "system",
            required_tools=["rich_search", "plan_route_between_places"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="北京站到北京301医院多远")],
        })
        tool_names = [
            message.name for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(tool_names, ["rich_search", "plan_route_between_places"])
        self.assertEqual(result["messages"][-1].content, "真实道路距离为 13.8 公里。")
        self.assertEqual(model.route_calls, 1)
        self.assertEqual(model.final_calls, 1)


if __name__ == "__main__":
    unittest.main()
