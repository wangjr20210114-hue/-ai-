from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents._infrastructure.makers.route_repository import save_route_cache
from agents._application.workspace.service import load_user_workspace


class RouteDialogueTransitTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_route_enriches_missing_cities_through_tencent_adapter(self):
        origin = {
            **PLACE,
            "place_id": "origin",
            "name": "Origin",
            "city": "",
            "latitude": 31.2,
            "longitude": 121.3,
        }
        destination = {
            **PLACE,
            "place_id": "destination",
            "name": "Destination",
            "city": "",
            "latitude": 30.3,
            "longitude": 120.2,
        }
        cached_route = {
            "schema_version": 4,
            "provider": "tencent",
            "mode": "transit",
            "places": [origin, destination],
            "path": [],
            "legs": [{
                "from": origin,
                "to": destination,
                "mode": "transit",
                "path": [],
                "sections": [{"mode": "rail", "vehicle": "RAIL"}],
                "distance_meters": 100_000,
                "duration_seconds": 3_600,
            }],
            "distance_meters": 100_000,
            "duration_seconds": 3_600,
            "fare": {},
            "transit": {"segments": [{"vehicle": "RAIL"}]},
        }
        store = FakeStore()
        await save_route_cache(
            store,
            TEST_USER_ID,
            [origin, destination],
            False,
            cached_route,
            mode="transit",
            strategy="time_then_cost",
            near_time_tolerance_minutes=10,
        )

        async def place_provider(_key, query, *, city, limit):
            return [origin] if query == "Origin" else [destination]

        reverse_provider = AsyncMock(side_effect=[
            {"city": "City One", "address": "Origin address"},
            {"city": "City Two", "address": "Destination address"},
        ])
        route_provider = AsyncMock()
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="cached-route-city-enrichment",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        route_tool = next(
            item for item in tools
            if item.name == "plan_route_between_places"
        )
        with (
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_search_places",
                new=place_provider,
            ),
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_reverse_geocode",
                new=reverse_provider,
            ),
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_plan_route",
                new=route_provider,
            ),
        ):
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "Origin",
                "destination_query": "Destination",
                "route_mode": "transit",
            }))

        route_provider.assert_not_awaited()
        self.assertEqual(reverse_provider.await_count, 2)
        action_id = result["action"]["id"]
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        route = saved["actions"][action_id]["payload"]["route"]
        self.assertEqual(route["legs"][0]["scope"], "intercity")
        self.assertEqual(route["transit"]["modes"], ["rail"])

    async def test_exact_bare_name_among_multiple_tencent_branches_requires_choice(self):
        station = {
            **PLACE,
            "place_id": "poi-station",
            "name": "北京站",
        }
        wanda_cbd = {
            **PLACE,
            "place_id": "poi-wanda-cbd",
            "name": "万达广场",
            "address": "北京市朝阳区建国路93号",
        }
        wanda_fengtai = {
            **PLACE,
            "place_id": "poi-wanda-fengtai",
            "name": "万达广场(丰台店)",
            "address": "北京市丰台区",
        }

        async def place_provider(_key, query, *, city, limit):
            if query == "北京站":
                return [station]
            return [wanda_cbd, wanda_fengtai]

        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="route-branch-choice",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        route_tool = next(
            item for item in tools
            if item.name == "plan_route_between_places"
        )
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=place_provider,
        ):
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "万达广场",
                "city": "北京",
                "route_mode": "transit",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["type"], "single")
        self.assertEqual(len(field["options"]), 2)

    async def test_primary_tencent_stage_allows_adapter_retry_budget(self):
        place = {**PLACE, "name": "王府井", "place_id": "poi-wangfujing"}
        observed_timeouts = []
        real_wait_for = asyncio.wait_for

        async def capture_wait_for(awaitable, timeout):
            observed_timeouts.append(timeout)
            return await real_wait_for(awaitable, timeout=timeout)

        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[place]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.asyncio.wait_for",
                side_effect=capture_wait_for,
            ),
        ):
            places = await search_verified_places_bounded(
                "key", "王府井", city="北京", limit=3, timeout_seconds=30,
            )

        self.assertEqual([item["place_id"] for item in places], ["poi-wangfujing"])
        self.assertEqual(observed_timeouts[0], 17.0)

    async def test_calendar_place_lookup_enforces_choice_and_fill_cards(self):
        tools = build_system_skill_tools(
            object(),
            store=FakeStore(),
            conversation_id="calendar-place-resolution",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_KEY": "key"},
            enabled_skills={"maps", "calendar"},
            planned_calendar_place_resolution=True,
        )
        search_tool = next(tool for tool in tools if tool.name == "search_places")
        matches = [
            PLACE,
            {**PLACE, "place_id": "poi-gugong-north", "address": "北门"},
        ]
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            AsyncMock(return_value=matches),
        ):
            choice = json.loads(await search_tool.ainvoke({
                "query": "故宫博物院",
                "city": "北京",
            }))
        self.assertEqual(choice["ui_action"], "clarification_action")
        self.assertEqual(choice["clarification"]["fields"][0]["type"], "single")
        self.assertEqual(len(choice["clarification"]["fields"][0]["options"]), 2)

        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            AsyncMock(return_value=[]),
        ):
            fill = json.loads(await search_tool.ainvoke({
                "query": "完全未知地点",
                "city": "全国",
            }))
        self.assertEqual(fill["ui_action"], "clarification_action")
        self.assertEqual(fill["clarification"]["fields"][0]["type"], "text")

    async def test_calendar_multiple_candidates_are_shown_in_ranked_choice_card(self):
        entrance = {
            **PLACE,
            "place_id": "poi-gugong-entrance",
            "name": "故宫博物院-午门",
            "address": "北京市东城区景山前街4号",
        }
        tools = build_system_skill_tools(
            object(),
            store=FakeStore(),
            conversation_id="calendar-semantic-landmark",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_KEY": "key"},
            enabled_skills={"maps", "calendar"},
            planned_calendar_place_resolution=True,
        )
        search_tool = next(tool for tool in tools if tool.name == "search_places")
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            AsyncMock(return_value=[PLACE, entrance]),
        ):
            result = json.loads(await search_tool.ainvoke({
                "query": "故宫博物院",
                "city": "北京",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["type"], "single")
        self.assertGreaterEqual(len(field["options"]), 2)

    async def test_calendar_unique_verified_correction_skips_extra_question(self):
        corrected = {
            **PLACE,
            "name": "天安门",
            "place_id": "poi-tiananmen",
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门",
                "confidence": 0.95,
                "evidence": "tencent_place_suggestion",
            },
        }
        tools = build_system_skill_tools(
            object(),
            store=FakeStore(),
            conversation_id="calendar-unique-correction",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_KEY": "key"},
            enabled_skills={"maps", "calendar"},
            planned_calendar_place_resolution=True,
        )
        search_tool = next(tool for tool in tools if tool.name == "search_places")
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            AsyncMock(return_value=[corrected]),
        ):
            result = json.loads(await search_tool.ainvoke({
                "query": "天安们",
                "city": "北京",
            }))
        self.assertEqual(result["resolution"]["decision"], "auto_use")
        self.assertEqual(
            result["resolution"]["selected_place_id"],
            "poi-tiananmen",
        )

    async def test_cached_route_keeps_current_tencent_typo_evidence(self):
        station = {
            **PLACE,
            "place_id": "poi-station",
            "name": "北京站",
            "address": "北京市东城区",
        }
        corrected = {
            **PLACE,
            "place_id": "poi-tiananmen",
            "name": "天安门",
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门",
                "confidence": 0.95,
                "evidence": "tencent_place_suggestion",
            },
        }

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else [corrected]

        # Provider/cache-normalized places do not carry the current query's
        # spelling evidence. The tool must merge it back before finalizing.
        route = {
            "provider": "tencent",
            "mode": "walking",
            "places": [
                {key: value for key, value in station.items() if key != "query_correction"},
                {key: value for key, value in corrected.items() if key != "query_correction"},
            ],
            "distance_meters": 4_100,
            "duration_seconds": 3_720,
            "fare": {},
        }
        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="route-typo-cache",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        route_tool = next(
            item for item in tools
            if item.name == "plan_route_between_places"
        )
        with (
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_search_places",
                new=place_provider,
            ),
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_plan_route",
                new=AsyncMock(return_value=route),
            ),
        ):
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "天安们",
                "city": "北京",
                "route_mode": "walking",
            }))
        self.assertEqual(
            result["ordered_stops"][1]["query_correction"]["original_query"],
            "天安们",
        )
        self.assertEqual(
            result["ordered_stops"][1]["query_correction"]["evidence"],
            "tencent_place_suggestion",
        )

    async def test_cached_route_drops_correction_for_current_exact_query(self):
        station = {
            **PLACE,
            "place_id": "poi-station",
            "name": "北京站",
        }
        destination = {
            **PLACE,
            "place_id": "poi-tiananmen",
            "name": "天安门",
        }
        stale_destination = {
            **destination,
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门",
                "confidence": 0.95,
                "evidence": "tencent_place_suggestion",
            },
        }

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else [destination]

        route = {
            "provider": "tencent",
            "mode": "transit",
            "places": [station, stale_destination],
            "distance_meters": 4_500,
            "duration_seconds": 2_100,
            "fare": {},
        }
        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="route-exact-cache",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        route_tool = next(
            item for item in tools
            if item.name == "plan_route_between_places"
        )
        with (
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_search_places",
                new=place_provider,
            ),
            patch(
                "agents._infrastructure.skills.builtin_operations.provider_plan_route",
                new=AsyncMock(return_value=route),
            ),
        ):
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "天安门",
                "city": "北京",
                "route_mode": "transit",
            }))
        self.assertNotIn(
            "query_correction",
            result["ordered_stops"][1],
        )

    async def test_transit_contract_decodes_path_fare_and_walking_transfer(self):
        browser = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 39.9,
            "longitude": 116.3,
            "coordinate_type": "wgs84",
        }

        async def provider(url, params):
            if url.endswith("/coord/v1/translate"):
                return {"status": 0, "locations": [{"lat": 39.901, "lng": 116.301}]}
            self.assertTrue(url.endswith("/direction/v1/transit/"))
            return {
                "status": 0,
                "result": {"routes": [{
                    "distance": 10_000,
                    "duration": 45,
                    "steps": [
                        {
                            "mode": "WALKING",
                            "distance": 500,
                            "polyline": [39.901, 116.301, 100, 100],
                        },
                        {
                            "mode": "TRANSIT",
                            "lines": [{
                                "vehicle": "SUBWAY",
                                "title": "地铁1号线",
                                "price": 300,
                                "station_count": 6,
                                "geton": {"title": "起点站"},
                                "getoff": {"title": "终点站"},
                                "polyline": [39.902, 116.302, 100, 100],
                            }],
                        },
                    ],
                }]},
            }

        with patch("agents._infrastructure.providers.tencent_location._get", side_effect=provider):
            route = await plan_verified_route(
                "key", [browser, PLACE], mode="transit",
            )
        self.assertEqual(route["mode"], "transit")
        self.assertEqual(route["duration_seconds"], 45 * 60)
        self.assertEqual(route["fare"]["transit"]["estimate"], 3)
        self.assertEqual(route["transit"]["walking_distance_meters"], 500)
        self.assertEqual(route["transit"]["lines"], ["地铁1号线"])
        self.assertEqual(
            [section["mode"] for section in route["legs"][0]["sections"]],
            ["walking", "rail"],
        )
        self.assertEqual(route["legs"][0]["sections"][1]["line"], "地铁1号线")
        self.assertEqual(route["places"][0]["coordinate_type"], "gcj02")
        self.assertGreaterEqual(len(route["path"]), 2)

    async def test_time_then_cost_uses_cheapest_tencent_candidate_within_tolerance(self):
        destination = {**PLACE, "place_id": "other", "latitude": 39.8}
        seen_params = {}

        async def provider(url, params):
            seen_params.update(params)
            return {
                "status": 0,
                "result": {"routes": [
                    {
                        "distance": 20_000,
                        "duration": 30,
                        "toll": 20,
                        "polyline": [39.9, 116.3, 100, 100],
                    },
                    {
                        "distance": 18_000,
                        "duration": 35,
                        "toll": 0,
                        "polyline": [39.9, 116.3, 100, 100],
                    },
                    {
                        "distance": 8_000,
                        "duration": 50,
                        "toll": 0,
                        "polyline": [39.9, 116.3, 100, 100],
                    },
                ]},
            }

        with patch("agents._infrastructure.providers.tencent_location._get", side_effect=provider):
            route = await plan_verified_route(
                "key",
                [PLACE, destination],
                mode="driving",
                strategy="time_then_cost",
                near_time_tolerance_minutes=10,
            )
        self.assertEqual(route["duration_seconds"], 35 * 60)
        self.assertEqual(route["selection"]["candidate_count"], 3)
        self.assertEqual(route["selection"]["fastest_duration_seconds"], 30 * 60)
        self.assertEqual(seen_params["policy"], "LEAST_TIME")
        self.assertEqual(seen_params["get_mp"], 1)

    async def test_least_cost_asks_tencent_to_avoid_fees(self):
        destination = {**PLACE, "place_id": "other", "latitude": 39.8}
        seen_params = {}

        async def provider(url, params):
            seen_params.update(params)
            return {
                "status": 0,
                "result": {"routes": [{
                    "distance": 10_000,
                    "duration": 20,
                    "toll": 0,
                    "polyline": [39.9, 116.3, 100, 100],
                }]},
            }

        with patch("agents._infrastructure.providers.tencent_location._get", side_effect=provider):
            await plan_verified_route(
                "key", [PLACE, destination], strategy="least_cost",
            )
        self.assertEqual(seen_params["policy"], "LEAST_TIME,LEAST_FEE")

    def test_cache_separates_each_travel_mode(self):
        places = [PLACE, {**PLACE, "place_id": "other", "latitude": 39.8}]
        self.assertNotEqual(
            route_cache_key(places, False, "driving"),
            route_cache_key(places, False, "walking"),
        )
        self.assertNotEqual(
            route_cache_key(places, False, "driving", "least_time", 10),
            route_cache_key(places, False, "driving", "time_then_cost", 10),
        )


if __name__ == "__main__":
    unittest.main()
