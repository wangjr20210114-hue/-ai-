from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class ChatPlanningTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_datetime_context_includes_authoritative_weekday(self):
        value = datetime(
            2026, 7, 25, 15, 30,
            tzinfo=timezone(timedelta(hours=8)),
        )
        context = runtime_datetime_context(value)
        self.assertIn("2026-07-25 15:30:00 UTC+08:00", context)
        self.assertIn("weekday=Saturday（周六）", context)
        self.assertIn("禁止自行重新推算", SYSTEM_PROMPT)

    def test_model_timeout_is_bounded_for_fast_failover(self):
        self.assertEqual(_model_timeout({}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 12)
        self.assertEqual(_model_timeout({"AI_GATEWAY_TIMEOUT_SECONDS": "999"}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 30)
        self.assertEqual(_model_timeout({"AI_GATEWAY_TIMEOUT_SECONDS": "1"}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 5)

    def test_long_history_is_trimmed_at_human_boundary(self):
        messages = [SimpleNamespace(type="human", content=f"q{index}") if index % 3 == 0
                    else SimpleNamespace(type="ai", content=f"a{index}") for index in range(60)]
        trimmed = bounded_history(messages, limit=20)
        self.assertLessEqual(len(trimmed), 20)
        self.assertEqual(trimmed[0].type, "human")
        self.assertEqual(trimmed[-1].content, "a59")

    def test_interrupted_tool_protocol_is_removed_before_next_model_call(self):
        messages = [
            {"role": "user", "content": "规划路线"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "route-1", "name": "plan_route_between_places", "args": {}},
            ]},
            # The browser stopped before ToolNode wrote route-1.
            {"role": "user", "content": "改成写入明天日程"},
        ]
        self.assertEqual(valid_model_history(messages), [
            {"role": "user", "content": "规划路线"},
            {"role": "user", "content": "改成写入明天日程"},
        ])

    def test_complete_tool_protocol_is_preserved_for_model_context(self):
        messages = [
            {"role": "user", "content": "规划路线"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "route-1", "name": "plan_route_between_places", "args": {}},
            ]},
            {"role": "tool", "content": "路线完成", "tool_call_id": "route-1"},
            {"role": "assistant", "content": "路线如下"},
        ]
        self.assertEqual(valid_model_history(messages), messages)

    def test_clarification_response_is_model_visible_but_marked_ui_hidden(self):
        body = {
            "interaction_mode": "clarification",
            "clarification_response": {"id": "trip-date"},
        }
        clarification_id = clarification_response_id(body)
        self.assertEqual(clarification_id, "trip-date")
        answers = clarification_response_answers({
            "interaction_mode": "clarification",
            "clarification_response": {
                "answers": [{
                    "id": "trip_date",
                    "label": "出发日期",
                    "value": "2026-08-01",
                }],
            },
        })
        self.assertEqual(graph_user_message(
            "出发日期：2026-08-01", clarification_id, answers,
        ), {
            "role": "user",
            "content": "出发日期：2026-08-01",
            "additional_kwargs": {
                "floris_ui_hidden": True,
                "floris_interaction": "clarification",
                "clarification_id": "trip-date",
                "floris_answers": [{
                    "id": "trip_date",
                    "label": "出发日期",
                    "value": "2026-08-01",
                }],
            },
        })
        self.assertEqual(clarification_response_id({
            "interaction_mode": "chat",
            "clarification_response": {"id": "trip-date"},
        }), "")
        self.assertFalse(should_persist_user_message(body))
        self.assertTrue(should_persist_user_message({"interaction_mode": "chat"}))

    def test_clarification_capability_plan_keeps_original_user_goal(self):
        self.assertEqual(
            capability_planning_message(
                "明天出发时间：07:04",
                "trip-time",
                ["从桔子酒店出发，先去北京站，再去锦江并写入日程"],
            ),
            (
                "[这是用户对上一轮结构化问题的补充答案，请结合原始目标规划尚未完成的能力；"
                "所有先前补充答案仍然有效，不要把答案误判为独立新问题或重复询问。]\n"
                "上一轮原始目标：从桔子酒店出发，先去北京站，再去锦江并写入日程\n"
                "本次补充答案：明天出发时间：07:04"
            ),
        )

    async def test_capability_planning_resolves_ordinal_from_bounded_dialogue(self):
        messages = [
            HumanMessage(content="给我推荐六个小众景点"),
            AIMessage(content=(
                "1. 圆明园遗址公园\n2. 西山国家森林公园\n"
                "3. 凤凰岭自然风景区\n4. 百望山森林公园\n"
                "5. 鹫峰国家森林公园\n6. 翠湖国家城市湿地公园"
            )),
        ]
        dialogue = await checkpoint_dialogue_context(
            FakeCheckpointer(messages),
            "ordinal-reference",
            "我想去第四个",
        )
        planning = capability_planning_message(
            "我想去第四个",
            recent_dialogue=dialogue,
        )
        self.assertIn("4. 百望山森林公园", planning)
        self.assertIn("不要把“第几个/那个/它”当作地点名称", planning)
        self.assertTrue(planning.endswith("我想去第四个"))

    def test_resume_protocol_preserves_chain_and_applies_route_field_ids(self):
        plan, arguments = resume_capability_protocol(
            {
                "needs_route": False,
                "needs_calendar_action": False,
                "route_strategy": "least_time",
            },
            {
                "version": 1,
                "required_tools": [
                    "plan_route_between_places",
                    "propose_calendar_changes",
                ],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "city": "北京",
                        "route_mode": "transit",
                        "route_strategy": "default",
                        "ordered_stops": [
                            {"query": "北京站", "near_query": ""},
                            {"query": "万达广场", "near_query": ""},
                            {"query": "咕咕塔XYZ", "near_query": ""},
                            {"query": "北京西站", "near_query": ""},
                        ],
                    },
                },
            },
            [
                {
                    "id": "route_stop_2",
                    "value": "北京通州万达广场｜北京市通州区",
                },
                {
                    "id": "route_stop_3_a1b2c3",
                    "value": "中国人民革命军事博物馆",
                },
            ],
        )
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_context"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(plan["route_strategy"], "default")
        self.assertEqual(
            [stop["query"] for stop in plan["route_stops"]],
            [
                "北京站",
                "北京通州万达广场｜北京市通州区",
                "中国人民革命军事博物馆",
                "北京西站",
            ],
        )
        self.assertEqual(
            arguments["plan_route_between_places"]["ordered_stops"],
            plan["route_stops"],
        )

    async def test_capability_planner_uses_langchain_structured_output(self):
        model = StructuredPlannerModel()
        plan = await plan_capabilities(model, "能给我讲讲故宫的历史吗")
        self.assertEqual(model.calls, 1)
        self.assertEqual(model.schema.__name__, "CapabilityPlan")
        self.assertEqual(model.method, "function_calling")
        self.assertTrue(model.include_raw)
        self.assertTrue(plan["needs_web_search"])
        self.assertTrue(plan["needs_images"])
        self.assertEqual(plan["image_query"], "故宫建筑")

    async def test_prompt_sections_are_selected_by_structured_semantics(self):
        model = StructuredPlannerModel(topic_args={"topics": ["maps", "calendar"]})
        topics = await select_prompt_topics(
            model,
            "请处理这个跨领域目标",
        )
        self.assertEqual(topics, ("maps", "calendar"))
        self.assertEqual(model.schema.__name__, "PromptTopicSelection")
        self.assertEqual(model.method, "function_calling")
        self.assertNotIn("关键词", model.messages[0]["content"])
        self.assertEqual(
            fallback_tools_for_prompt_topics(("paper",)),
            ("search_arxiv",),
        )

    async def test_missing_source_content_is_planned_as_structured_card(self):
        model = StructuredPlannerModel({
            "needs_clarification": True,
            "clarification_title": "请提供需要处理的内容",
            "clarification_prompt": "本轮没有收到原文。",
            "clarification_fields": [{
                "id": "source_content",
                "label": "需要处理的原文",
                "type": "text",
                "required": True,
                "placeholder": "请粘贴文字内容",
            }],
        })
        plan = await plan_capabilities(
            model,
            "把下面这段文字翻译成英文",
            prompt_topics=(),
        )
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(
            plan["clarification_fields"][0]["id"],
            "source_content",
        )

    async def test_single_semantic_plan_returns_all_blocking_fields_once(self):
        model = StructuredPlannerModel(args={
            "needs_clarification": True,
            "clarification_title": "请提供需要处理的内容",
            "clarification_prompt": "本轮没有收到原文。",
            "clarification_fields": [{
                "id": "source_content",
                "label": "需要处理的原文",
                "type": "text",
                "required": True,
            }],
        })
        timings = {}
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "一种没有固定短语的新表达",
            timeout_seconds=1,
            timings_ms=timings,
        )
        self.assertFalse(timed_out)
        self.assertEqual(model.calls, 1)
        self.assertIn("semantic_plan", timings)
        self.assertIn("capability_planning_total", timings)
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(plan["clarification_fields"][0]["id"], "source_content")

    async def test_single_semantic_plan_omits_invented_optional_clarification(self):
        model = StructuredPlannerModel(
            args={
                "needs_route": True,
                "needs_calendar_action": True,
                "route_stops": [{"query": "颐和园"}],
                "route_uses_current_location": True,
            },
        )
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "从本轮浏览器位置去颐和园并生成日程提案",
            location_context="浏览器位置已授权且新鲜，可作为本轮起点",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(model.calls, 1)

    async def test_required_input_gate_receives_request_location_context(self):
        model = StructuredPlannerModel()
        result = await plan_required_clarification(
            model,
            "用我本轮的位置继续完成请求",
            location_context="浏览器位置已授权且新鲜，可作为本轮起点",
        )
        self.assertFalse(result["needs_clarification"])
        self.assertIn(
            "浏览器位置已授权且新鲜",
            model.messages[0]["content"],
        )

    async def test_capability_planner_never_receives_skill_switches(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "route_stops": [
                {"query": "海淀百旺公园"},
                {"query": "百望山森林公园"},
            ],
        })
        plan = await plan_capabilities(model, "规划这两个地点的路线")
        system_prompt = model.messages[0]["content"]
        self.assertNotIn("enabled", system_prompt)
        self.assertNotIn("disabled", system_prompt)
        self.assertNotIn("blocked_skill", CapabilityPlan.model_json_schema()["properties"])
        self.assertTrue(plan["needs_route"])

    def test_runtime_skill_policy_runs_after_planning(self):
        enabled_plan = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "route_stops": [
                    {"query": "海淀百旺公园"},
                    {"query": "百望山森林公园"},
                ],
            },
            disabled_skills={"vision"},
        )
        self.assertEqual(enabled_plan["blocked_skill"], "")
        self.assertEqual(
            required_tools_for_plan(enabled_plan),
            ("plan_route_between_places",),
        )

        search_fallback = apply_runtime_skill_policy(
            {
                "needs_web_search": True,
                "search_query": "最近 AI 有什么新进展",
                "_capabilities": ["web_search"],
            },
            disabled_skills={"web-search"},
        )
        self.assertEqual(search_fallback["blocked_skill"], "")
        self.assertFalse(search_fallback["needs_web_search"])
        self.assertEqual(search_fallback["_capabilities"], [])
        self.assertEqual(
            search_fallback["_runtime_model_fallback_skills"],
            ["web-search"],
        )
        self.assertEqual(required_tools_for_plan(search_fallback), ())

        route_without_calendar = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "_capabilities": [
                    "route",
                    "calendar_context",
                    "calendar_action",
                ],
                "optional_capabilities": [
                    "calendar_context",
                    "calendar_action",
                ],
            },
            disabled_skills={"calendar"},
        )
        self.assertEqual(route_without_calendar["blocked_skill"], "")
        self.assertFalse(route_without_calendar["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(route_without_calendar),
            ("plan_route_between_places",),
        )

        disabled_plan = apply_runtime_skill_policy(
            {
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "_capabilities": ["calendar_context", "calendar_action"],
            },
            disabled_skills={"calendar"},
        )
        self.assertEqual(disabled_plan["blocked_skill"], "calendar")
        self.assertEqual(required_tools_for_plan(disabled_plan), ())

        reused_route = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "reuse_latest_route": True,
                "route_stops": [
                    {"query": "不应重新搜索的历史地点"},
                ],
                "_capabilities": [
                    "route",
                    "calendar_context",
                    "calendar_action",
                ],
            },
            disabled_skills=set(),
        )
        self.assertFalse(reused_route["needs_route"])
        self.assertEqual(reused_route["route_stops"], [])
        self.assertEqual(
            required_tools_for_plan(reused_route),
            ("propose_calendar_changes",),
        )

    async def test_capability_planner_preserves_every_ordered_route_stop(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "route_city": "北京",
            "route_stops": [
                {"query": "腾讯北京总部"},
                {"query": "锦江之星", "near_query": "北京301医院"},
                {"query": "王府井那个店"},
                {"query": "桔子酒店"},
            ],
        })
        plan = await plan_capabilities(
            model,
            "今晚从腾讯北京总部出发，先去301医院附近的锦江之星，再去王府井那个店，最后回桔子酒店",
        )
        self.assertEqual(plan["route_city"], "北京")
        self.assertEqual(
            [item["query"] for item in plan["route_stops"]],
            ["腾讯北京总部", "锦江之星", "王府井那个店", "桔子酒店"],
        )
        self.assertEqual(plan["route_stops"][1]["near_query"], "北京301医院")

    async def test_capability_plan_is_not_mutated_by_phrase_rules(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "needs_calendar_action": False,
            "route_stops": [
                {"query": "北京站"},
                {"query": "北京西站"},
            ],
        })
        plan = await plan_capabilities(
            model,
            "请规划北京站到北京西站的路线，并生成待确认的日程提案",
        )
        self.assertTrue(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places",),
        )

    async def test_failed_structured_planner_does_not_guess_from_phrases(self):
        model = FailingStructuredPlannerModel()
        plan = await plan_capabilities(
            model,
            "请规划北京六个地点的路线，并生成待确认的日程提案",
        )
        self.assertEqual(model.calls, 1)
        self.assertFalse(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(required_tools_for_plan(plan), ())
        self.assertEqual(plan["_prompt_topics"], [])

    def test_capability_plan_rejects_unknown_blocked_skill(self):
        plan = parse_capability_plan(json.dumps({
            "blocked_skill": "fake-business-rule",
            "needs_calendar_action": True,
        }))
        self.assertEqual(plan["blocked_skill"], "")
        self.assertEqual(required_tools_for_plan(plan), ("propose_calendar_changes",))

    async def test_capability_planner_timeout_keeps_main_semantic_routing_available(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "推荐北京三里屯附近的餐馆",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertFalse(any(plan[key] for key in plan if key.startswith("needs_")))

    async def test_capability_planner_timeout_never_uses_location_phrases(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "我现在在哪",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertEqual(required_tools_for_plan(plan), ())

    def test_system_prompt_sections_are_named_complete_and_ordered(self):
        self.assertEqual(
            tuple(SYSTEM_PROMPT_SECTIONS),
            SYSTEM_PROMPT_SECTION_ORDER,
        )
        self.assertEqual(
            SYSTEM_PROMPT,
            "\n".join(SYSTEM_PROMPT_SECTIONS.values()),
        )
        self.assertEqual(len(SYSTEM_PROMPT_SECTIONS), 32)
        self.assertIn(
            "plan_route_between_places",
            SYSTEM_PROMPT_SECTIONS["route"],
        )
        self.assertIn(
            "propose_calendar_changes",
            SYSTEM_PROMPT_SECTIONS["calendar"],
        )

    def test_dynamic_prompt_injects_only_the_current_skill_policy(self):
        common = {
            "now": "2026-07-26 12:00:00 UTC+08:00",
            "response_language_instruction": "使用简体中文。",
            "capability_plan": {"needs_route": True},
            "calendar_context": '[{"id":"should-not-leak"}]',
            "reference_image_context": "无",
            "document_context": "无",
            "current_location_context": "不可用",
            "current_route_context": "无",
            "memory_context": "",
        }
        route_prompt = dynamic_system_prompt(
            selected_tools={"plan_route_between_places"},
            **common,
        )
        self.assertIn("plan_route_between_places", route_prompt)
        self.assertNotIn("rich_search 始终是可用能力", route_prompt)
        self.assertNotIn("用户询问某个已知地点、当前位置或日程地点附近", route_prompt)
        self.assertNotIn("should-not-leak", route_prompt)
        self.assertLess(len(route_prompt), len(SYSTEM_PROMPT) * 0.7)

        public_route_prompt = dynamic_system_prompt(
            selected_tools={"plan_route_between_places"},
            public_answer=True,
            **common,
        )
        self.assertIn(
            "transit.walking_distance_meters 是全程所有接驳步行的合计",
            public_route_prompt,
        )
        self.assertIn("线路运营时段", public_route_prompt)
        self.assertIn("一律不得用模型常识补写", public_route_prompt)

        calendar_prompt = dynamic_system_prompt(
            selected_tools={"propose_calendar_changes"},
            **common,
        )
        self.assertIn("propose_calendar_changes", calendar_prompt)
        self.assertIn("should-not-leak", calendar_prompt)
        self.assertNotIn("rich_search 始终是可用能力", calendar_prompt)

        plain_prompt = dynamic_system_prompt(
            selected_tools=set(),
            **common,
        )
        self.assertIn("浏览器当前位置状态：不可用", plain_prompt)
        self.assertIn("禁止声称已授权、已定位或已搜索当前位置附近", plain_prompt)

        fallback_prompt = dynamic_system_prompt(
            selected_tools=set(),
            public_answer=True,
            **{
                **common,
                "capability_plan": {
                    "needs_web_search": False,
                    "_runtime_model_fallback_skills": ["web-search"],
                },
            },
        )
        self.assertIn("必须继续用基础模型直接回答", fallback_prompt)
        self.assertIn("不能要求用户安装、开启或连接 Skill", fallback_prompt)
        self.assertIn("无法实时核验", fallback_prompt)

    def test_successful_capability_plan_hides_unrelated_tool_schemas(self):
        tools = [
            SimpleNamespace(name="rich_search"),
            SimpleNamespace(name="plan_route_between_places"),
            SimpleNamespace(name="propose_calendar_changes"),
            SimpleNamespace(name="ask_user_clarification"),
        ]
        selected = tools_for_capability_stage(
            tools, ("plan_route_between_places",),
        )
        self.assertEqual(
            [tool.name for tool in selected],
            ["plan_route_between_places", "ask_user_clarification"],
        )
        self.assertEqual(
            [tool.name for tool in tools_for_capability_stage(tools, ())],
            ["ask_user_clarification"],
        )
        self.assertEqual(
            tools_for_capability_stage(
                tools, (), planner_timed_out=True,
            ),
            tools,
        )

    def test_capability_plan_parser_is_bounded_to_known_booleans(self):
        plan = parse_capability_plan('```json\n{"needs_places": true, "needs_map_action": 1, "strict_today_only": true, "search_query": "北京旅行", "image_query": "故宫建筑", "unknown": true}\n```')
        self.assertTrue(plan["needs_places"])
        self.assertTrue(plan["needs_map_action"])
        self.assertTrue(plan["strict_today_only"])
        self.assertEqual(plan["search_query"], "北京旅行")
        self.assertEqual(plan["image_query"], "故宫建筑")
        self.assertNotIn("unknown", plan)

    def test_missing_critical_information_requires_only_structured_clarification(self):
        plan = {
            "needs_clarification": True,
            "needs_web_search": True,
            "needs_calendar_action": True,
        }
        self.assertEqual(required_tools_for_plan(plan), ("ask_user_clarification",))

    def test_optional_or_undecided_preferences_produce_scenarios_not_questionnaires(self):
        self.assertIn("阻断所有安全且有用的回答", SYSTEM_PROMPT)
        self.assertIn("2–3 套可独立采用的方案", SYSTEM_PROMPT)
        self.assertIn("没决定、都可以、先看看", SYSTEM_PROMPT)
        self.assertIn("用户不需要再点发送", SYSTEM_PROMPT)
        self.assertNotIn("不同选择会明显改变后续结果时，应先用 ask_user_clarification", SYSTEM_PROMPT)

    def test_every_qa_scene_keeps_full_history_clarification_available(self):
        source = (
            AGENTS_ROOT
            / "_application"
            / "chat"
            / "turn_service.py"
        ).read_text(encoding="utf-8")
        graph_source = (AGENTS_ROOT / "chat" / "_graph.py").read_text(encoding="utf-8")
        self.assertNotIn("if not clarification_tool_available", source)
        self.assertIn('required_name and "ask_user_clarification" in allowed_tool_names', graph_source)
        self.assertIn("required_or_question_tools", graph_source)
        self.assertIn("你在此前回答里自行建议、假设或补出的时间", SYSTEM_PROMPT)

    def test_semantic_plan_builds_short_native_action_chain(self):
        plan = {
            "needs_web_search": True,
            "needs_places": True,
            "needs_map_action": True,
            "needs_calendar_action": True,
        }
        self.assertEqual(
            required_tools_for_plan(plan),
            ("rich_search", "recommend_places_on_map", "propose_calendar_changes"),
        )
        allowed = {"rich_search", "recommend_places_on_map", "propose_calendar_changes"}
        self.assertEqual(next_required_tool(required_tools_for_plan(plan), [], allowed), "rich_search")
        self.assertEqual(
            next_required_tool(required_tools_for_plan(plan), ["rich_search"], allowed),
            "recommend_places_on_map",
        )
        self.assertEqual(
            next_required_tool(required_tools_for_plan(plan), ["rich_search", "recommend_places_on_map"], allowed),
            "propose_calendar_changes",
        )

    def test_follow_up_parser_accepts_only_three_unique_questions(self):
        self.assertEqual(
            parse_followups('```json\n["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？", "多余问题？"]\n```'),
            ["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？"],
        )
        self.assertEqual(parse_followups("不是 JSON"), [])

    def test_follow_up_generation_uses_semantic_result_state(self):
        self.assertTrue(should_generate_followups({
            "needs_nearby_places": True,
            "needs_followups": False,
        }))
        self.assertTrue(should_generate_followups({
            "needs_followups": True,
        }))
        self.assertFalse(should_generate_followups({
            "needs_clarification": True,
            "needs_nearby_places": True,
        }))
        self.assertFalse(should_generate_followups(
            {"needs_nearby_places": True},
            blocked_skill="maps",
        ))
        self.assertFalse(should_generate_followups({}))

    async def test_follow_up_generator_uses_the_selected_output_language(self):
        model = SimpleNamespace(ainvoke=AsyncMock(
            return_value=SimpleNamespace(content='["What changed most?"]')
        ))
        result = await generate_followups(
            model,
            "What is new in artificial intelligence this week?",
            plan_context='{"needs_web_search": true}',
            response_language="en",
        )
        self.assertEqual(result, ["What changed most?"])
        system_prompt = model.ainvoke.await_args.args[0][0]["content"]
        self.assertIn("Write every question in clear, concise English.", system_prompt)

    async def test_clarification_tool_converts_finite_text_options_to_single_choice(self):
        tools = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="clarification-policy",
            user_id=TEST_USER_ID, env={},
        )
        clarification = next(item for item in tools if item.name == "ask_user_clarification")
        self.assertIn("阻断所有安全有用的回答", clarification.description)
        self.assertIn("2–3 套带假设与取舍的方案", clarification.description)
        schema = clarification.args_schema.model_json_schema()
        field_schema = schema["$defs"]["ClarificationFieldInput"]
        self.assertEqual(field_schema["required"], ["id", "label", "type"])
        self.assertIn("time", field_schema["properties"]["type"]["enum"])
        self.assertIn("user-visible question", field_schema["properties"]["label"]["description"])
        self.assertIn("never invent a generic profile question", field_schema["properties"]["label"]["description"])
        result = json.loads(await clarification.ainvoke({
            "title": "请选择输出风格",
            "prompt": "选一种即可",
            "fields": [{
                "id": "style",
                "label": "输出风格",
                "type": "text",
                "options": ["简洁", "详细"],
            }],
        }))
        self.assertEqual(result["clarification"]["fields"][0]["type"], "single")
        self.assertEqual(result["clarification"]["fields"][0]["options"], ["简洁", "详细"])

    def test_dsml_tool_protocol_is_normalized(self):
        wire = '''<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="search_arxiv"><｜｜DSML｜｜parameter name="topic" string="true">Zhi-Hua Zhou 2026</｜｜DSML｜｜parameter><｜｜DSML｜｜parameter name="limit" string="false">5</｜｜DSML｜｜parameter></｜｜DSML｜｜invoke></｜｜DSML｜｜tool_calls>'''
        calls = dsml_tool_calls(wire, {"search_arxiv"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "search_arxiv")
        self.assertEqual(calls[0]["args"], {"topic": "Zhi-Hua Zhou 2026", "limit": 5})

