from __future__ import annotations

import unittest

from agents._application.skills.access import resolve_skill_access
from agents._domain.entitlements.generated_contract import GUEST_SKILL_IDS


class SkillAccessPolicyTests(unittest.TestCase):
    def test_guest_defaults_can_never_restore_non_guest_skills(self) -> None:
        access = resolve_skill_access(
            {"auth_type": "guest", "membership": "guest"},
            {},
        )

        self.assertEqual(access.enabled_skills, GUEST_SKILL_IDS)
        self.assertTrue(access.allows_capability("clarification"))
        self.assertTrue(access.allows_capability("workflow_action"))
        self.assertFalse(access.allows_capability("web_search"))
        self.assertFalse(access.allows_capability("route"))
        self.assertEqual(
            access.reason_for_capability("route"),
            "login_required",
        )
        self.assertFalse(access.preference_map()["maps"])

    def test_authenticated_user_switch_has_a_non_login_downgrade(self) -> None:
        access = resolve_skill_access(
            {"auth_type": "cloudbase", "membership": "free"},
            {"web-search": False, "maps": True},
        )

        self.assertFalse(access.allows_capability("web_search"))
        self.assertTrue(access.allows_capability("route"))
        self.assertEqual(
            access.reason_for_capability("web_search"),
            "degraded",
        )


if __name__ == "__main__":
    unittest.main()
