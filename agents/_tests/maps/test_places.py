from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class MapPlaceTests(unittest.IsolatedAsyncioTestCase):
    def test_resume_protocol_applies_nearby_anchor_choice(self):
        plan, arguments = resume_capability_protocol(
            {"needs_nearby_places": False},
            {
                "version": 1,
                "required_tools": ["recommend_nearby_places_on_map"],
                "planned_tool_arguments": {
                    "recommend_nearby_places_on_map": {
                        "anchor_query": "北京天安门",
                        "anchor_queries": [],
                        "query": "景点",
                        "use_current_location_as_anchor": False,
                    },
                },
            },
            [{
                "id": "anchor_0",
                "value": "天安门广场｜北京市东城区东长安街",
            }],
        )
        expected_anchor = "天安门广场｜北京市东城区东长安街"
        self.assertTrue(plan["needs_nearby_places"])
        self.assertEqual(plan["nearby_anchor_query"], expected_anchor)
        self.assertEqual(plan["nearby_query"], "景点")
        self.assertEqual(
            arguments["recommend_nearby_places_on_map"]["anchor_query"],
            expected_anchor,
        )

    def test_resume_protocol_turns_manual_location_into_nearby_anchor(self):
        plan, arguments = resume_capability_protocol(
            {"needs_nearby_places": False},
            {
                "version": 1,
                "required_tools": ["recommend_nearby_places_on_map"],
                "planned_tool_arguments": {
                    "recommend_nearby_places_on_map": {
                        "anchor_query": "",
                        "anchor_queries": [],
                        "query": "公园",
                        "use_current_location_as_anchor": True,
                    },
                },
            },
            [{
                "id": "nearby_anchor",
                "value": "北京市海淀区中关村",
            }],
        )
        nearby = arguments["recommend_nearby_places_on_map"]
        self.assertEqual(nearby["anchor_query"], "北京市海淀区中关村")
        self.assertFalse(nearby["use_current_location_as_anchor"])
        self.assertFalse(plan["nearby_uses_current_location"])

    async def test_capability_planner_timeout_never_infers_nearby_category(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "这附近有什么好吃的？",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertEqual(required_tools_for_plan(plan), ())
        self.assertEqual(plan["nearby_query"], "")

    def test_system_prompt_formats_without_accidental_placeholders(self):
        rendered = SYSTEM_PROMPT.format(
            now="2026-07-15 12:00:00 UTC+08:00",
            response_language_instruction="使用简体中文。",
            capability_plan='{"needs_places": true}',
            calendar_context='[{"id":"cal-live"}]',
            reference_image_context="无",
            document_context="无",
        )
        self.assertIn("2026-07-15", rendered)

    def test_current_location_plan_uses_tencent_reverse_geocode_tool(self):
        self.assertEqual(
            required_tools_for_plan({"needs_current_location": True}),
            ("get_current_location",),
        )

    def test_nearby_plan_uses_one_native_location_composite(self):
        self.assertEqual(
            required_tools_for_plan({
                "needs_nearby_places": True,
                "needs_places": True,
                "needs_map_action": True,
            }),
            ("recommend_nearby_places_on_map",),
        )

    def test_proactive_window_queues_by_fcfs_without_replacement(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 50,
            "window_limit": 4,
            "quiet_hours": {"enabled": False},
        })
        for index in range(5):
            stats = process_schedule_signals(state, [{
                "type": "schedule_upcoming",
                "dedup_key": f"operation:{index}",
                "title": f"操作提醒{index}",
                "detail": "来自用户操作",
                "action": "继续处理",
                "occurred_at": now + index,
            }], now + index)
        public = public_proactive_state(state, now + 10)
        self.assertEqual(len(public["notifications"]), 4)
        self.assertEqual(stats["window_replaced"], 0)
        self.assertEqual(stats["window_queued"], 1)
        self.assertEqual(
            [item["title"] for item in public["notifications"]],
            ["操作提醒0", "操作提醒1", "操作提醒2", "操作提醒3"],
        )

    async def test_map_action_requires_explicit_activation(self):
        store = FakeStore()
        state = empty_workspace()
        action = new_action("map_recommendation", {"title": "推荐", "places": [PLACE]}, requires_confirmation=False)
        put_action(state, action)
        await save_workspace(store, TEST_USER_ID, state)
        before = await handler(FakeContext(store, {"operation": "get"}))
        self.assertIsNone(before["map"])
        after = await handler(FakeContext(store, {"operation": "activate_map", "action_id": action["id"], "version": 1}))
        self.assertEqual(after["map"]["places"][0]["place_id"], "poi-1")
        proactive = await load_proactive_state(store, TEST_USER_ID)
        self.assertEqual(proactive["checkpoints"]["route_change"]["schedule_count"], 0)
        self.assertTrue(any(event["type"] == "route_changed" for event in proactive["events"].values()))

    async def test_model_selected_places_are_verified_in_parallel(self):
        started: set[str] = set()
        all_started = asyncio.Event()

        async def provider(_map_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 3)
            started.add(query)
            if len(started) == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=0.2)
            return [{
                **PLACE,
                "place_id": f"poi-{query}",
                "name": query,
                "address": f"北京市朝阳区{query}",
            }]

        selected, candidates, missing = await verify_place_queries_parallel(
            provider,
            "map-key",
            ["餐馆甲", "餐馆乙", "餐馆丙"],
            city="北京",
            timeout_seconds=1,
        )

        self.assertEqual([place["name"] for place in selected], ["餐馆甲", "餐馆乙", "餐馆丙"])
        self.assertEqual(len(candidates), 3)
        self.assertEqual(missing, [])

    async def test_model_selected_place_rejects_wrong_city_and_unrelated_name(self):
        valid = {
            **PLACE,
            "place_id": "valid-restaurant",
            "name": "小吊梨汤(王府井银泰店)",
            "address": "北京市东城区王府井大街88号",
            "city": "北京市",
        }
        wrong_city = {
            **PLACE,
            "place_id": "wrong-city",
            "name": "小吊梨汤",
            "address": "上海市浦东新区",
            "city": "上海市",
        }
        unrelated = {
            **PLACE,
            "place_id": "unrelated",
            "name": "庐江县气象局",
            "address": "安徽省合肥市庐江县",
            "city": "庐江县",
        }

        async def provider(_map_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 3)
            if "小吊梨汤" in query:
                return [wrong_city, valid]
            return [unrelated]

        selected, candidates, missing = await verify_place_queries_parallel(
            provider,
            "map-key",
            ["小吊梨汤王府井银泰店", "四季民福王府井店"],
            city="北京",
            timeout_seconds=1,
        )

        self.assertEqual([place["place_id"] for place in selected], ["valid-restaurant"])
        self.assertEqual([place["place_id"] for place in candidates], ["valid-restaurant"])
        self.assertEqual(missing, ["四季民福王府井店"])

    async def test_map_recommendation_keeps_verified_subset(self):
        async def provider(_map_key, query, *, city, limit):
            if query == "未核实餐馆":
                return []
            return [{**PLACE, "place_id": f"poi-{query}", "name": query}]

        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=provider):
            tools = build_system_skill_tools(
                None, store=FakeStore(), conversation_id="partial-map",
                user_id=TEST_USER_ID, env={},
            )
            tool = next(item for item in tools if item.name == "recommend_places_on_map")
            result = json.loads(await tool.ainvoke({
                "queries": ["真实餐馆", "未核实餐馆"],
                "city": "北京",
                "title": "餐馆推荐",
                "action_text": "在地图中查看",
            }))

        self.assertTrue(result["partial"])
        self.assertEqual(result["verified_place_count"], 1)
        self.assertEqual(result["unverified_queries"], ["未核实餐馆"])
        self.assertIn("实际核实成功 1/2 个地点", result["response_constraint"])
        self.assertIn("正文只能声称地图显示了 1 个", result["response_constraint"])
        self.assertIn("未核实餐馆", result["response_constraint"])
        self.assertEqual([place["name"] for place in result["action"]["payload"]["places"]], ["真实餐馆"])

    async def test_map_recommendation_rejects_when_every_place_is_unverified(self):
        async def provider(_map_key, query, *, city, limit):
            return []

        with patch("agents._infrastructure.skills.builtin_operations.provider_search_places", new=provider):
            tools = build_system_skill_tools(
                None, store=FakeStore(), conversation_id="empty-map",
                user_id=TEST_USER_ID, env={},
            )
            tool = next(item for item in tools if item.name == "recommend_places_on_map")
            with self.assertRaisesRegex(ValueError, "所有候选地点都未通过真实地点服务核实"):
                await tool.ainvoke({
                    "queries": ["未核实餐馆甲", "未核实餐馆乙"],
                    "city": "北京",
                    "title": "餐馆推荐",
                    "action_text": "在地图中查看",
                })

    async def test_nearby_recommendation_reuses_schedule_anchor_and_prepares_map(self):
        store = FakeStore()
        anchor = {
            **PLACE,
            "place_id": "orange-hotel",
            "name": "桔子酒店(北京中关村软件园店)",
            "address": "北京市海淀区西北旺付家窑丁2号",
            "latitude": 40.042246,
            "longitude": 116.255289,
        }
        state = empty_workspace()
        state["schedules"]["hotel-stay"] = {
            "id": "hotel-stay",
            "title": "入住桔子酒店",
            "extra": {"place": anchor},
        }
        await save_user_workspace(store, state, TEST_USER_ID)
        breakfast_places = [
            {
                **PLACE,
                "place_id": "breakfast-1",
                "name": "庆丰包子铺(软件园店)",
                "address": "北京市海淀区软件园路",
                "latitude": 40.0419,
                "longitude": 116.257,
                "distance_to_anchor_meters": 180.0,
            },
            {
                **PLACE,
                "place_id": "breakfast-2",
                "name": "麦当劳(西北旺店)",
                "address": "北京市海淀区西北旺路",
                "latitude": 40.044,
                "longitude": 116.258,
                "distance_to_anchor_meters": 360.0,
            },
        ]

        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(),
        ) as anchor_provider, patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
            new=AsyncMock(return_value=breakfast_places),
        ) as nearby_provider:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="nearby-breakfast",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "桔子酒店(北京中关村软件园店)",
                "query": "早餐店",
                "city": "北京",
                "limit": 5,
                "title": "酒店附近早餐",
                "action_text": "在地图中查看",
            }))

        anchor_provider.assert_not_awaited()
        nearby_provider.assert_awaited_once_with(
            "map-key",
            "早餐店",
            anchor,
            radius_meters=2000,
            limit=5,
        )
        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(result["anchor"]["place_id"], "orange-hotel")
        self.assertEqual(result["verified_place_count"], 2)
        self.assertEqual(
            [place["place_id"] for place in result["action"]["payload"]["places"]],
            ["breakfast-1", "breakfast-2"],
        )

    async def test_nearby_current_location_uses_request_scoped_browser_fix(self):
        browser_location = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 39.913,
            "longitude": 116.456,
            "coordinate_type": "wgs84",
        }
        park = {
            **PLACE,
            "place_id": "nearby-park",
            "name": "测试公园",
            "address": "北京市朝阳区",
            "latitude": 39.914,
            "longitude": 116.455,
            "distance_to_anchor_meters": 180.0,
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(),
        ) as place_search, patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
            new=AsyncMock(return_value=[park]),
        ) as nearby_search:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="nearby-browser-location",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=browser_location,
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "",
                "query": "公园",
                "use_current_location_as_anchor": True,
            }))

        place_search.assert_not_awaited()
        nearby_search.assert_awaited_once_with(
            "map-key",
            "公园",
            browser_location,
            radius_meters=2_000,
            limit=5,
        )
        self.assertEqual(result["anchor"]["place_id"], "browser-current-location")
        self.assertEqual(result["groups"][0]["anchor_query"], "当前位置")
        self.assertEqual(result["places"][0]["place_id"], "nearby-park")

    async def test_current_location_tool_returns_tencent_address_without_coordinates(self):
        browser_location = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 43.8171,
            "longitude": 125.3235,
            "coordinate_type": "wgs84",
            "accuracy_meters": 18,
        }
        resolved = {
            "provider": "tencent",
            "address": "吉林省长春市朝阳区前进大街2699号",
            "province": "吉林省",
            "city": "长春市",
            "district": "朝阳区",
            "street": "前进大街",
            "street_number": "2699号",
            "nearby_landmark": "吉林大学前卫南区",
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_reverse_geocode",
            new=AsyncMock(return_value=resolved),
        ) as provider:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="current-location-address",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=browser_location,
            )
            tool = next(item for item in tools if item.name == "get_current_location")
            result = json.loads(await tool.ainvoke({}))

        provider.assert_awaited_once_with("map-key", browser_location)
        self.assertTrue(result["location_available"])
        self.assertEqual(result["location"]["city"], "长春市")
        self.assertNotIn("latitude", result["location"])
        self.assertNotIn("longitude", result["location"])

    async def test_current_location_tool_without_browser_fix_skips_provider(self):
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_reverse_geocode",
            new=AsyncMock(),
        ) as provider:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="current-location-unavailable",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=None,
            )
            tool = next(item for item in tools if item.name == "get_current_location")
            result = json.loads(await tool.ainvoke({}))

        provider.assert_not_awaited()
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["id"], "manual_location")
        self.assertEqual(result["clarification"]["fields"][0]["type"], "text")

    async def test_nearby_current_location_without_browser_fix_never_searches_provider(self):
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(),
        ) as place_search, patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
            new=AsyncMock(),
        ) as nearby_search:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="nearby-browser-location-missing",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=None,
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "",
                "query": "好玩的地方",
                "use_current_location_as_anchor": True,
            }))

        place_search.assert_not_awaited()
        nearby_search.assert_not_awaited()
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["id"], "nearby_anchor")

    async def test_nearby_recommendation_keeps_successful_alternative_anchor(self):
        samsung = {
            **PLACE,
            "place_id": "samsung-tower",
            "name": "北京三星大厦",
            "address": "北京市朝阳区景辉街31号院1号楼",
            "latitude": 39.913,
            "longitude": 116.456,
        }
        guomao = {
            **PLACE,
            "place_id": "guomao-tower",
            "name": "北京国贸大厦",
            "address": "北京市朝阳区建国门外大街1号",
            "latitude": 39.909,
            "longitude": 116.459,
        }
        restaurant = {
            **PLACE,
            "place_id": "restaurant-samsung",
            "name": "三星大厦附近餐厅",
            "address": "北京市朝阳区景辉街",
            "latitude": 39.914,
            "longitude": 116.455,
            "distance_to_anchor_meters": 260.0,
        }

        async def anchor_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 5)
            return [samsung] if "三星" in query else [guomao]

        async def nearby_provider(
            _key, query, anchor, *, radius_meters, limit,
        ):
            self.assertEqual(query, "适合生日聚餐的餐厅")
            self.assertEqual(radius_meters, 2_000)
            return [restaurant] if anchor["place_id"] == "samsung-tower" else []

        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(side_effect=anchor_provider),
        ) as anchor_lookup, patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
            new=AsyncMock(side_effect=nearby_provider),
        ) as nearby_lookup:
            tools = build_system_skill_tools(
                None,
                store=FakeStore(),
                conversation_id="alternative-nearby-restaurants",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "北京三星大厦",
                "anchor_queries": ["北京三星大厦", "北京国贸大厦"],
                "query": "适合生日聚餐的餐厅",
                "city": "北京",
                "limit": 5,
                "title": "三星大厦或国贸大厦附近餐厅",
                "action_text": "查看附近餐厅",
            }))

        self.assertEqual(anchor_lookup.await_count, 2)
        self.assertEqual(nearby_lookup.await_count, 2)
        self.assertEqual(result["verified_place_count"], 1)
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(
            result["action"]["payload"]["places"][0]["nearby_anchor_name"],
            "北京三星大厦",
        )
        self.assertEqual(
            [place["place_id"] for place in result["action"]["payload"]["places"]],
            ["restaurant-samsung"],
        )

    async def test_nearby_recommendation_respects_user_explicit_strict_radius(self):
        anchor = {
            **PLACE,
            "place_id": "hotel",
            "name": "桔子酒店(北京中关村软件园店)",
        }
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][anchor["place_id"]] = anchor
        await save_user_workspace(store, state, TEST_USER_ID)
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places_nearby",
            new=AsyncMock(return_value=[]),
        ) as nearby_provider:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="strict-nearby",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            with self.assertRaisesRegex(ValueError, "500 米内"):
                await tool.ainvoke({
                    "anchor_query": anchor["name"],
                    "query": "早餐店",
                    "radius_meters": 500,
                    "strict_radius": True,
                })
        self.assertEqual(nearby_provider.await_args.kwargs["radius_meters"], 500)

    def test_complete_planner_route_preserves_literal_user_place_text(self):
        self.assertEqual(
            preserve_planned_route_stops(
                [("腾讯北京总部大楼", ""), ("北京站", "")],
                [{"query": "腾讯总部"}, {"query": "北京站"}],
            ),
            [("腾讯总部", ""), ("北京站", "")],
        )

    def test_resume_protocol_applies_selected_nearby_anchor_by_stable_field_id(self):
        _plan, arguments = resume_capability_protocol(
            {"needs_route": False},
            {
                "version": "1",
                "required_tools": ["plan_route_between_places"],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "origin_query": "北京站",
                        "destination_query": "锦江之星",
                        "destination_near_query": "万达广场",
                    },
                },
            },
            [{
                "id": "route_destination_anchor",
                "value": "floris-place:wanda-cbd",
            }],
        )
        route = arguments["plan_route_between_places"]
        self.assertEqual(route["destination_query"], "锦江之星")
        self.assertEqual(
            route["destination_near_query"],
            "floris-place:wanda-cbd",
        )

    def test_tencent_polyline_delta_decode(self):
        path = decode_polyline([39.9, 116.3, 100000, 200000])
        self.assertAlmostEqual(path[1]["latitude"], 40.0)
        self.assertAlmostEqual(path[1]["longitude"], 116.5)

    def test_place_distance_supports_nearby_boundary_validation(self):
        origin = {"latitude": 39.9, "longitude": 116.3}
        close = {"latitude": 39.901, "longitude": 116.301}
        far = {"latitude": 40.1, "longitude": 116.5}
        self.assertLess(place_distance_meters(origin, close), 500)
        self.assertGreater(place_distance_meters(origin, far), 20_000)

    async def test_nearby_place_search_uses_anchor_boundary_and_filters_outside_radius(self):
        anchor = {
            **PLACE,
            "place_id": "hospital",
            "name": "北京301医院",
            "latitude": 39.902,
            "longitude": 116.276,
        }
        response = {"data": [
            {
                "id": "near",
                "title": "锦江之星(五棵松店)",
                "address": "北京市海淀区",
                "location": {"lat": 39.906, "lng": 116.271},
                "ad_info": {"city": "北京市"},
            },
            {
                "id": "far",
                "title": "锦江之星(远郊店)",
                "address": "北京市远郊区",
                "location": {"lat": 40.2, "lng": 116.7},
                "ad_info": {"city": "北京市"},
            },
        ]}
        with patch(
            "agents._infrastructure.providers.tencent_location._get",
            new=AsyncMock(return_value=response),
        ) as request:
            places = await search_verified_places_nearby(
                "map-key", "锦江之星酒店", anchor, radius_meters=5_000,
            )
        self.assertEqual([item["place_id"] for item in places], ["near"])
        params = request.await_args.args[1]
        self.assertEqual(params["keyword"], "锦江之星酒店")
        self.assertTrue(params["boundary"].startswith("nearby(39.902,116.276,5000"))
        self.assertEqual(params["orderby"], "_distance")

    async def test_nearby_category_search_accepts_provider_ranked_brand_names(self):
        anchor = {
            **PLACE,
            "place_id": "hotel",
            "name": "桔子酒店(北京中关村软件园店)",
            "latitude": 40.042246,
            "longitude": 116.255289,
        }
        response = {"data": [{
            "id": "breakfast",
            "title": "庆丰包子铺(软件园店)",
            "address": "北京市海淀区软件园路",
            "location": {"lat": 40.0419, "lng": 116.257},
            "ad_info": {"city": "北京市"},
        }]}
        with patch(
            "agents._infrastructure.providers.tencent_location._get",
            new=AsyncMock(return_value=response),
        ):
            places = await search_verified_places_nearby(
                "map-key",
                "早餐店",
                anchor,
                radius_meters=2_000,
            )
        self.assertEqual([item["place_id"] for item in places], ["breakfast"])
        self.assertGreater(places[0]["distance_to_anchor_meters"], 0)

    async def test_place_search_falls_back_when_primary_results_do_not_match_query(self):
        target = {**PLACE, "place_id": "osm:lake", "name": "查干湖", "provider": "openstreetmap"}
        with patch("agents._infrastructure.providers.tencent_location.search_places", new=AsyncMock(return_value=[PLACE])), \
             patch("agents._infrastructure.providers.tencent_location.search_place_suggestions", new=AsyncMock(return_value=[])), \
             patch("agents._infrastructure.providers.tencent_location.search_osm_places", new=AsyncMock(return_value=[target])) as fallback:
            places = await search_verified_places("map-key", "查干湖")
        self.assertEqual(places[0]["name"], "查干湖")
        fallback.assert_awaited_once()

    async def test_place_search_uses_provider_suggestion_for_descriptive_query(self):
        primary = {
            **PLACE,
            "place_id": "tencent:trb-hutong",
            "name": "TRB Hutong",
            "address": "北京市东城区沙滩北街23号",
        }
        with patch("agents._infrastructure.providers.tencent_location.search_places", new=AsyncMock(return_value=[primary])), \
             patch("agents._infrastructure.providers.tencent_location.search_place_suggestions", new=AsyncMock(return_value=[primary])), \
             patch("agents._infrastructure.providers.tencent_location.search_osm_places", new=AsyncMock(return_value=[])) as fallback:
            places = await search_verified_places("map-key", "TRB Hutong北京胡同创意西餐厅", city="北京")
        self.assertEqual(places[0]["place_id"], "tencent:trb-hutong")
        fallback.assert_not_awaited()

    async def test_place_search_preserves_ambiguous_provider_candidates(self):
        generic = {
            **PLACE,
            "place_id": "tencent:sanlitun-area",
            "name": "三里屯",
            "address": "北京市朝阳区三里屯街道",
        }
        restaurant = {
            **PLACE,
            "place_id": "tencent:bottega",
            "name": "BOTTEGA意库(三里屯店)",
            "address": "北京市朝阳区三里屯路19号",
        }
        with patch(
            "agents._infrastructure.providers.tencent_location.search_places",
            new=AsyncMock(return_value=[generic, restaurant]),
        ), patch(
            "agents._infrastructure.providers.tencent_location.search_place_suggestions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents._infrastructure.providers.tencent_location.search_osm_places",
            new=AsyncMock(return_value=[]),
        ) as fallback:
            places = await search_verified_places("map-key", "BOTTEGA意库三里屯", city="北京")
        self.assertEqual(
            [item["place_id"] for item in places],
            ["tencent:sanlitun-area", "tencent:bottega"],
        )
        fallback.assert_not_awaited()

    async def test_place_search_never_substitutes_generic_area_for_missing_restaurant(self):
        generic = {
            **PLACE,
            "place_id": "tencent:sanlitun-area",
            "name": "三里屯",
            "address": "北京市朝阳区三里屯商圈",
            "category": "地名地址:行政地名",
        }
        with patch(
            "agents._infrastructure.providers.tencent_location.search_places",
            new=AsyncMock(return_value=[generic]),
        ), patch(
            "agents._infrastructure.providers.tencent_location.search_place_suggestions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents._infrastructure.providers.tencent_location.search_osm_places",
            new=AsyncMock(return_value=[]),
        ) as fallback:
            places = await search_verified_places("map-key", "BOTTEGA意库三里屯", city="北京")
        self.assertEqual(places, [])
        fallback.assert_awaited_once()

    def test_nearby_tool_failure_fallback_is_user_facing(self):
        result = tool_failure_fallback([
            HumanMessage(content="三星大厦或者国贸大厦附近有餐厅吗"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "没有在两个参照地点附近 2000 米内核实到餐厅",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                tool_call_id="nearby-1",
                name="recommend_nearby_places_on_map",
            ),
        ])
        self.assertIn("地点服务这次没有找到", result)
        self.assertNotIn("确认卡", result)

    def test_missing_browser_location_failure_fallback_never_claims_search(self):
        result = tool_failure_fallback([
            HumanMessage(content="帮我看看我附近有什么好玩的"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "本轮没有收到浏览器定位坐标，不能搜索当前位置附近",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                tool_call_id="nearby-location-missing",
                name="recommend_nearby_places_on_map",
            ),
        ])
        self.assertIn("没有收到浏览器定位坐标", result)
        self.assertIn("地点服务", result)
        self.assertNotIn("已授权", result)

    def test_current_location_result_has_truthful_terminal_fallback(self):
        content = tool_result_fallback([
            HumanMessage(content="我现在在哪"),
            ToolMessage(
                content=json.dumps({
                    "location_available": True,
                    "location": {
                        "address": "吉林省长春市朝阳区前进大街2699号",
                        "city": "长春市",
                        "district": "朝阳区",
                        "nearby_landmark": "吉林大学前卫南区",
                    },
                }, ensure_ascii=False),
                name="get_current_location",
                tool_call_id="location-1",
            ),
        ])
        self.assertIn("前进大街2699号", content)
        self.assertIn("吉林大学前卫南区", content)
        self.assertNotIn("经纬度", content)

    async def test_tencent_reverse_geocode_uses_wgs84_and_sanitizes_result(self):
        response = {
            "status": 0,
            "result": {
                "address": "吉林省长春市朝阳区前进大街2699号",
                "formatted_addresses": {"recommend": "朝阳区前进大街2699号"},
                "address_component": {
                    "province": "吉林省",
                    "city": "长春市",
                    "district": "朝阳区",
                    "street": "前进大街",
                    "street_number": "2699号",
                },
                "pois": [{
                    "title": "吉林大学前卫南区",
                    "address": "前进大街2699号",
                    "location": {"lat": 43.817, "lng": 125.324},
                }],
            },
        }
        with patch(
            "agents._infrastructure.providers.tencent_location._get",
            new=AsyncMock(return_value=response),
        ) as provider:
            result = await reverse_geocode("map-key", {
                "latitude": 43.8171,
                "longitude": 125.3235,
                "coordinate_type": "wgs84",
            })

        self.assertTrue(provider.await_args.args[0].endswith("/geocoder/v1"))
        self.assertEqual(provider.await_args.args[1]["coord_type"], 1)
        self.assertEqual(result["city"], "长春市")
        self.assertEqual(result["nearby_landmark"], "吉林大学前卫南区（前进大街2699号）")
        self.assertNotIn("latitude", result)

