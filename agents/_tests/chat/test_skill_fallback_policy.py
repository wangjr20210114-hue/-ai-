from __future__ import annotations

import unittest

from agents._application.chat.skill_policy import apply_runtime_skill_policy


class SkillFallbackPolicyTests(unittest.TestCase):
    def test_abandoned_component_arguments_do_not_shape_model_fallback(self):
        plan = apply_runtime_skill_policy(
            {
                "needs_clarification": True,
                "needs_web_search": True,
                "web_search_is_independent": True,
                "needs_calendar_action": True,
                "route_stops": [{"query": "A"}, {"query": "B"}],
                "_capabilities": [
                    "web_search",
                    "calendar_action",
                    "route",
                ],
            },
            {"web-search", "calendar", "maps"},
            {
                "web-search": "login_required",
                "calendar": "login_required",
                "maps": "login_required",
            },
        )

        self.assertFalse(plan["needs_clarification"])
        self.assertFalse(plan["needs_web_search"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(plan["route_stops"], [])
        self.assertEqual(plan["_capabilities"], [])
        self.assertEqual(
            plan["_runtime_model_fallback_skills"],
            ["web-search", "calendar", "maps"],
        )
        self.assertTrue(plan["_runtime_model_only_fallback"])
        self.assertEqual(
            set(plan["_runtime_fallback_reasons"].values()),
            {"login_required"},
        )


if __name__ == "__main__":
    unittest.main()
