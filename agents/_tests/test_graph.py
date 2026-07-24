import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.chat._graph import build_graph, tool_result_fallback


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


@tool
def search_places(query: str) -> str:
    """Return verified places."""
    return '{"places":[{"place_id":"breakfast-1","name":"早餐店","address":"酒店东侧"}],"count":1}'


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


class _ContinuationBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        if self.owner.calls == 1:
            self.owner.first_tool_names = {tool.name for tool in self.tools}
            return AIMessage(content="", tool_calls=[{
                "name": "propose_calendar_changes",
                "args": {"summary": "07:04 出发"},
                "id": "calendar-1",
            }])
        return AIMessage(content="日程确认卡已经准备好。")


class _ContinuationModel:
    def __init__(self):
        self.calls = 0
        self.first_tool_names = set()

    def bind_tools(self, tools, **kwargs):
        return _ContinuationBoundModel(self, tools, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="日程确认卡已经准备好。")


class _BlankAfterToolBoundModel:
    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="")


class _BlankAfterToolModel:
    def __init__(self):
        self.recovery_calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _BlankAfterToolBoundModel()

    async def ainvoke(self, _messages, **_kwargs):
        self.recovery_calls += 1
        return AIMessage(content="已根据核实路线整理好结果。")


class _RepeatingPlaceBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="", tool_calls=[{
            "name": "search_places",
            "args": {"query": "桔子酒店附近早餐店"},
            "id": f"place-{self.owner.bound_calls}",
        }])


class _RepeatingPlaceModel:
    def __init__(self, final_content="附近有已核实的早餐店。"):
        self.bound_calls = 0
        self.unbound_calls = 0
        self.final_content = final_content

    def bind_tools(self, _tools, **_kwargs):
        return _RepeatingPlaceBoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        self.unbound_calls += 1
        return AIMessage(content=self.final_content)


class _BurstPlaceBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="", tool_calls=[
            {
                "name": "search_places",
                "args": {"query": query},
                "id": f"place-burst-{index}",
            }
            for index, query in enumerate(
                ["桔子酒店附近早餐店", "中关村软件园早餐店", "西北旺早餐店"],
                start=1,
            )
        ])


class _BurstPlaceModel(_RepeatingPlaceModel):
    def bind_tools(self, _tools, **_kwargs):
        return _BurstPlaceBoundModel(self)


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

    async def test_clarification_answer_continues_original_tool_chain_without_repeating_route(self):
        model = _ContinuationModel()
        graph = build_graph(
            model,
            [plan_route_between_places, propose_calendar_changes, ask_user_clarification],
            "system",
            required_tools=["plan_route_between_places", "propose_calendar_changes"],
        )
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="从酒店到北京站再去锦江，写入明天行程"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "桔子酒店", "destination_query": "北京站"},
                "id": "route-before-card",
            }]),
            ToolMessage(
                content="桔子酒店->北京站:31km",
                name="plan_route_between_places",
                tool_call_id="route-before-card",
            ),
            AIMessage(content="", tool_calls=[{
                "name": "ask_user_clarification",
                "args": {"title": "确认出发时间"},
                "id": "clarify-time",
            }]),
            ToolMessage(
                content='{"ui_action":"clarification_action"}',
                name="ask_user_clarification",
                tool_call_id="clarify-time",
            ),
            AIMessage(content=""),
            HumanMessage(
                content="明天出发时间：07:04",
                additional_kwargs={
                    "floris_ui_hidden": True,
                    "floris_interaction": "clarification",
                    "clarification_id": "time-card",
                },
            ),
        ]})
        tool_names = [
            message.name for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(tool_names.count("plan_route_between_places"), 1)
        self.assertEqual(tool_names.count("propose_calendar_changes"), 1)
        self.assertEqual(
            model.first_tool_names,
            {"propose_calendar_changes", "ask_user_clarification"},
        )
        self.assertEqual(result["messages"][-1].content, "日程确认卡已经准备好。")

    async def test_empty_model_turn_after_tool_gets_one_tool_free_synthesis_retry(self):
        model = _BlankAfterToolModel()
        graph = build_graph(model, [plan_route_between_places], "system")
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="北京站到北京301医院多远"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "北京站", "destination_query": "北京301医院"},
                "id": "route-blank",
            }]),
            ToolMessage(
                content="北京站->北京301医院:13.8km",
                name="plan_route_between_places",
                tool_call_id="route-blank",
            ),
        ]})
        self.assertEqual(result["messages"][-1].content, "已根据核实路线整理好结果。")
        self.assertEqual(model.recovery_calls, 1)

    async def test_planned_place_lookup_closes_tools_before_answer_synthesis(self):
        model = _RepeatingPlaceModel()
        graph = build_graph(
            model,
            [search_places],
            "system",
            required_tools=["search_places"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="桔子酒店附近有早餐店吗？")],
        })
        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(model.bound_calls, 1)
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(result["messages"][-1].content, "附近有已核实的早餐店。")

    async def test_unplanned_duplicate_place_lookup_is_suppressed(self):
        model = _RepeatingPlaceModel()
        graph = build_graph(model, [search_places], "system")
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="桔子酒店附近有早餐店吗？")],
        })
        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(model.bound_calls, 2)
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(result["messages"][-1].content, "附近有已核实的早餐店。")

    async def test_parallel_single_place_lookups_are_reduced_to_one_provider_call(self):
        model = _BurstPlaceModel()
        graph = build_graph(model, [search_places], "system")
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="桔子酒店附近有早餐店吗？")],
        })
        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(model.bound_calls, 2)
        self.assertEqual(model.unbound_calls, 1)

    async def test_empty_place_synthesis_uses_verified_result_instead_of_terminal_error(self):
        model = _RepeatingPlaceModel(final_content="")
        graph = build_graph(
            model,
            [search_places],
            "system",
            required_tools=["search_places"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="桔子酒店附近有早餐店吗？")],
        })
        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("早餐店", result["messages"][-1].content)
        self.assertIn("酒店东侧", result["messages"][-1].content)

    def test_place_result_has_truthful_terminal_fallback(self):
        content = tool_result_fallback([
            ToolMessage(
                content='{"places":[{"place_id":"p1","name":"麦香早餐","address":"酒店东侧100米"}],"count":1}',
                name="search_places",
                tool_call_id="places-fallback",
            ),
        ])
        self.assertIn("麦香早餐", content)
        self.assertIn("酒店东侧100米", content)

    def test_failed_nearby_lookup_has_truthful_terminal_fallback(self):
        content = tool_result_fallback([
            ToolMessage(
                content="操作未完成：没有在酒店附近核实到早餐店。请自然说明原因和下一步，不要声称已经成功。",
                name="recommend_nearby_places_on_map",
                tool_call_id="nearby-fallback",
            ),
        ])
        self.assertIn("没有核实到", content)
        self.assertIn("扩大查找范围", content)


if __name__ == "__main__":
    unittest.main()
