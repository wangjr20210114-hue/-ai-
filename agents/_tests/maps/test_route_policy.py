from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents._application.chat.turn_policy import (
    route_calendar_tool_arguments,
    route_tool_arguments_for_plan,
)
from agents.chat._calendar_context import latest_route_context


class RoutePolicyTests(unittest.TestCase):
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
            {"latest_route_plan": {"ordered_stops": [
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
