import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.chat._graph import (
    _linked_trip_result_answer,
    _route_result_answer,
    blocked_capability_response,
    build_graph,
    tool_result_fallback,
)


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

@tool
def search_arxiv(
    topic: str = "",
    limit: int = 5,
    author: str = "",
    year: int = 0,
) -> str:
    """Return structured arXiv papers."""
    return (
        '{"ui_action":"paper_results","papers":['
        f'{{"title":"{topic}","year":{year}}}'
        f'],"limit":{limit},"author":"{author}"}}'
    )


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


class _RetryRequiredBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        if self.owner.calls == 1:
            return AIMessage(content="请告诉我更多信息")
        return AIMessage(content="", tool_calls=[{
            "name": "ask_user_clarification",
            "args": {"title": "请补充必要信息"},
            "id": "clarify-required-retry",
        }])


class _RetryRequiredModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _RetryRequiredBoundModel(self)

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


class _LinkedRouteCalendarBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        tool_names = {tool.name for tool in self.tools}
        self.owner.decisions.append((tool_names, self.tool_choice))
        if "plan_route_between_places" in tool_names:
            return AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {
                    "origin_query": "北京站",
                    "destination_query": "北京西站",
                },
                "id": "linked-route-1",
            }])
        return AIMessage(content="", tool_calls=[{
            "name": "propose_calendar_changes",
            "args": {"summary": "六站日程提案"},
            "id": "linked-calendar-1",
        }])


class _LinkedRouteCalendarModel:
    def __init__(self):
        self.decisions = []

    def bind_tools(self, tools, **kwargs):
        return _LinkedRouteCalendarBoundModel(
            self, tools, kwargs.get("tool_choice", ""),
        )

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="路线和日程提案已准备好。")


class _CalendarStageGuardBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        return AIMessage(content="", tool_calls=[
            {
                "name": "search_places",
                "args": {"query": "北京西站"},
                "id": f"out-of-stage-{self.owner.calls}",
            },
            {
                "name": "propose_calendar_changes",
                "args": {"summary": "路线日程提案"},
                "id": f"calendar-stage-{self.owner.calls}",
            },
        ])


class _CalendarStageGuardModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _CalendarStageGuardBoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="日程提案已准备好。")


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


class _UnavailableRequiredModel:
    def __init__(self):
        self.bound_calls = 0
        self.unbound_calls = 0
        self.last_messages = []

    def bind_tools(self, _tools, **_kwargs):
        self.bound_calls += 1
        return self

    async def ainvoke(self, messages, **_kwargs):
        self.unbound_calls += 1
        self.last_messages = messages
        return AIMessage(content="对应能力当前不可用，请先开启 Skill 或完成连接。")


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
    def test_linked_trip_answer_uses_action_counts_without_inventing_schedule(self):
        route_id = "routeplan-1"
        answer = _linked_trip_result_answer(
            {
                "ui_action": "map_action",
                "route_plan_id": route_id,
                "ordered_stops": [
                    {"name": "北京站"},
                    {"name": "天安门"},
                    {"name": "故宫博物院"},
                ],
                "route": {
                    "mode": "driving",
                    "distance_kilometers": 8.2,
                    "duration_minutes": 42,
                },
            },
            {
                "ui_action": "calendar_action",
                "action": {
                    "payload": {
                        "source_route_plan_id": route_id,
                        "changes": [
                            {"operation": "create"},
                            {"operation": "create"},
                            {"operation": "create"},
                        ],
                        "warnings": ["间隔不足"],
                    },
                },
            },
        )
        self.assertIn("按原顺序核实 3 个地点", answer)
        self.assertIn("约 8.2 公里", answer)
        self.assertIn("包含 3 项变更", answer)
        self.assertIn("尚未写入日程", answer)
        self.assertIn("1 条时间或通勤提醒", answer)

    def test_route_result_answer_discloses_verified_correction_and_facts(self):
        answer = _route_result_answer({
            "ui_action": "map_action",
            "ordered_stops": [
                {"name": "北京站"},
                {
                    "name": "天安门",
                    "query_correction": {
                        "original_query": "天安们",
                        "corrected_name": "天安门",
                        "evidence": "tencent_place_suggestion",
                    },
                },
            ],
            "route": {
                "mode": "walking",
                "distance_kilometers": 4.1,
                "duration_minutes": 62,
            },
        })
        self.assertIn("腾讯地点候选证据", answer)
        self.assertIn("“天安们”纠正为“天安门”", answer)
        self.assertIn("步行约 4.1 公里", answer)
        self.assertIn("预计 62 分钟", answer)
        self.assertIn("不会自动写入日程", answer)

    async def test_paper_only_result_skips_redundant_public_model_round(self):
        model = _RecordingModel()
        public_model = _RecordingModel()
        graph = build_graph(
            model,
            [search_arxiv],
            "tool system",
            required_tools=["search_arxiv"],
            public_answer_model=public_model,
            planned_tool_arguments={
                "search_arxiv": {
                    "topic": "route planning",
                    "limit": 1,
                    "author": "",
                    "year": 2024,
                },
            },
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="找一篇相关论文")],
        })
        final = result["messages"][-1]
        self.assertIn("论文卡片已经准备好", final.content)
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(public_model.unbound_calls, 0)

    async def test_planned_arxiv_arguments_skip_redundant_tool_model_round(self):
        model = _RecordingModel()
        public_model = _RecordingModel()
        graph = build_graph(
            model,
            [search_arxiv],
            "tool system",
            required_tools=["search_arxiv"],
            public_answer_model=public_model,
            planned_tool_arguments={
                "search_arxiv": {
                    "topic": "large language model route planning",
                    "limit": 3,
                    "author": "",
                    "year": 2024,
                },
            },
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="找三篇 2024 年相关论文")],
        })
        tool_calls = [
            call
            for message in result["messages"]
            for call in list(getattr(message, "tool_calls", None) or [])
        ]
        self.assertEqual(tool_calls[0]["name"], "search_arxiv")
        self.assertEqual(tool_calls[0]["args"]["year"], 2024)
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(public_model.unbound_calls, 0)

    async def test_fixed_route_schema_uses_fast_tool_model(self):
        reasoning_model = _LinkedRouteCalendarModel()
        fast_model = _LinkedRouteCalendarModel()
        public_model = _RecordingModel()
        graph = build_graph(
            reasoning_model,
            [plan_route_between_places, ask_user_clarification],
            "tool system",
            required_tools=["plan_route_between_places"],
            fast_tool_model=fast_model,
            public_answer_model=public_model,
            public_system_prompt="public system",
        )
        await graph.ainvoke({"messages": [HumanMessage(content="北京站到北京西站")]})
        self.assertEqual(len(fast_model.decisions), 1)
        self.assertEqual(len(reasoning_model.decisions), 0)
        self.assertEqual(public_model.unbound_calls, 1)

    async def test_calendar_side_effect_can_retain_reasoning_model(self):
        reasoning_model = _LinkedRouteCalendarModel()
        fast_model = _LinkedRouteCalendarModel()
        public_model = _RecordingModel()
        graph = build_graph(
            reasoning_model,
            [propose_calendar_changes, ask_user_clarification],
            "tool system",
            required_tools=["propose_calendar_changes"],
            fast_tool_model=fast_model,
            reasoning_tools={"propose_calendar_changes"},
            public_answer_model=public_model,
        )
        await graph.ainvoke({"messages": [HumanMessage(content="创建日程提案")]})
        self.assertEqual(len(reasoning_model.decisions), 1)
        self.assertEqual(len(fast_model.decisions), 0)
        self.assertEqual(reasoning_model.decisions[0][1], "")

    async def test_public_answer_can_use_a_non_thinking_sibling_model(self):
        tool_model = _RecordingModel()
        public_model = _RecordingModel()
        graph = build_graph(
            tool_model,
            [],
            "system",
            public_answer_model=public_model,
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="简短总结已完成的操作")],
        })
        self.assertEqual(result["messages"][-1].content, "final answer")
        self.assertEqual(public_model.unbound_calls, 1)
        self.assertEqual(tool_model.unbound_calls, 0)

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
        self.assertEqual(
            result["messages"][-1].additional_kwargs["floris_resume"]["version"],
            1,
        )
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(model.unbound_calls, 0)

    async def test_domain_clarification_checkpoints_original_linked_tool_protocol(self):
        model = _RecordingModel()
        route_arguments = {
            "city": "北京",
            "route_mode": "transit",
            "route_strategy": "default",
            "ordered_stops": [
                {"query": "北京站", "near_query": ""},
                {"query": "万达广场", "near_query": ""},
                {"query": "北京西站", "near_query": ""},
            ],
        }
        graph = build_graph(
            model,
            [plan_route_between_places, propose_calendar_changes],
            "system",
            required_tools=[
                "plan_route_between_places",
                "propose_calendar_changes",
            ],
            planned_tool_arguments={
                "plan_route_between_places": route_arguments,
            },
        )
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="规划路线并写入日程"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": route_arguments,
                "id": "route-needs-place",
            }]),
            ToolMessage(
                content='{"ui_action":"clarification_action"}',
                name="plan_route_between_places",
                tool_call_id="route-needs-place",
            ),
        ]})
        resume = result["messages"][-1].additional_kwargs["floris_resume"]
        self.assertEqual(
            resume["required_tools"],
            ["plan_route_between_places", "propose_calendar_changes"],
        )
        self.assertEqual(
            resume["planned_tool_arguments"]["plan_route_between_places"],
            route_arguments,
        )

    async def test_failed_required_route_cannot_advance_or_invent_prose(self):
        model = _RecordingModel()
        graph = build_graph(
            model,
            [plan_route_between_places, propose_calendar_changes],
            "system",
            required_tools=[
                "plan_route_between_places",
                "propose_calendar_changes",
            ],
        )
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="规划路线并生成日程提案"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {
                    "origin_query": "北京站",
                    "destination_query": "不存在的地点",
                },
                "id": "failed-route",
            }]),
            ToolMessage(
                content=json.dumps({
                    "tool_error": {
                        "kind": "validation",
                        "detail": "路线地点搜索超过时间预算",
                        "retry_same_call": False,
                    },
                }, ensure_ascii=False),
                name="plan_route_between_places",
                tool_call_id="failed-route",
            ),
        ]})

        self.assertIn("没有完成路线规划", result["messages"][-1].content)
        self.assertIn("超过时间预算", result["messages"][-1].content)
        self.assertFalse(any(
            isinstance(message, ToolMessage)
            and message.name == "propose_calendar_changes"
            for message in result["messages"]
        ))
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(model.unbound_calls, 0)

    async def test_retryable_validation_failure_gets_a_corrected_required_call(self):
        model = _LinkedRouteCalendarModel()
        graph = build_graph(
            model,
            [propose_calendar_changes, ask_user_clarification],
            "system",
            required_tools=["propose_calendar_changes"],
        )
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="生成路线日程提案"),
            AIMessage(content="", tool_calls=[{
                "name": "propose_calendar_changes",
                "args": {"summary": "时间范围无效"},
                "id": "calendar-invalid-time",
            }]),
            ToolMessage(
                content=json.dumps({
                    "tool_error": {
                        "kind": "validation",
                        "detail": "日程结束时间必须晚于开始时间",
                        "retry_same_call": True,
                    },
                }, ensure_ascii=False),
                name="propose_calendar_changes",
                tool_call_id="calendar-invalid-time",
            ),
        ]})

        calendar_results = [
            message for message in result["messages"]
            if isinstance(message, ToolMessage)
            and message.name == "propose_calendar_changes"
        ]
        self.assertEqual(len(calendar_results), 2)
        self.assertEqual(len(model.decisions), 1)
        self.assertEqual(result["messages"][-1].content, "路线和日程提案已准备好。")

    async def test_required_validation_corrections_stop_at_bounded_budget(self):
        model = _RecordingModel()
        messages = [HumanMessage(content="生成路线日程提案")]
        for attempt in range(1, 4):
            call_id = f"calendar-invalid-{attempt}"
            messages.extend([
                AIMessage(content="", tool_calls=[{
                    "name": "propose_calendar_changes",
                    "args": {"summary": f"无效参数 {attempt}"},
                    "id": call_id,
                }]),
                ToolMessage(
                    content=json.dumps({
                        "tool_error": {
                            "kind": "validation",
                            "detail": f"第 {attempt} 次校验失败",
                            "retry_same_call": True,
                        },
                    }, ensure_ascii=False),
                    name="propose_calendar_changes",
                    tool_call_id=call_id,
                ),
            ])
        graph = build_graph(
            model,
            [propose_calendar_changes],
            "system",
            required_tools=["propose_calendar_changes"],
        )
        result = await graph.ainvoke({"messages": messages})

        self.assertIn("第 3 次校验失败", result["messages"][-1].content)
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(model.unbound_calls, 0)

    async def test_linked_calendar_stage_suppresses_unbound_place_tool(self):
        model = _CalendarStageGuardModel()
        graph = build_graph(
            model,
            [propose_calendar_changes, ask_user_clarification],
            "system",
            required_tools=["propose_calendar_changes"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="把已核实路线生成日程提案")],
        })

        tool_names = [
            message.name for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(tool_names, ["propose_calendar_changes"])
        self.assertEqual(model.calls, 1)

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

    async def test_required_capability_retries_when_gateway_ignores_tool_choice(self):
        model = _RetryRequiredModel()
        graph = build_graph(
            model,
            [ask_user_clarification],
            "system",
            required_tools=["ask_user_clarification"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="帮我完成一个缺必要信息的任务")],
        })
        self.assertEqual(model.calls, 2)
        self.assertEqual(result["messages"][-1].content, "")

    async def test_required_capability_never_exposes_premature_plain_answer(self):
        model = _RecordingModel()
        graph = build_graph(
            model,
            [ask_user_clarification],
            "system",
            required_tools=["ask_user_clarification"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="帮我完成一个缺必要信息的任务")],
        })
        self.assertEqual(model.bound_calls, 2)
        self.assertIn("没有生成任何卡片", result["messages"][-1].content)
        self.assertNotIn("bound answer", result["messages"][-1].content)

    async def test_unavailable_required_tool_is_not_treated_as_completed(self):
        model = _UnavailableRequiredModel()
        graph = build_graph(
            model,
            [ask_user_clarification],
            "system",
            required_tools=["propose_meeting"],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="创建腾讯会议")],
        })
        self.assertIn("腾讯会议", result["messages"][-1].content)
        self.assertIn("没有生成任何卡片", result["messages"][-1].content)
        self.assertNotIn("propose_meeting", result["messages"][-1].content)
        self.assertEqual(model.unbound_calls, 0)

    async def test_planner_blocked_skill_cannot_simulate_a_result(self):
        model = _UnavailableRequiredModel()
        graph = build_graph(
            model,
            [search_places],
            "system",
            blocked_skill="maps",
            response_language="zh-CN",
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="核实北京站到天安门的距离")],
        })
        self.assertIn("地图", result["messages"][-1].content)
        self.assertIn("没有生成任何卡片", result["messages"][-1].content)
        self.assertEqual(model.unbound_calls, 0)

    def test_blocked_capability_response_is_localized_and_hides_internal_ids(self):
        english = blocked_capability_response(
            ["propose_meeting"], "en", configured=True,
        )
        self.assertIn("Tencent Meeting", english)
        self.assertIn("no card", english)
        self.assertNotIn("propose_meeting", english)

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

    async def test_linked_route_uses_auto_choice_before_required_calendar(self):
        model = _LinkedRouteCalendarModel()
        graph = build_graph(
            model,
            [
                plan_route_between_places,
                propose_calendar_changes,
                ask_user_clarification,
            ],
            "system",
            required_tools=[
                "plan_route_between_places",
                "propose_calendar_changes",
            ],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="规划六站路线并生成日程提案")],
        })
        tool_names = [
            message.name for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(
            tool_names,
            ["plan_route_between_places", "propose_calendar_changes"],
        )
        self.assertEqual(
            model.decisions[0],
            (
                {"plan_route_between_places", "ask_user_clarification"},
                "",
            ),
        )
        self.assertEqual(
            model.decisions[1],
            (
                {"propose_calendar_changes", "ask_user_clarification"},
                "",
            ),
        )
        self.assertEqual(
            result["messages"][-1].content,
            "路线和日程提案已准备好。",
        )

    async def test_domain_tool_clarification_does_not_mark_required_route_complete(self):
        model = _RouteChainModel()
        graph = build_graph(
            model,
            [plan_route_between_places],
            "system",
            required_tools=["plan_route_between_places"],
        )
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="从腾讯总部出发，先去锦江之星，再去王府井吃饭"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {
                    "origin_query": "腾讯北京总部",
                    "destination_query": "锦江之星",
                },
                "id": "route-ambiguous",
            }]),
            ToolMessage(
                content='{"ui_action":"clarification_action","clarification":{"id":"hotel"}}',
                name="plan_route_between_places",
                tool_call_id="route-ambiguous",
            ),
            AIMessage(content=""),
            HumanMessage(
                content="桔子酒店：北京中关村软件园",
                additional_kwargs={
                    "floris_ui_hidden": True,
                    "floris_interaction": "clarification",
                    "clarification_id": "hotel",
                },
            ),
        ]})
        route_results = [
            message for message in result["messages"]
            if isinstance(message, ToolMessage)
            and message.name == "plan_route_between_places"
        ]
        self.assertEqual(len(route_results), 2)
        self.assertEqual(model.route_calls, 1)
        self.assertEqual(result["messages"][-1].content, "真实道路距离为 13.8 公里。")

    async def test_multiple_domain_clarifications_continue_the_same_original_route(self):
        model = _RouteChainModel()
        graph = build_graph(
            model,
            [plan_route_between_places],
            "system",
            required_tools=["plan_route_between_places"],
        )
        hidden = {
            "floris_ui_hidden": True,
            "floris_interaction": "clarification",
        }
        result = await graph.ainvoke({"messages": [
            HumanMessage(content="腾讯总部到锦江，再去王府井，最后回桔子酒店"),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "腾讯总部", "destination_query": "锦江"},
                "id": "route-clarify-hotel",
            }]),
            ToolMessage(
                content='{"ui_action":"clarification_action","clarification":{"id":"hotel"}}',
                name="plan_route_between_places",
                tool_call_id="route-clarify-hotel",
            ),
            AIMessage(content=""),
            HumanMessage(
                content="锦江之星品尚五棵松店",
                additional_kwargs={**hidden, "clarification_id": "hotel"},
            ),
            AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "腾讯总部", "destination_query": "桔子酒店"},
                "id": "route-clarify-orange",
            }]),
            ToolMessage(
                content='{"ui_action":"clarification_action","clarification":{"id":"orange"}}',
                name="plan_route_between_places",
                tool_call_id="route-clarify-orange",
            ),
            AIMessage(content=""),
            HumanMessage(
                content="桔子酒店北京中关村软件园店",
                additional_kwargs={**hidden, "clarification_id": "orange"},
            ),
        ]})
        route_results = [
            message for message in result["messages"]
            if isinstance(message, ToolMessage)
            and message.name == "plan_route_between_places"
        ]
        self.assertEqual(len(route_results), 3)
        self.assertEqual(model.route_calls, 1)
        self.assertEqual(result["messages"][-1].content, "真实道路距离为 13.8 公里。")

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
                content=json.dumps({
                    "tool_error": {
                        "kind": "validation",
                        "detail": "没有在酒店附近核实到早餐店",
                        "retry_same_call": False,
                    },
                }, ensure_ascii=False),
                name="recommend_nearby_places_on_map",
                tool_call_id="nearby-fallback",
            ),
        ])
        self.assertIn("没有核实到", content)
        self.assertIn("扩大查找范围", content)

    def test_place_fallback_never_reuses_a_previous_turn_result(self):
        content = tool_result_fallback([
            HumanMessage(content="酒店附近有早餐店吗？"),
            AIMessage(content="", tool_calls=[{
                "name": "search_places",
                "args": {"query": "早餐店"},
                "id": "old-place-call",
            }]),
            ToolMessage(
                content='{"places":[{"place_id":"old","name":"小二包子铺","address":"茉莉园"}],"count":1}',
                name="search_places",
                tool_call_id="old-place-call",
            ),
            AIMessage(content=""),
            HumanMessage(content="26号早8点安排北京天安门日程"),
        ])
        self.assertEqual(content, "")


if __name__ == "__main__":
    unittest.main()
