from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class MapPlaceProviderBoundaryTests(unittest.IsolatedAsyncioTestCase):
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
        await save_user_workspace(store, state, user_id=TEST_USER_ID)
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
