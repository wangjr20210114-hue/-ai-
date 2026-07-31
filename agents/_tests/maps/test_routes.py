from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class MapRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_route_action_is_compacted_only_for_the_next_model_input(self):
        original = ToolMessage(
            name="plan_route_between_places",
            tool_call_id="route-1",
            content=json.dumps({
                "ui_action": "map_action",
                "route_plan_id": "route-plan-1",
                "ordered_stops": [{
                    "place_id": "poi-1",
                    "name": "北京站",
                    "address": "一段无需传给日程模型的详细地址",
                    "latitude": 39.9,
                    "longitude": 116.4,
                }],
                "route": {"duration_minutes": 30},
                "evidence_contract": {
                    "strict": True,
                    "unknown_fields": ["operating_hours"],
                },
                "action": {
                    "id": "map-1",
                    "kind": "map_recommendation",
                    "status": "ready",
                    "payload": {"places": [{"large": "x" * 2000}]},
                },
            }, ensure_ascii=False),
        )
        compacted = compact_tool_results_for_model([original])[0]
        self.assertLess(len(compacted.content), len(original.content) / 3)
        payload = json.loads(compacted.content)
        self.assertEqual(payload["ordered_stops"][0]["place_id"], "poi-1")
        self.assertNotIn("address", payload["ordered_stops"][0])
        self.assertTrue(payload["evidence_contract"]["strict"])
        self.assertEqual(
            payload["evidence_contract"]["unknown_fields"],
            ["operating_hours"],
        )
        self.assertEqual(original.content.count("x"), 2000)

    async def test_route_clarification_planning_keeps_all_prior_card_answers(self):
        messages = [
            HumanMessage(content="规划六站路线"),
            AIMessage(content=""),
            HumanMessage(
                content="第 4 站：北京通州万达广场",
                additional_kwargs={
                    "floris_interaction": "clarification",
                    "clarification_id": "route-stop-4",
                },
            ),
            AIMessage(content=""),
            HumanMessage(
                content="终点：北京西站",
                additional_kwargs={
                    "floris_interaction": "clarification",
                    "clarification_id": "route-stop-6",
                },
            ),
            AIMessage(content=""),
        ]
        answers = await checkpoint_clarification_answers(
            FakeCheckpointer(messages),
            "route-clarification-context",
        )
        self.assertEqual(
            answers,
            ["第 4 站：北京通州万达广场", "终点：北京西站"],
        )
        planning = capability_planning_message(
            "第 5 站：中国人民解放军总医院第一医学中心",
            "route-stop-5",
            ["规划六站路线"],
            answers,
        )
        self.assertIn("北京通州万达广场", planning)
        self.assertIn("北京西站", planning)
        self.assertIn("中国人民解放军总医院第一医学中心", planning)

    async def test_route_planning_does_not_imply_calendar_side_effect(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "needs_calendar_action": False,
        })
        plan = await plan_capabilities(model, "请帮我规划明天的六站行程")
        self.assertFalse(plan["needs_calendar_action"])

    def test_route_plan_uses_verified_route_tool_without_web_estimate(self):
        self.assertEqual(
            required_tools_for_plan({"needs_route": True}),
            ("plan_route_between_places",),
        )
        self.assertEqual(
            required_tools_for_plan({
                "needs_route": True,
                "needs_calendar_action": True,
            }),
            ("plan_route_between_places", "propose_calendar_changes"),
        )
        self.assertIn("一个/多个依次停靠点", SYSTEM_PROMPT)
        self.assertIn("ordered_stops", SYSTEM_PROMPT)
        self.assertIn("不要再问用户“是否需要写入日程”", SYSTEM_PROMPT)
        self.assertIn("source_route_plan_id", SYSTEM_PROMPT)

    async def test_route_tool_resolves_a_brand_near_a_verified_anchor(self):
        station = {
            **PLACE,
            "place_id": "station",
            "name": "北京站",
            "address": "北京市东城区毛家湾胡同甲13号",
        }
        hospital = {
            **PLACE,
            "place_id": "hospital",
            "name": "中国人民解放军总医院",
            "address": "北京市海淀区复兴路28号",
            "latitude": 39.902,
            "longitude": 116.276,
        }
        hotel = {
            **PLACE,
            "place_id": "hotel",
            "name": "锦江之星(北京五棵松店)",
            "address": "北京市海淀区西四环中路",
            "latitude": 39.906,
            "longitude": 116.271,
            "distance_to_anchor_meters": 620,
        }

        async def place_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            return [station] if query == "北京站" else [hospital]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 13_800,
            "duration_seconds": 2_100,
            "fare": {"taxi_fare": 46},
        }
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_search_places_nearby", new=AsyncMock(return_value=[hotel])) as nearby, \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="verified-route",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "city": "北京",
                "destination_near_query": "北京301医院",
            }))

        self.assertEqual(result["origin"]["place_id"], "station")
        self.assertEqual(result["destination"]["place_id"], "hotel")
        self.assertEqual(result["route"]["distance_kilometers"], 13.8)
        self.assertEqual(result["route"]["duration_minutes"], 35)
        self.assertTrue(result["evidence_contract"]["strict"])
        self.assertIn(
            "alternative_lines",
            result["evidence_contract"]["unknown_fields"],
        )
        self.assertIn(
            "route.transit.walking_distance_meters",
            result["evidence_contract"]["aggregate_only"],
        )
        nearby.assert_awaited_once()
        planner.assert_awaited_once()

    async def test_route_tool_preserves_user_order_for_multi_stop_itinerary(self):
        places = {
            "腾讯北京总部": {
                **PLACE,
                "place_id": "tencent",
                "name": "腾讯北京总部大楼",
            },
            "锦江之星": {
                **PLACE,
                "place_id": "jinjiang",
                "name": "锦江之星品尚(北京五棵松店)",
            },
            "烤肉刘王府井店": {
                **PLACE,
                "place_id": "restaurant",
                "name": "清真·烤肉刘炙子烤肉(故宫·王府井店)",
            },
            "桔子酒店北京中关村软件园": {
                **PLACE,
                "place_id": "orange",
                "name": "桔子酒店(北京中关村软件园店)",
            },
        }

        async def place_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            return [places[query]]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 52_400,
            "duration_seconds": 7_200,
            "fare": {"taxi": {"low": 120, "high": 150}},
        }
        store = FakeStore()
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="ordered-itinerary",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "city": "北京",
                "ordered_stops": [
                    {"query": "腾讯北京总部"},
                    {"query": "锦江之星"},
                    {"query": "烤肉刘王府井店"},
                    {"query": "桔子酒店北京中关村软件园"},
                ],
            }))

        ordered_ids = [place["place_id"] for place in result["ordered_stops"]]
        self.assertEqual(ordered_ids, ["tencent", "jinjiang", "restaurant", "orange"])
        planned_places = planner.await_args.args[1]
        self.assertEqual(
            [place["place_id"] for place in planned_places],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertFalse(planner.await_args.kwargs["optimize"])
        self.assertIn("绝不能重新排序", result["response_constraint"])
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertEqual(saved["latest_route_plan"]["id"], result["route_plan_id"])
        self.assertEqual(
            saved["route_plans"][result["route_plan_id"]]["id"],
            result["route_plan_id"],
        )
        self.assertEqual(
            [item["place_id"] for item in saved["latest_route_plan"]["ordered_stops"]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertIn(result["route_plan_id"], latest_route_context(saved))

    async def test_route_tool_restores_origin_dropped_by_second_model_call(self):
        names = {
            "腾讯北京总部": "tencent",
            "锦江之星": "jinjiang",
            "王府井餐厅": "restaurant",
            "桔子酒店": "orange",
        }

        async def place_provider(_key, query, *, city, limit):
            return [{
                **PLACE,
                "place_id": names[query],
                "name": query,
            }]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 50_000,
            "duration_seconds": 7_000,
            "fare": {},
        }
        planned_stops = [
            {"query": "腾讯北京总部", "near_query": ""},
            {"query": "锦江之星", "near_query": ""},
            {"query": "王府井餐厅", "near_query": ""},
            {"query": "桔子酒店", "near_query": ""},
        ]
        store = FakeStore()
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="restore-dropped-origin",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=planned_stops,
                planned_route_city="北京",
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "city": "北京",
                # Simulate the full-history tool model accidentally omitting
                # the stated origin while retaining later stops.
                "ordered_stops": [
                    {"query": "锦江之星"},
                    {"query": "王府井餐厅"},
                    {"query": "桔子酒店"},
                ],
            }))

        self.assertEqual(
            [item["place_id"] for item in result["ordered_stops"]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertEqual(
            [item["place_id"] for item in planner.await_args.args[1]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )

    async def test_route_tool_preserves_browser_origin_before_planned_stops(self):
        destinations = {
            "颐和园": {**PLACE, "place_id": "summer-palace", "name": "颐和园"},
            "故宫": {**PLACE, "place_id": "forbidden-city", "name": "故宫"},
        }

        async def place_provider(_key, query, *, city, limit):
            return [destinations[query]]

        browser_origin = {
            **PLACE,
            "place_id": "browser-current-location",
            "name": "当前位置",
            "provider": "browser-wgs84",
            "coordinate_type": "wgs84",
            "ephemeral": True,
        }
        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 30_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        planned_stops = [{"query": "颐和园"}, {"query": "故宫"}]
        store = FakeStore()
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="browser-origin-planned-stops",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=planned_stops,
                planned_route_uses_current_location=True,
                browser_current_location=browser_origin,
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "ordered_stops": planned_stops,
                "use_current_location_as_origin": True,
            }))

        self.assertEqual(
            [item["place_id"] for item in result["ordered_stops"]],
            ["browser-current-location", "summer-palace", "forbidden-city"],
        )
        self.assertEqual(
            [item["place_id"] for item in planner.await_args.args[1]],
            ["browser-current-location", "summer-palace", "forbidden-city"],
        )
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertNotIn(
            "browser-current-location",
            saved["place_candidates"],
        )
        persisted_origin = saved["latest_route_plan"]["ordered_stops"][0]
        self.assertEqual(
            set(persisted_origin),
            {"place_id", "name", "provider", "ephemeral"},
        )
        self.assertNotIn("latitude", persisted_origin)
        self.assertNotIn("longitude", persisted_origin)
        self.assertNotIn("address", persisted_origin)

    async def test_route_ambiguity_card_identifies_intermediate_stop(self):
        places = {
            "起点公园": [{**PLACE, "place_id": "origin", "name": "起点公园"}],
            "第一站博物馆": [{**PLACE, "place_id": "museum", "name": "第一站博物馆"}],
            "同名餐厅": [
                {**PLACE, "place_id": "restaurant-a", "name": "同名餐厅 A 店"},
                {**PLACE, "place_id": "restaurant-b", "name": "同名餐厅 B 店"},
            ],
            "终点车站": [{**PLACE, "place_id": "destination", "name": "终点车站"}],
        }

        async def place_provider(_key, query, *, city, limit):
            return places[query]

        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="intermediate-stop-ambiguity",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "起点公园"},
                    {"query": "第一站博物馆"},
                    {"query": "同名餐厅"},
                    {"query": "终点车站"},
                ],
            }))

        field = result["clarification"]["fields"][0]
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(field["id"], "route_stop_3")
        self.assertEqual(field["label"], "请选择具体第 3 站")
        self.assertIn("第 3 站", result["clarification"]["prompt"])
        planner.assert_not_awaited()

    async def test_route_shows_ranked_candidates_when_provider_has_no_correction(self):
        origin = {**PLACE, "place_id": "station", "name": "北京站"}
        candidates = [
            {**PLACE, "place_id": "square", "name": "天安门广场"},
            {**PLACE, "place_id": "gate", "name": "天安门"},
            {**PLACE, "place_id": "subway", "name": "天安门东[地铁站]"},
        ]

        async def place_provider(_key, query, *, city, limit):
            return [origin] if query == "北京站" else candidates

        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="semantic-candidate-route",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "天安们",
                "route_mode": "walking",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["type"], "single")
        self.assertGreaterEqual(len(field["options"]), 2)
        self.assertIn("天安门", field["options"][0])
        planner.assert_not_awaited()

    async def test_route_semantic_review_can_use_canonical_provider_candidate(self):
        class CanonicalPlaceModel:
            def __init__(self):
                self.schema = None
                self.calls = 0

            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                self.calls += 1
                return {
                    "parsed": self.schema(
                        unique_intent=True,
                        selected_place_id="station-main",
                    ),
                }

        model = CanonicalPlaceModel()
        station_candidates = [
            {**PLACE, "place_id": "station-main", "name": "北京站"},
            {
                **PLACE,
                "place_id": "station-subway",
                "name": "北京站[地铁站]",
            },
        ]
        destination = {
            **PLACE,
            "place_id": "destination",
            "name": "故宫博物院",
        }

        async def place_provider(_key, query, *, city, limit):
            return station_candidates if query == "北京站" else [destination]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 8_000,
            "duration_seconds": 1_800,
            "fare": {},
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=place_provider,
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(return_value=route),
        ) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="canonical-provider-place",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                place_disambiguation_model=model,
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "故宫博物院",
            }))

        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(result["ordered_stops"][0]["place_id"], "station-main")
        self.assertEqual(model.calls, 1)
        planner.assert_awaited_once()

    async def test_route_search_timeout_returns_fill_in_card(self):
        async def place_provider(_key, _query, *, city, limit):
            raise TimeoutError("provider deadline")

        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=place_provider,
        ), patch(
            "agents._infrastructure.skills.builtin_operations.load_place_cache",
            new=AsyncMock(return_value=None),
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(),
        ) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="route-timeout-fill-card",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                map_preferences={"search_timeout_seconds": 3},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "起点",
                "destination_query": "无法核实的终点",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(
            result["clarification"]["fields"][0]["type"],
            "text",
        )
        self.assertIn("时间预算", result["clarification"]["prompt"])
        planner.assert_not_awaited()

    async def test_route_collects_all_place_blockers_in_one_card_group(self):
        origin = {**PLACE, "place_id": "origin", "name": "北京站"}
        branches = [
            {
                **PLACE,
                "place_id": "branch-a",
                "name": "北京通州万达广场",
                "address": "新华西街58号",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京通州万达广场",
                    "evidence": "tencent_place_search",
                },
            },
            {
                **PLACE,
                "place_id": "branch-b",
                "name": "北京五棵松万达广场",
                "address": "复兴路69号",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京五棵松万达广场",
                    "evidence": "tencent_place_search",
                },
            },
        ]
        destination = {
            **PLACE,
            "place_id": "destination",
            "name": "北京西站",
        }

        async def place_provider(_key, query, *, city, limit):
            return {
                "北京站": [origin],
                "万达广场": branches,
                "不存在终点": [],
                "北京西站": [destination],
            }[query]

        store = FakeStore()
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=place_provider,
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(),
        ) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-multiple-card-state",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            first = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "北京站"},
                    {"query": "万达广场"},
                    {"query": "不存在终点"},
                ],
            }))
            third = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "北京站"},
                    {"query": "万达广场"},
                    {"query": "北京西站"},
                ],
            }))

        fields = first["clarification"]["fields"]
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["type"], "single")
        self.assertEqual(fields[1]["type"], "text")
        self.assertEqual(fields[0]["id"], "route_stop_2")
        self.assertRegex(fields[1]["id"], r"route_destination_[0-9a-f]{6}")
        self.assertIn("一次填完", first["clarification"]["prompt"])
        self.assertEqual(third["clarification"]["fields"][0]["type"], "single")
        self.assertIn("北京通州万达广场", third["clarification"]["fields"][0]["options"][0])
        planner.assert_not_awaited()

    def test_route_tool_fallback_does_not_rewrite_place_text(self):
        self.assertEqual(
            preserve_planned_route_stops(
                [("北京站", ""), ("天安门", "")],
                [],
                "从北京站步行去天安们",
            ),
            [("北京站", ""), ("天安门", "")],
        )

    async def test_route_calendar_proposal_rejects_compressed_stops_and_accepts_complete_order(self):
        store = FakeStore()
        state = empty_workspace()
        now = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)
        stops = [
            {
                **PLACE,
                "place_id": place_id,
                "name": name,
                "address": f"北京市{name}地址",
            }
            for place_id, name in (
                ("tencent", "腾讯北京总部大楼"),
                ("jinjiang", "锦江之星品尚(北京五棵松店)"),
                ("restaurant", "清真·烤肉刘炙子烤肉(故宫·王府井店)"),
                ("orange", "桔子酒店(北京中关村软件园店)"),
            )
        ]
        state["place_candidates"] = {item["place_id"]: item for item in stops}
        state["latest_route_plan"] = {
            "id": "routeplan-complete",
            "created_at": int(time.time()),
            "ordered_stops": stops,
            "distance_meters": 62_800,
            "duration_seconds": 9_720,
        }
        await save_user_workspace(store, state, TEST_USER_ID)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="route-calendar",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(item for item in tools if item.name == "propose_calendar_changes")

        def change(index: int) -> dict:
            start = now + timedelta(minutes=index * 45)
            return {
                "operation": "create",
                "event": {
                    "title": f"第{index + 1}站：{stops[index]['name']}",
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(minutes=30)).isoformat(),
                    "place_id": stops[index]["place_id"],
                },
            }

        with self.assertRaisesRegex(ValueError, "完整路线包含 4 个站点"):
            await calendar_tool.ainvoke({
                "summary": "压缩后的两站行程",
                "source_route_plan_id": "routeplan-complete",
                "changes": [change(0), change(2)],
            })

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "完整四站行程",
            "source_route_plan_id": "routeplan-complete",
            "changes": [change(index) for index in range(4)],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        self.assertEqual(result["action"]["payload"]["source_route_plan_id"], "routeplan-complete")
        self.assertEqual(len(result["action"]["payload"]["changes"]), 4)

    async def test_route_calendar_normalizes_instant_verified_stop_markers(self):
        store = FakeStore()
        state = empty_workspace()
        stops = [
            {
                **PLACE,
                "place_id": place_id,
                "name": name,
                "address": f"北京市{name}地址",
            }
            for place_id, name in (
                ("beijing-station", "北京站"),
                ("forbidden-city", "故宫博物院"),
                ("beijing-west", "北京西站"),
            )
        ]
        state["place_candidates"] = {item["place_id"]: item for item in stops}
        route_plan = {
            "id": "routeplan-instant-markers",
            "created_at": int(time.time()),
            "ordered_stops": stops,
            "distance_meters": 18_000,
            "duration_seconds": 4_200,
            "mode": "transit",
        }
        state["latest_route_plan"] = route_plan
        state["route_plans"] = {route_plan["id"]: route_plan}
        await save_user_workspace(store, state, TEST_USER_ID)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="route-calendar-instant-markers",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)

        def event(
            index: int,
            event_start: datetime,
            duration_minutes: int,
        ) -> dict:
            return {
                "operation": "create",
                "event": {
                    "title": stops[index]["name"],
                    "start_time": event_start.isoformat(),
                    "end_time": (
                        event_start + timedelta(minutes=duration_minutes)
                    ).isoformat(),
                    "location_kind": "physical",
                },
            }

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "含瞬时出发和抵达提醒的三站行程",
            "source_route_plan_id": "routeplan-instant-markers",
            "changes": [
                event(0, start, 0),
                event(1, start + timedelta(minutes=40), 45),
                event(2, start + timedelta(minutes=120), 0),
            ],
        }))

        payload = result["action"]["payload"]
        self.assertEqual(
            payload["source_route_plan_id"],
            "routeplan-instant-markers",
        )
        self.assertEqual(
            [
                change["event"]["duration_minutes"]
                for change in payload["changes"]
            ],
            [1, 45, 1],
        )
        self.assertEqual(
            [
                change["event"]["place"]["place_id"]
                for change in payload["changes"]
            ],
            [stop["place_id"] for stop in stops],
        )
        self.assertTrue(
            any("最小粒度" in warning for warning in payload["warnings"])
        )
        self.assertTrue(
            any("站点顺序补齐" in warning for warning in payload["warnings"])
        )

    async def test_route_calendar_keeps_recent_source_when_another_route_is_latest(self):
        store = FakeStore()
        state = empty_workspace()
        intended_stops = [
            {
                **PLACE,
                "place_id": f"intended-{index}",
                "name": name,
                "address": f"北京市{name}地址",
            }
            for index, name in enumerate(("北京站", "故宫博物院", "北京西站"), 1)
        ]
        other_stops = [
            {
                **PLACE,
                "place_id": f"other-{index}",
                "name": name,
            }
            for index, name in enumerate(("上海站", "外滩"), 1)
        ]
        intended_route = {
            "id": "routeplan-intended",
            "created_at": int(time.time()) - 10,
            "ordered_stops": intended_stops,
            "duration_seconds": 4_200,
        }
        latest_route = {
            "id": "routeplan-other",
            "created_at": int(time.time()),
            "ordered_stops": other_stops,
            "duration_seconds": 1_800,
        }
        state["place_candidates"] = {
            stop["place_id"]: stop
            for stop in other_stops
        }
        state["latest_route_plan"] = latest_route
        state["route_plans"] = {
            intended_route["id"]: intended_route,
            latest_route["id"]: latest_route,
        }
        await save_user_workspace(store, state, TEST_USER_ID)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="route-calendar-recent-source",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)
        changes = [
            {
                "operation": "create",
                "event": {
                    "title": stop["name"],
                    "start_time": (
                        start + timedelta(minutes=index * 60)
                    ).isoformat(),
                    "end_time": (
                        start + timedelta(minutes=index * 60 + 45)
                    ).isoformat(),
                },
            }
            for index, stop in enumerate(intended_stops)
        ]

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "把先前核实的北京路线加入日程",
            "source_route_plan_id": intended_route["id"],
            "changes": changes,
        }))

        payload = result["action"]["payload"]
        self.assertEqual(
            payload["source_route_plan_id"],
            intended_route["id"],
        )
        self.assertEqual(
            [
                change["event"]["place"]["place_id"]
                for change in payload["changes"]
            ],
            [stop["place_id"] for stop in intended_stops],
        )

    async def test_route_calendar_does_not_persist_implicit_browser_origin(self):
        store = FakeStore()
        state = empty_workspace()
        browser_origin = {
            **PLACE,
            "place_id": "browser-current-location",
            "provider": "browser-tencent",
            "name": "当前位置",
            "ephemeral": True,
        }
        destination = {
            **PLACE,
            "place_id": "summer-palace",
            "name": "颐和园",
            "address": "北京市海淀区新建宫门路19号",
        }
        state["place_candidates"] = {
            destination["place_id"]: destination,
        }
        state["latest_route_plan"] = {
            "id": "routeplan-browser-origin",
            "created_at": int(time.time()),
            "ordered_stops": [browser_origin, destination],
            "implicit_browser_origin": True,
            "distance_meters": 7_884,
            "duration_seconds": 1_380,
        }
        await save_user_workspace(store, state, TEST_USER_ID)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="route-calendar-browser-origin",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "从当前位置去颐和园",
            "source_route_plan_id": "routeplan-browser-origin",
            "changes": [
                {
                    "operation": "create",
                    "event": {
                        "title": "从当前位置出发",
                        "start_time": start.isoformat(),
                        "end_time": (start + timedelta(minutes=1)).isoformat(),
                        "place_id": browser_origin["place_id"],
                    },
                },
                {
                    "operation": "create",
                    "event": {
                        "title": "游览颐和园",
                        "start_time": (start + timedelta(minutes=23)).isoformat(),
                        "end_time": (start + timedelta(hours=2)).isoformat(),
                        "place_id": destination["place_id"],
                    },
                },
            ],
        }))

        self.assertEqual(result["ui_action"], "calendar_action")
        payload = result["action"]["payload"]
        self.assertEqual(payload["source_route_plan_id"], "routeplan-browser-origin")
        self.assertEqual(len(payload["changes"]), 2)
        self.assertNotIn("place", payload["changes"][0]["event"])
        self.assertEqual(payload["changes"][0]["event"]["location"], "")
        self.assertEqual(
            payload["changes"][1]["event"]["place"]["place_id"],
            "summer-palace",
        )
        self.assertNotIn("browser-current-location", json.dumps(payload))

    async def test_route_tool_revalidates_descriptive_aliases_with_provider(self):
        store = FakeStore()
        state = empty_workspace()
        headquarters = {
            **PLACE,
            "place_id": "tencent",
            "name": "腾讯北京总部大楼",
            "address": "北京市海淀区西北旺东路10号院西区9号楼",
        }
        restaurant = {
            **PLACE,
            "place_id": "restaurant",
            "name": "清真·烤肉刘炙子烤肉(故宫·王府井店)",
            "address": "北京市东城区王府井大街",
        }
        state["place_candidates"] = {
            headquarters["place_id"]: headquarters,
            restaurant["place_id"]: restaurant,
        }
        await save_user_workspace(store, state, TEST_USER_ID)
        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 28_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(side_effect=[[headquarters], [restaurant]]),
        ) as search, \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="workspace-alias-route",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "腾讯北京总部",
                "destination_query": "烤肉刘（故宫·王府井店）",
                "city": "北京",
            }))

        self.assertEqual(result["origin"]["place_id"], "tencent")
        self.assertEqual(result["destination"]["place_id"], "restaurant")
        self.assertEqual(search.await_count, 2)
        planner.assert_awaited_once()

    def test_route_failure_fallback_does_not_claim_a_confirmation_card(self):
        content = tool_failure_fallback([
            HumanMessage(content="帮我规划四站行程"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "没有核实到第 3 站",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                name="plan_route_between_places",
                tool_call_id="route-failed",
            ),
        ])
        self.assertIn("没有完成路线规划", content)
        self.assertNotIn("确认卡", content)

    async def test_route_tool_asks_user_to_choose_when_nearby_brand_has_multiple_branches(self):
        station = {**PLACE, "place_id": "station", "name": "北京站"}
        hospital = {**PLACE, "place_id": "hospital", "name": "北京301医院"}
        hotels = [
            {
                **PLACE,
                "place_id": f"hotel-{index}",
                "name": f"锦江之星({name}店)",
                "address": f"北京市海淀区{name}路",
                "distance_to_anchor_meters": distance,
            }
            for index, (name, distance) in enumerate((("五棵松", 620), ("玉泉路", 1800)), 1)
        ]

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else [hospital]

        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=place_provider), \
             patch("agents._infrastructure.skills.builtin_operations.provider_search_places_nearby", new=AsyncMock(return_value=hotels)), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="ambiguous-route",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "city": "北京",
                "destination_near_query": "北京301医院",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["type"], "single")
        self.assertEqual(len(result["clarification"]["fields"][0]["options"]), 2)
        self.assertEqual(
            set(result["clarification"]["fields"][0]["option_values"].values()),
            {"floris-place:hotel-1", "floris-place:hotel-2"},
        )
        planner.assert_not_awaited()

    async def test_route_card_choices_resume_by_place_id_without_repeated_search(self):
        station = {
            **PLACE,
            "place_id": "station",
            "name": "北京站",
            "address": "北京市东城区毛家湾胡同甲13号",
        }
        peach_places = [
            {
                **PLACE,
                "place_id": f"peach-{index}",
                "name": name,
                "address": address,
            }
            for index, (name, address) in enumerate((
                ("桃花源景区", "北京市海淀区黑山扈北口19号"),
                ("桃花湾", "北京市门头沟区妙峰山镇"),
            ), 1)
        ]
        park_places = [
            {
                **PLACE,
                "place_id": f"park-{index}",
                "name": name,
                "address": address,
            }
            for index, (name, address) in enumerate((
                ("百望山森林公园", "北京市海淀区黑山扈北口19号"),
                ("百望公园", "北京市海淀区西北旺镇"),
            ), 1)
        ]

        async def place_provider(_key, query, *, city, limit):
            if query == "北京站":
                return [station]
            if query == "桃花源景区":
                return peach_places
            if query == "Baiwang Park":
                return park_places
            raise AssertionError(f"confirmed candidate must not be searched again: {query}")

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 28_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        store = FakeStore()
        search = AsyncMock(side_effect=place_provider)
        planner = AsyncMock(return_value=route)
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=search), \
             patch("agents._infrastructure.skills.builtin_operations.provider_plan_route", new=planner):
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="resume-route-place-ids",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            original_arguments = {
                "city": "北京",
                "ordered_stops": [
                    {"query": "北京站", "near_query": ""},
                    {"query": "桃花源景区", "near_query": ""},
                    {"query": "Baiwang Park", "near_query": ""},
                ],
            }
            first = json.loads(await route_tool.ainvoke(original_arguments))
            self.assertEqual(first["ui_action"], "clarification_action")
            fields = first["clarification"]["fields"]
            self.assertEqual(
                [field["id"] for field in fields],
                ["route_stop_2", "route_destination"],
            )
            answers = [
                {
                    "id": field["id"],
                    "value": field["option_values"][field["options"][0]],
                }
                for field in fields
            ]
            plan, resumed_arguments = resume_capability_protocol(
                {"needs_route": False},
                {
                    "version": "1",
                    "required_tools": ["plan_route_between_places"],
                    "planned_tool_arguments": {
                        "plan_route_between_places": original_arguments,
                    },
                },
                answers,
            )
            resumed_route = resumed_arguments["plan_route_between_places"]
            resumed_tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="resume-route-place-ids",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=plan["route_stops"],
                planned_route_city="北京",
            )
            resumed_tool = next(
                item for item in resumed_tools
                if item.name == "plan_route_between_places"
            )
            second = json.loads(await resumed_tool.ainvoke(resumed_route))

        self.assertEqual(second["ui_action"], "map_action")
        self.assertEqual(
            [place["place_id"] for place in second["ordered_stops"]],
            ["station", "peach-1", "park-1"],
        )
        self.assertEqual(search.await_count, 3)
        planner.assert_awaited_once()

    async def test_route_tool_never_silently_picks_one_of_multiple_nearby_anchors(self):
        station = {**PLACE, "place_id": "station", "name": "北京站"}
        anchors = [
            {
                **PLACE,
                "place_id": "wanda-cbd",
                "name": "万达广场",
                "address": "北京市朝阳区建国路93号",
            },
            {
                **PLACE,
                "place_id": "wanda-fengtai",
                "name": "万达广场(丰台店)",
                "address": "北京市丰台区",
            },
        ]

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else anchors

        with (
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_search_places",
                new=place_provider,
            ),
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
                new=AsyncMock(),
            ) as nearby,
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_plan_route",
                new=AsyncMock(),
            ) as planner,
        ):
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="ambiguous-nearby-anchor",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "destination_near_query": "万达广场",
                "city": "北京",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["id"], "route_destination_anchor")
        self.assertEqual(field["type"], "single")
        self.assertEqual(len(field["options"]), 2)
        nearby.assert_not_awaited()
        planner.assert_not_awaited()

    async def test_route_change_retires_stale_route_risk_notification(self):
        store = FakeStore()
        now = int(time.time())
        state = empty_workspace()
        first = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "A", "start_time": now + 3600, "duration_minutes": 60, "place": PLACE},
        }])[0]
        second_place = {**PLACE, "place_id": "poi-2", "name": "颐和园", "longitude": 116.273}
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "B", "start_time": now + 7500, "duration_minutes": 60, "place": second_place},
        }])
        await save_workspace(store, TEST_USER_ID, state)
        proactive = empty_proactive_state()
        signals = [{
            "type": "route_risk", "source": "provider_route",
            "dedup_key": f"route_risk:{first['id']}:old", "priority": "high",
            "subject_ids": [first["id"]], "title": "路程不足", "detail": "旧风险",
            "action": "调整时间", "evidence": {}, "occurred_at": now,
        }]
        process_schedule_signals(proactive, signals, now)
        await save_proactive_state(store, proactive, TEST_USER_ID)
        with patch("agents._controllers.workspace_controller.collect_provider_signals", AsyncMock(return_value=([], {}))):
            response = await handler(FakeContext(store, {
                "operation": "save_travel_plan",
                "plan": {"title": "路线变更", "destination": "北京", "days": 1},
            }))
        self.assertEqual(response["travel_plan"]["title"], "路线变更")
        refreshed = public_proactive_state(await load_proactive_state(store, TEST_USER_ID))
        self.assertFalse(any(item["type"] == "route_risk" for item in refreshed["notifications"]))

