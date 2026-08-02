from __future__ import annotations

import json
import unittest

from agents.chat._capability_plan import parse_capability_plan


class TravelPlanningTests(unittest.TestCase):
    def test_travel_itinerary_without_budget_becomes_one_structured_question(self):
        plan = parse_capability_plan(json.dumps({
            "needs_travel_itinerary": True,
            "travel_budget_tier": "unknown",
            "needs_route": True,
            "needs_calendar_action": True,
        }))
        self.assertTrue(plan["needs_clarification"])
        self.assertFalse(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(len(plan["clarification_fields"]), 1)
        field = plan["clarification_fields"][0]
        self.assertEqual(field["id"], "travel-budget-tier")
        self.assertEqual(field["type"], "single")
        self.assertEqual(field["options"], ["省钱", "标准", "没考虑"])

    def test_explicit_travel_budget_does_not_repeat_the_question(self):
        plan = parse_capability_plan(json.dumps({
            "needs_travel_itinerary": True,
            "travel_budget_tier": "economy",
            "needs_route": True,
        }))
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_route"])


if __name__ == "__main__":
    unittest.main()
