from agents._tests.support.graph_environment import *  # noqa: F401,F403


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

    def test_output_boundary_prefers_verified_actions_over_model_prose(self):
        actions = [
            json.loads(linked_verified_route_action.invoke({
                "origin_query": "北京站",
                "destination_query": "故宫博物院",
            })),
            json.loads(mismatched_linked_calendar_action.invoke({
                "summary": "明日上午行程",
            })),
        ]
        answer = grounded_route_action_answer(actions)

        self.assertIn("腾讯公交路线约 5 公里，预计 50 分钟", answer)
        self.assertIn("包含 2 项变更", answer)
        self.assertNotIn("45 分钟", answer)
        self.assertEqual(
            grounded_route_stream_answer(
                actions[:1],
                calendar_required=True,
                clarification_emitted=False,
                run_error="",
            ),
            "",
        )
        self.assertEqual(
            grounded_route_stream_answer(
                actions,
                calendar_required=True,
                clarification_emitted=True,
                run_error="",
            ),
            "",
        )
        self.assertIn(
            "预计 50 分钟",
            grounded_route_stream_answer(
                actions,
                calendar_required=True,
                clarification_emitted=False,
                run_error="",
            ),
        )

    def test_calendar_continuation_keeps_the_card_as_the_only_timetable(self):
        answer = grounded_route_stream_answer(
            [{
                "ui_action": "calendar_action",
                "action": {
                    "kind": "calendar_changes",
                    "payload": {
                        "source_route_plan_id": "routeplan-1",
                        "changes": [
                            {"operation": "create", "event": {
                                "title": "第一站", "start_time": 1_900_000_000,
                            }},
                            {"operation": "create", "event": {
                                "title": "第二站", "start_time": 1_900_012_300,
                            }},
                        ],
                    },
                },
            }],
            calendar_required=True,
            clarification_emitted=False,
            run_error="",
        )
        self.assertIn("包含 2 项变更", answer)
        self.assertIn("尚未写入日程", answer)
        self.assertNotIn("第一站", answer)
        self.assertNotIn("第二站", answer)
        self.assertNotIn("1900000000", answer)

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

    async def test_voluntary_verified_route_is_synthesized_by_answer_model(self):
        class VoluntaryRouteModel:
            def __init__(self):
                self.calls = 0

            def bind_tools(self, _tools, **_kwargs):
                return self

            async def ainvoke(self, _messages, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return AIMessage(content="", tool_calls=[{
                        "name": "plan_route_between_places",
                        "args": {
                            "origin_query": "北京站",
                            "destination_query": "故宫博物院",
                        },
                        "id": "voluntary-route-1",
                    }])
                return AIMessage(content="模型猜测约 45 分钟")

        model = VoluntaryRouteModel()
        graph = build_graph(
            model,
            [verified_route_action],
            "system",
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="帮我规划路线")],
        })

        final = result["messages"][-1].content
        self.assertEqual(final, "模型猜测约 45 分钟")
        self.assertEqual(model.calls, 2)

    async def test_linked_route_and_calendar_keep_action_as_time_source(self):
        model = _LinkedRouteCalendarModel()
        graph = build_graph(
            model,
            [
                linked_verified_route_action,
                mismatched_linked_calendar_action,
                ask_user_clarification,
            ],
            "system",
            required_tools=[
                "plan_route_between_places",
                "propose_calendar_changes",
            ],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="规划路线并生成日程提案")],
        })

        final = result["messages"][-1].content
        self.assertIn("包含 2 项变更", final)
        self.assertIn("尚未写入日程", final)
        self.assertNotEqual(final, "路线和日程提案已准备好。")

    async def test_calendar_only_graph_does_not_recalculate_card_times(self):
        model = _LinkedRouteCalendarModel()
        graph = build_graph(
            model,
            [mismatched_linked_calendar_action],
            "system",
            required_tools=["propose_calendar_changes"],
            planned_tool_arguments={
                "propose_calendar_changes": {"summary": "冻结日程"},
            },
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="把已核实路线写入日程")],
        })

        final = result["messages"][-1].content
        self.assertIn("包含 2 项变更", final)
        self.assertNotIn("10:25", final)
        self.assertNotIn("205", final)

    async def test_paper_only_result_uses_public_model_synthesis(self):
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
        self.assertEqual(final.content, "final answer")
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(public_model.unbound_calls, 1)

    async def test_empty_paper_result_uses_public_model_synthesis(self):
        model = _RecordingModel()
        public_model = _RecordingModel()
        graph = build_graph(
            model,
            [empty_search_arxiv],
            "tool system",
            required_tools=["search_arxiv"],
            public_answer_model=public_model,
            planned_tool_arguments={
                "search_arxiv": {
                    "topic": "recent papers by Xin Peng",
                    "limit": 2,
                },
            },
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(
                content="给我找两篇复旦大学彭鑫老师近2年的论文"
            )],
        })
        final = result["messages"][-1].content
        self.assertEqual(final, "final answer")
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(public_model.unbound_calls, 1)

    async def test_paper_search_is_synthesized_when_reader_skill_is_off(self):
        model = _RecordingModel()
        graph = build_graph(
            model,
            [search_arxiv],
            "tool system",
            required_tools=["search_arxiv"],
            planned_tool_arguments={
                "search_arxiv": {
                    "topic": "verified paper",
                    "limit": 1,
                    "author": "",
                    "year": 2026,
                },
            },
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="找一篇论文")],
        })
        final = result["messages"][-1].content
        self.assertEqual(final, "final answer")

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
        self.assertEqual(public_model.unbound_calls, 1)

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
    async def test_failed_search_only_turn_degrades_to_public_model_answer(self):
        model = _RecordingModel()
        graph = build_graph(
            model,
            [failing_rich_search],
            "system",
            required_tools=["rich_search"],
        )

        result = await graph.ainvoke({
            "messages": [HumanMessage(content="recent AI progress")],
        })

        self.assertEqual(result["messages"][-1].content, "final answer")
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(model.bound_calls, 0)
        self.assertTrue(any(
            isinstance(message, ToolMessage)
            and message.name == "rich_search"
            and "tool_error" in message.content
            for message in result["messages"]
        ))

    async def test_failed_search_only_closes_optional_tools_before_synthesis(self):
        """A rich-search outage must not let the answer model restart tools."""
        model = _RecordingModel()
        graph = build_graph(
            model,
            [failing_rich_search, search_places],
            "system",
            required_tools=["rich_search"],
        )

        result = await graph.ainvoke({
            "messages": [HumanMessage(content="recent AI progress")],
        })

        self.assertEqual(result["messages"][-1].content, "final answer")
        self.assertEqual(model.unbound_calls, 1)
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(
            len([
                message for message in result["messages"]
                if isinstance(message, ToolMessage) and message.name == "rich_search"
            ]),
            1,
        )

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

        self.assertEqual(result["messages"][-1].content, "路线规划未完成，请检查地点后重试。")
        self.assertFalse(any(
            isinstance(message, ToolMessage)
            and message.name == "propose_calendar_changes"
            for message in result["messages"]
        ))
        self.assertEqual(model.bound_calls, 0)
        self.assertEqual(model.unbound_calls, 0)
