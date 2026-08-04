from agents._tests.support.workspace_environment import *  # noqa: F401,F403
from agents._infrastructure.providers.tencent_location import normalize_route_contract


class MapRouteCoreTests(unittest.IsolatedAsyncioTestCase):
    def test_calendar_compaction_preserves_frozen_timeline_facts(self):
        original = ToolMessage(
            name="propose_calendar_changes",
            tool_call_id="calendar-1",
            content=json.dumps({
                "ui_action": "calendar_action",
                "action": {
                    "id": "cal-1",
                    "kind": "calendar_changes",
                    "status": "awaiting_confirmation",
                    "payload": {
                        "summary": "杭州一日游",
                        "changes": [{
                            "operation": "create",
                            "event": {
                                "title": "第2站：灵隐寺",
                                "start_time": 1785882600,
                                "duration_minutes": 120,
                                "location": "灵隐路",
                                "description": "不需要进入模型上下文的长说明",
                            },
                        }],
                    },
                },
            }, ensure_ascii=False),
        )

        compacted = compact_tool_results_for_model([original])[0]
        payload = json.loads(compacted.content)
        event = payload["action"]["changes"][0]["event"]
        self.assertEqual(event["start_time"], 1785882600)
        self.assertEqual(event["duration_minutes"], 120)
        self.assertEqual(event["title"], "第2站：灵隐寺")
        self.assertNotIn("description", event)

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
            "mode": "transit",
            "distance_meters": 52_400,
            "duration_seconds": 7_200,
            "fare": {"taxi": {"low": 120, "high": 150}},
            "legs": [
                {
                    "mode": "transit",
                    "distance_meters": 18_000,
                    "duration_seconds": 2_400,
                    "sections": [
                        {
                            "mode": "walking",
                            "distance_meters": 500,
                            "duration_seconds": 420,
                            "instruction": "步行到公交站",
                        },
                        {
                            "mode": "bus",
                            "line": "杭州公交 1 路",
                            "vehicle": "BUS",
                            "distance_meters": 17_500,
                            "duration_seconds": 1_980,
                            "geton": "起点站",
                            "getoff": "西湖站",
                        },
                    ],
                },
            ],
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
        self.assertNotIn("route", result["action"]["payload"])
        self.assertIn("绝不能重新排序", result["response_constraint"])
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertEqual(
            saved["actions"][result["action"]["id"]]["payload"]["route"],
            normalize_route_contract(route),
        )
        self.assertEqual(saved["latest_route_plan"]["id"], result["route_plan_id"])
        self.assertEqual(
            saved["route_plans"][result["route_plan_id"]]["id"],
            result["route_plan_id"],
        )
        self.assertEqual(
            [item["place_id"] for item in saved["latest_route_plan"]["ordered_stops"]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        saved_leg = saved["latest_route_plan"]["legs"][0]
        self.assertEqual(
            [section["mode"] for section in saved_leg["sections"]],
            ["walking", "bus"],
        )
        self.assertEqual(saved_leg["sections"][1]["line"], "杭州公交 1 路")
        context = json.loads(latest_route_context(saved))
        self.assertEqual(
            [section["mode"] for section in context["legs"][0]["sections"]],
            ["walking", "bus"],
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
                planned_route_origin_is_departure=True,
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
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertTrue(saved["latest_route_plan"]["explicit_origin_is_departure"])

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
            "agents._infrastructure.skills.map_runtime.load_place_cache",
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
