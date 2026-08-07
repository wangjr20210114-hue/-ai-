from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents.chat._calendar_context import latest_route_context


class RoutePolicyTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
