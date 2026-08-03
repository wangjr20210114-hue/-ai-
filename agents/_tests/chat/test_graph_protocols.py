from agents._tests.support.graph_environment import *  # noqa: F401,F403


class GraphProtocolTests(unittest.IsolatedAsyncioTestCase):
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
            {"propose_calendar_changes"},
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
                {"propose_calendar_changes"},
                "",
            ),
        )
        self.assertEqual(
            result["messages"][-1].content,
            "路线和日程提案已准备好。",
        )

    async def test_completed_route_survives_unavailable_calendar_stage(self):
        model = _LinkedRouteCalendarModel()
        graph = build_graph(
            model,
            [linked_verified_route_action],
            "system",
            required_tools=[
                "plan_route_between_places",
                "propose_calendar_changes",
            ],
        )
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="明天下午去这几个地方逛逛")],
        })
        tool_names = [
            message.name for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(tool_names, ["plan_route_between_places"])
        answer = result["messages"][-1].content
        self.assertIn("北京站 → 北京西站", answer)
        self.assertIn("路线规划已经完成", answer)
        self.assertIn("本轮没有生成日程提案", answer)
        self.assertNotIn("Skills 广场", answer)
        self.assertNotIn("没有执行", answer)

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
