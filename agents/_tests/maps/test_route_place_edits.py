from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents._application.workspace.service import (
    load_user_workspace,
    save_user_workspace,
)
from agents._domain.maps.route_place_set import RoutePlaceEdit, apply_route_place_edits
from agents._domain.maps.route_strategy import infer_route_preferences, select_route_strategy


class RoutePlaceSetPolicyTests(unittest.TestCase):
    def test_route_preferences_are_extracted_by_domain_policy(self):
        self.assertEqual(infer_route_preferences("公交优先，想省钱"), ("transit", "least_cost"))
        self.assertEqual(infer_route_preferences("take the fastest bike route"), ("bicycling", "least_time"))
        self.assertEqual(infer_route_preferences("不要步行，改坐公交"), ("transit", ""))
        self.assertEqual(infer_route_preferences("公交加步行接驳"), ("transit", ""))

    def test_proven_city_scopes_provider_candidates(self):
        places = [
            {**PLACE, "place_id": "beijing", "city": "北京市"},
            {**PLACE, "place_id": "haikou", "city": "海口市"},
        ]
        scoped = _scope_provider_candidates_for_city(places, "北京")
        self.assertEqual([place["place_id"] for place in scoped], ["beijing"])

    def test_typo_tolerant_remove_is_limited_to_current_route(self):
        result = apply_route_place_edits(
            [
                {"place_id": "station", "name": "北京站"},
                {"place_id": "square", "name": "天安门"},
                {"place_id": "museum", "name": "故宫博物院"},
            ],
            [RoutePlaceEdit(operation="remove", target_query="天安们")],
        )
        self.assertFalse(result.issues)
        self.assertEqual(
            [stop["place_id"] for stop in result.stops],
            ["station", "museum"],
        )

    def test_ambiguous_existing_branch_requires_a_current_route_choice(self):
        result = apply_route_place_edits(
            [
                {"place_id": "a", "name": "纯K", "address": "朝阳店"},
                {"place_id": "b", "name": "纯K", "address": "海淀店"},
                {"place_id": "c", "name": "北京站"},
            ],
            [RoutePlaceEdit(operation="remove", target_query="纯K")],
        )
        self.assertEqual(result.issues[0].reason, "ambiguous_target")
        self.assertEqual(
            {item["place_id"] for item in result.issues[0].candidates},
            {"a", "b"},
        )

    def test_replace_emits_only_the_new_place_for_provider_verification(self):
        result = apply_route_place_edits(
            [
                {"place_id": "a", "name": "北京站"},
                {"place_id": "b", "name": "天安门"},
            ],
            [RoutePlaceEdit(
                operation="replace",
                target_query="天安门",
                new_query="故宫博物院",
            )],
        )
        self.assertFalse(result.issues)
        self.assertEqual(result.stops[0]["place_id"], "a")
        self.assertEqual(result.stops[1]["query"], "故宫博物院")
        self.assertEqual(result.new_stop_edit_indexes, (None, 0))

    def test_route_strategy_keeps_latest_route_when_edit_has_no_new_preference(self):
        selected = select_route_strategy(
            requested_mode="default",
            planned_mode="default",
            context_mode="transit",
            learned_mode="driving",
            default_mode="driving",
            requested_strategy="default",
            planned_strategy="default",
            context_strategy="least_cost",
            learned_strategy="least_time",
            default_strategy="time_then_cost",
        )
        self.assertEqual((selected.mode, selected.strategy), ("transit", "least_cost"))


class RoutePlaceEditContractTests(unittest.IsolatedAsyncioTestCase):
    def test_capability_plan_preserves_route_place_edits_without_rebuilding_stops(self):
        plan = parse_capability_plan({
            "capabilities": ["route"],
            "needs_route": False,
            "route_place_edits": [{
                "operation": "remove",
                "target_query": "天安们",
                "position": "default",
            }],
        })
        self.assertEqual(plan["route_stops"], [])
        self.assertEqual(plan["route_place_edits"][0]["target_query"], "天安们")
        self.assertEqual(required_tools_for_plan(plan), ("plan_route_between_places",))

    def test_route_edit_choice_resumes_the_original_operation(self):
        _plan, arguments = resume_capability_protocol(
            {"needs_route": False},
            {
                "version": "1",
                "required_tools": ["plan_route_between_places"],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "place_edits": [{
                            "operation": "remove",
                            "target_query": "纯K",
                            "new_query": "",
                            "position": "default",
                        }],
                    },
                },
            },
            [{"id": "route_edit_target_0", "value": "floris-place:branch-b"}],
        )
        route = arguments["plan_route_between_places"]
        self.assertEqual(
            route["place_edits"][0]["target_query"],
            "floris-place:branch-b",
        )

    def test_manual_origin_resume_keeps_dependent_calendar_protocol(self):
        plan, arguments = resume_capability_protocol(
            {"needs_route": False},
            {
                "version": "1",
                "required_tools": [
                    "plan_route_between_places",
                    "propose_calendar_changes",
                ],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "destination_query": "北京站",
                        "use_current_location_as_origin": True,
                    },
                    "propose_calendar_changes": {
                        "summary": "去接朋友并写入日程",
                        "changes": [],
                    },
                },
            },
            [{"id": "route_origin", "value": "北京南站"}],
        )
        self.assertTrue(plan["calendar_uses_planned_route"])
        self.assertTrue(plan["reuse_latest_route"])
        self.assertTrue(plan["route_origin_is_departure"])
        self.assertEqual(
            arguments["plan_route_between_places"]["origin_query"],
            "北京南站",
        )
        self.assertEqual(
            arguments["propose_calendar_changes"]["changes"],
            [],
        )

    async def test_tool_reuses_cached_pois_and_only_replans_after_typo_remove(self):
        store = FakeStore()
        state = await load_user_workspace(store, user_id=TEST_USER_ID)
        stops = [
            {**PLACE, "place_id": "station", "name": "北京站"},
            {**PLACE, "place_id": "square", "name": "天安门"},
            {**PLACE, "place_id": "museum", "name": "故宫博物院"},
        ]
        state["place_candidates"] = {
            stop["place_id"]: stop for stop in stops
        }
        state["latest_route_plan"] = {
            "id": "routeplan-before-edit",
            "ordered_stops": stops,
            "mode": "transit",
            "strategy": "least_cost",
            "explicit_origin_is_departure": True,
        }
        await save_user_workspace(store, state, user_id=TEST_USER_ID)
        route = {
            "provider": "tencent",
            "mode": "transit",
            "distance_meters": 12_000,
            "duration_seconds": 2_400,
            "fare": {"amount": 5, "currency": "CNY"},
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=AsyncMock(),
        ) as search, patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(return_value=route),
        ) as planner:
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-place-edit",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "place_edits": [{
                    "operation": "remove",
                    "target_query": "天安们",
                }],
            }))

        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(
            [stop["place_id"] for stop in result["ordered_stops"]],
            ["station", "museum"],
        )
        search.assert_not_awaited()
        planner.assert_awaited_once()
        called = planner.await_args.args[1]
        self.assertEqual([stop["place_id"] for stop in called], ["station", "museum"])

    async def test_new_place_ambiguity_resumes_without_repeating_provider_search(self):
        store = FakeStore()
        state = await load_user_workspace(store, user_id=TEST_USER_ID)
        stops = [
            {**PLACE, "place_id": "station", "name": "北京站"},
            {**PLACE, "place_id": "museum", "name": "故宫博物院"},
        ]
        state["place_candidates"] = {
            stop["place_id"]: stop for stop in stops
        }
        state["latest_route_plan"] = {
            "id": "routeplan-add-before",
            "ordered_stops": stops,
            "mode": "transit",
            "strategy": "time_then_cost",
        }
        await save_user_workspace(store, state, user_id=TEST_USER_ID)
        branches = [
            {
                **PLACE,
                "place_id": f"ktv-{index}",
                "name": f"纯K({district}店)",
                "address": f"北京市{district}",
            }
            for index, district in enumerate(("朝阳区", "海淀区"), 1)
        ]
        route = {
            "provider": "tencent",
            "mode": "transit",
            "distance_meters": 18_000,
            "duration_seconds": 3_000,
            "fare": {"amount": 6, "currency": "CNY"},
        }
        search = AsyncMock(return_value=branches)
        planner = AsyncMock(return_value=route)
        original_arguments = {
            "city": "北京",
            "place_edits": [{
                "operation": "add",
                "target_query": "",
                "new_query": "纯K",
                "new_near_query": "",
                "position": "end",
            }],
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            new=search,
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=planner,
        ):
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-place-add",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            first = json.loads(await route_tool.ainvoke(original_arguments))
            field = first["clarification"]["fields"][0]
            self.assertEqual(field["id"], "route_edit_new_0")
            selected = field["option_values"][field["options"][1]]
            plan, resumed = resume_capability_protocol(
                {"needs_route": False},
                {
                    "version": "1",
                    "required_tools": ["plan_route_between_places"],
                    "planned_tool_arguments": {
                        "plan_route_between_places": original_arguments,
                    },
                },
                [{"id": field["id"], "value": selected}],
            )
            resumed_tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-place-add",
                user_id=TEST_USER_ID,
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=plan["route_stops"],
            )
            resumed_tool = next(
                item for item in resumed_tools
                if item.name == "plan_route_between_places"
            )
            second = json.loads(await resumed_tool.ainvoke(
                resumed["plan_route_between_places"]
            ))

        self.assertEqual(second["ui_action"], "map_action")
        self.assertEqual(second["ordered_stops"][-1]["place_id"], "ktv-2")
        self.assertEqual(search.await_count, 1)
        planner.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
