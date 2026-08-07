from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents._application.chat.turn_policy import (
    route_calendar_tool_arguments,
    route_tool_arguments_for_plan,
)
from agents._domain.maps.route_chain import (
    current_route_plan,
    record_route_plan,
    route_plan_by_id,
)
from agents._application.workspace.service import load_user_workspace
from agents._domain.maps.route_order import optimize_open_route_order
from agents._infrastructure.makers.route_repository import route_cache_key
from agents._infrastructure.providers.tencent_location import (
    optimize_place_order,
    plan_route,
)
from agents._infrastructure.skills.place_operations import PlaceOperations
from agents.chat._calendar_context import latest_route_context


class RoutePolicyTests(unittest.TestCase):
    def test_unordered_recommendations_use_one_trusted_route_component(self):
        plan = parse_capability_plan({
            "needs_route": True,
            "needs_places": True,
            "needs_map_action": True,
            "route_order_policy": "optimize",
            "route_mode": "transit",
            "route_strategy": "least_cost",
            "route_stops": [],
            "capabilities": ["route", "map_action", "places"],
        })
        self.assertEqual(plan["route_order_policy"], "optimize")
        self.assertEqual(
            required_tools_for_plan(plan),
            ("recommend_places_on_map",),
        )

    def test_explicit_route_order_cannot_be_optimized_implicitly(self):
        plan = parse_capability_plan({
            "needs_route": True,
            "route_order_policy": "preserve",
            "capabilities": ["route", "map_action", "places"],
            "route_stops": [
                {"query": "起点"},
                {"query": "中途地点"},
                {"query": "终点"},
            ],
        })
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places",),
        )

    def test_unordered_route_uses_provider_time_or_cost_objective(self):
        distances = (
            (0, 1, 10),
            (1, 0, 1),
            (10, 1, 0),
        )
        durations = (
            (0, 10, 1),
            (10, 0, 1),
            (1, 1, 0),
        )
        self.assertEqual(
            optimize_open_route_order(
                distances, durations, strategy="least_cost",
            ),
            (0, 1, 2),
        )
        self.assertEqual(
            optimize_open_route_order(
                distances, durations, strategy="least_time",
            ),
            (0, 2, 1),
        )

    def test_invalid_provider_matrix_preserves_recommendation_order(self):
        self.assertEqual(
            optimize_open_route_order(
                ((0, 1), (1, 0)),
                ((0,), (1, 0)),
            ),
            (0, 1),
        )

    def test_optimized_route_cache_treats_recommendations_as_a_set(self):
        places = [
            {"place_id": "a", "latitude": 30.1, "longitude": 120.1},
            {"place_id": "b", "latitude": 30.2, "longitude": 120.2},
            {"place_id": "c", "latitude": 30.3, "longitude": 120.3},
        ]
        self.assertEqual(
            route_cache_key(places, True),
            route_cache_key(list(reversed(places)), True),
        )
        self.assertNotEqual(
            route_cache_key(places, False),
            route_cache_key(list(reversed(places)), False),
        )

    def test_route_chain_is_scoped_and_versioned_per_conversation(self):
        state = {"route_chains": {}, "route_chain_index": {}, "latest_route_plan": {}}
        first = record_route_plan(state, "chat-a", {"id": "plan-a1"}, now=1)
        second = record_route_plan(state, "chat-a", {"id": "plan-a2"}, now=2)
        record_route_plan(state, "chat-b", {"id": "plan-b1"}, now=3)
        self.assertEqual(first["route_chain_revision"], 1)
        self.assertEqual(second["previous_route_plan_id"], "plan-a1")
        self.assertEqual(current_route_plan(state, "chat-a")["id"], "plan-a2")
        self.assertEqual(current_route_plan(state, "chat-b")["id"], "plan-b1")
        self.assertEqual(current_route_plan(state, "chat-c"), {})
        self.assertEqual(route_plan_by_id(state, "chat-a", "plan-a1")["id"], "plan-a1")
        self.assertEqual(route_plan_by_id(state, "chat-b", "plan-a1"), {})

    def test_route_arguments_preserve_user_order_and_current_origin(self):
        arguments = route_tool_arguments_for_plan({
            "needs_route": True,
            "route_uses_current_location": True,
            "route_stops": [{"query": "目的地", "near_query": ""}],
        })
        self.assertEqual(arguments["destination_query"], "目的地")
        self.assertTrue(arguments["use_current_location_as_origin"])

    def test_linked_route_calendar_seeds_adapter_owned_arguments(self):
        arguments = route_calendar_tool_arguments({
            "needs_calendar_action": True,
            "calendar_uses_planned_route": True,
        }, "去接朋友并写入日程")
        self.assertEqual(arguments["changes"], [])
        self.assertEqual(arguments["summary"], "去接朋友并写入日程")

    def test_new_route_calendar_plan_preserves_both_required_tools(self):
        plan = parse_capability_plan({
            "needs_route": True,
            "needs_calendar_action": True,
            "calendar_uses_planned_route": True,
            "route_uses_current_location": True,
            "route_stops": [{"query": "目的地", "near_query": ""}],
        })
        self.assertTrue(plan["calendar_uses_planned_route"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places", "propose_calendar_changes"),
        )

    def test_route_provider_ambiguity_cannot_become_generic_clarification(self):
        plan = parse_capability_plan({
            "needs_clarification": True,
            "clarification_title": "先问城市",
            "clarification_prompt": "城市不明确",
            "clarification_fields": [{
                "id": "city", "label": "城市", "type": "text",
            }],
            "place_resolution_target": "route",
            "needs_route": True,
            "route_stops": [{"query": "某品牌门店", "near_query": ""}],
        })
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_route"])

    def test_latest_route_continuation_binds_verified_endpoint_and_city(self):
        plan, arguments = bind_latest_route_continuation(
            {
                "needs_route": True,
                "route_continues_latest": True,
                "route_city": "全国",
                "route_stops": [{"query": "下一处地点", "near_query": ""}],
            },
            {
                "city": "全国",
                "ordered_stops": [{"query": "下一处地点", "near_query": ""}],
            },
            {
                "latest_route_plan": {
                    "id": "routeplan-latest",
                    "ordered_stops": [
                        {"place_id": "origin", "name": "起点", "city": "示例市"},
                        {"place_id": "terminal", "name": "上一段终点", "city": "示例市"},
                    ],
                },
            },
        )
        self.assertEqual(plan["route_city"], "示例市")
        self.assertTrue(plan["route_origin_is_departure"])
        self.assertEqual(
            arguments["ordered_stops"][0]["query"],
            "floris-place:terminal",
        )
        self.assertEqual(arguments["ordered_stops"][1]["query"], "下一处地点")

    def test_generic_continuation_language_binds_without_model_flag(self):
        plan, arguments = bind_latest_route_continuation(
            {
                "needs_route": True,
                "route_continues_latest": False,
                "route_city": "全国",
                "route_stops": [{"query": "某品牌门店", "near_query": ""}],
            },
            {
                "city": "全国",
                "ordered_stops": [{"query": "某品牌门店", "near_query": ""}],
            },
            {"latest_route_plan": {"id": "routeplan-latest", "ordered_stops": [
                {"place_id": "terminal", "name": "上一段终点", "city": "示例市"},
            ]}},
            "接完朋友后再去下一站",
        )
        self.assertEqual(plan["route_city"], "示例市")
        self.assertEqual(
            [item["query"] for item in arguments["ordered_stops"]],
            ["floris-place:terminal", "某品牌门店"],
        )

    def test_latest_route_context_exposes_provider_city_without_coordinates(self):
        context = json.loads(latest_route_context({
            "latest_route_plan": {
                "id": "routeplan-city",
                "ordered_stops": [
                    {"place_id": "a", "name": "A", "city": "示例市"},
                    {"place_id": "b", "name": "B", "city": "示例市"},
                ],
            },
        }))
        self.assertEqual(context["ordered_stops"][-1]["city"], "示例市")
        self.assertNotIn("latitude", context["ordered_stops"][-1])

    def test_provider_choice_card_allows_a_manual_place_without_another_question(self):
        field = _place_choice_field(
            "route_destination",
            "选择具体终点",
            [PLACE, {**PLACE, "place_id": "another", "name": "另一分店"}],
        )
        self.assertTrue(field["allow_custom_input"])
        self.assertTrue(field["custom_placeholder"])


class RouteModelBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_transit_leg_uses_strategy_aware_provider_fallback(self):
        places = [
            {**PLACE, "place_id": "a", "name": "A"},
            {**PLACE, "place_id": "b", "name": "B", "longitude": 116.4},
            {**PLACE, "place_id": "c", "name": "C", "longitude": 116.5},
        ]

        async def route_leg(_key, origin, destination, *, mode, **_kwargs):
            if origin["place_id"] == "b" and mode == "transit":
                raise RuntimeError("no transit candidate")
            return {
                "path": [
                    {
                        "latitude": origin["latitude"],
                        "longitude": origin["longitude"],
                    },
                    {
                        "latitude": destination["latitude"],
                        "longitude": destination["longitude"],
                    },
                ],
                "sections": [{
                    "mode": mode,
                    "path": [],
                    "distance_meters": 1_000,
                    "duration_seconds": 600,
                }],
                "distance_meters": 1_000,
                "duration_seconds": 600,
                "fare": {"currency": "CNY", "basis": "provider"},
                "selection": {},
            }

        with patch(
            "agents._infrastructure.providers.tencent_location._plan_route_leg",
            new=route_leg,
        ):
            route = await plan_route(
                "map-key",
                places,
                mode="transit",
                strategy="least_cost",
            )

        self.assertEqual(
            [leg["mode"] for leg in route["legs"]],
            ["transit", "bicycling"],
        )
        self.assertFalse(route["legs"][0]["selection"]["mode_fallback"])
        self.assertTrue(route["legs"][1]["selection"]["mode_fallback"])
        self.assertEqual(
            route["legs"][1]["selection"]["requested_mode"],
            "transit",
        )

    async def test_transit_fallback_reaches_tencent_driving_as_last_resort(self):
        places = [
            {**PLACE, "place_id": "a", "name": "A"},
            {**PLACE, "place_id": "b", "name": "B", "longitude": 116.4},
        ]

        async def route_leg(_key, origin, destination, *, mode, **_kwargs):
            if mode in {"transit", "bicycling"}:
                raise RuntimeError(f"no {mode} candidate")
            return {
                "path": [],
                "sections": [{
                    "mode": mode,
                    "path": [],
                    "distance_meters": 1_000,
                    "duration_seconds": 600,
                }],
                "distance_meters": 1_000,
                "duration_seconds": 600,
                "selection": {},
            }

        with patch(
            "agents._infrastructure.providers.tencent_location._plan_route_leg",
            new=route_leg,
        ):
            route = await plan_route(
                "map-key",
                places,
                mode="transit",
                strategy="least_cost",
            )

        self.assertEqual(route["legs"][0]["mode"], "driving")
        self.assertTrue(route["legs"][0]["selection"]["mode_fallback"])

    async def test_verified_recommendations_are_handed_to_route_component(self):
        captured: dict[str, object] = {}

        async def search_places(_map_key, query, *, city, limit):
            return [{
                **PLACE,
                "place_id": f"poi-{query}",
                "name": query,
                "city": city,
            }]

        async def recommended_route_planner(**kwargs):
            captured.update(kwargs)
            return json.dumps({
                "ui_action": "map_action",
                "action": {"payload": {}},
                "response_constraint": "route constraint",
            })

        async def load_state():
            return {}

        async def save_state(state):
            return state

        map_runtime = MagicMock()
        map_runtime.search_places = search_places
        operations = PlaceOperations(
            runtime_env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            conversation_id="verified-handoff",
            browser_current_location=None,
            map_runtime=map_runtime,
            load_state=load_state,
            save_state=save_state,
            place_disambiguation_model=None,
            planned_calendar_place_resolution=False,
            provider_place_review_enabled=False,
            place_result_limit=6,
            route_stop_limit=12,
            parallelism=3,
            search_timeout=5,
            recommended_route_planner=recommended_route_planner,
        )

        result = json.loads(await operations.recommend_places_on_map(
            ["景点甲", "景点乙"],
            "杭州",
            "推荐路线",
            "查看路线",
        ))

        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(
            [
                place["place_id"]
                for place in captured["_verified_recommended_places"]
            ],
            ["poi-景点甲", "poi-景点乙"],
        )

        async def failed_route_planner(**_kwargs):
            raise RuntimeError("provider route unavailable")

        operations._recommended_route_planner = failed_route_planner
        degraded = json.loads(await operations.recommend_places_on_map(
            ["景点甲", "景点乙"],
            "杭州",
            "推荐路线",
            "查看路线",
        ))
        self.assertEqual(degraded["route_status"], "unavailable")
        self.assertEqual(
            degraded["action"]["payload"]["route_status"],
            "unavailable",
        )
        self.assertNotEqual(
            degraded["action"]["payload"]["action_text"],
            "查看路线",
        )

    async def test_unordered_recommendation_uses_shared_route_chain(self):
        names = ["景点甲", "景点乙", "景点丙"]

        async def place_provider(_map_key, query, *, city, limit):
            self.assertEqual(city, "杭州")
            return [{
                **PLACE,
                "place_id": f"poi-{query}",
                "name": query,
                "city": "杭州市",
                "address": f"杭州市{query}路",
            }]

        async def route_provider(_map_key, places, **kwargs):
            self.assertTrue(kwargs["optimize"])
            self.assertEqual(kwargs["strategy"], "time_then_cost")
            ordered = [places[2], places[0], places[1]]
            return {
                "provider": "tencent",
                "mode": "driving",
                "places": ordered,
                "legs": [{
                    "from": ordered[index],
                    "to": ordered[index + 1],
                    "mode": "driving",
                    "distance_meters": 1_000,
                    "duration_seconds": 600,
                    "path": [],
                    "sections": [],
                } for index in range(2)],
                "distance_meters": 2_000,
                "duration_seconds": 1_200,
                "selection": {
                    "stop_order_policy": "tencent_matrix_optimized",
                },
            }

        store = FakeStore()
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=place_provider,
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=route_provider,
        ):
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="unordered-recommendation",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            tool = next(
                item for item in tools
                if item.name == "recommend_places_on_map"
            )
            result = json.loads(await tool.ainvoke({
                "queries": names,
                "city": "杭州",
                "title": "杭州景点",
                "action_text": "查看路线",
            }))

        self.assertEqual(
            [place["name"] for place in result["ordered_stops"]],
            ["景点丙", "景点甲", "景点乙"],
        )
        self.assertEqual(
            result["action"]["payload"]["stop_order_policy"],
            "tencent_matrix_optimized",
        )
        saved = await load_user_workspace(store, user_id=TEST_USER_ID)
        current = current_route_plan(saved, "unordered-recommendation")
        self.assertEqual(current["id"], result["route_plan_id"])
        self.assertEqual(current["stop_order_policy"], "tencent_matrix_optimized")

    async def test_tencent_matrix_duration_drives_time_preference(self):
        places = [
            {"place_id": "a", "latitude": 30.1, "longitude": 120.1},
            {"place_id": "b", "latitude": 30.2, "longitude": 120.2},
            {"place_id": "c", "latitude": 30.3, "longitude": 120.3},
        ]
        matrix_response = {"result": {"rows": [
            {"elements": [
                {"distance": 0, "duration": 0},
                {"distance": 1, "duration": 10},
                {"distance": 10, "duration": 1},
            ]},
            {"elements": [
                {"distance": 1, "duration": 10},
                {"distance": 0, "duration": 0},
                {"distance": 1, "duration": 1},
            ]},
            {"elements": [
                {"distance": 10, "duration": 1},
                {"distance": 1, "duration": 1},
                {"distance": 0, "duration": 0},
            ]},
        ]}}
        with patch(
            "agents._infrastructure.providers.tencent_location._get",
            new=AsyncMock(return_value=matrix_response),
        ):
            optimized = await optimize_place_order(
                "map-key", places, strategy="least_time",
            )
        self.assertEqual(
            [place["place_id"] for place in optimized],
            ["a", "c", "b"],
        )

    async def test_direction_adapter_builds_matrix_when_matrix_capability_is_unavailable(self):
        places = [
            {"place_id": "a", "latitude": 30.1, "longitude": 120.1},
            {"place_id": "b", "latitude": 30.2, "longitude": 120.2},
            {"place_id": "c", "latitude": 30.3, "longitude": 120.3},
        ]
        metrics = {
            ("a", "b"): (10_000, 1_000),
            ("a", "c"): (1_000, 100),
            ("b", "c"): (1_000, 100),
        }
        calls = []

        async def route_leg(_key, origin, destination, *, mode, **_kwargs):
            calls.append((origin["place_id"], destination["place_id"], mode))
            distance, duration = metrics[(origin["place_id"], destination["place_id"])]
            return {
                "distance_meters": distance,
                "duration_seconds": duration,
            }

        with (
            patch(
                "agents._infrastructure.providers.tencent_location._get",
                new=AsyncMock(side_effect=RuntimeError("matrix not enabled")),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location._plan_route_leg",
                new=route_leg,
            ),
        ):
            optimized = await optimize_place_order(
                "map-key", places, strategy="least_time",
            )

        self.assertEqual(
            [place["place_id"] for place in optimized],
            ["a", "c", "b"],
        )
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(mode == "driving" for *_pair, mode in calls))

    async def test_transit_preference_uses_transit_direction_for_stop_order(self):
        places = [
            {"place_id": "a", "latitude": 30.1, "longitude": 120.1},
            {"place_id": "b", "latitude": 30.2, "longitude": 120.2},
            {"place_id": "c", "latitude": 30.3, "longitude": 120.3},
        ]
        calls = []

        async def route_leg(_key, origin, destination, *, mode, **_kwargs):
            calls.append((origin["place_id"], destination["place_id"], mode))
            short = {origin["place_id"], destination["place_id"]} != {"a", "b"}
            return {
                "distance_meters": 1_000 if short else 10_000,
                "duration_seconds": 100 if short else 1_000,
                "selection": {},
            }

        matrix = AsyncMock(side_effect=AssertionError("transit has no matrix mode"))
        with (
            patch(
                "agents._infrastructure.providers.tencent_location._get",
                new=matrix,
            ),
            patch(
                "agents._infrastructure.providers.tencent_location._plan_route_leg",
                new=route_leg,
            ),
        ):
            optimized = await optimize_place_order(
                "map-key", places, mode="transit", strategy="least_cost",
            )

        self.assertEqual(
            [place["place_id"] for place in optimized],
            ["a", "c", "b"],
        )
        matrix.assert_not_awaited()
        self.assertTrue(all(mode == "transit" for *_pair, mode in calls))

    async def test_public_fallback_candidates_never_enter_model_reconciliation(self):
        model = MagicMock()
        result = await _place_resolution_with_provider_review(model, "目的地", [
            {**PLACE, "place_id": "osm-a", "provider": "openstreetmap"},
            {**PLACE, "place_id": "osm-b", "provider": "openstreetmap"},
        ])
        self.assertEqual(result, ("choose", None, "multiple_verified_candidates"))
        model.with_structured_output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
