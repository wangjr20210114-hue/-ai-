from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from agents._domain.entitlements.policy import (
    allowed_skill_ids,
    normalize_membership,
    plan_allows,
    public_entitlements,
)


ROOT = Path(__file__).resolve().parents[3]


class EntitlementPolicyTests(unittest.TestCase):
    def test_invalid_membership_uses_auth_type_default(self) -> None:
        self.assertEqual(normalize_membership("unknown", "guest"), "guest")
        self.assertEqual(normalize_membership("unknown", "wechat"), "free")

    def test_plan_order_and_guest_skills_come_from_contract(self) -> None:
        self.assertFalse(plan_allows("free", "plus"))
        self.assertTrue(plan_allows("pro", "plus"))
        self.assertEqual(
            allowed_skill_ids(
                {"auth_type": "guest"},
                {"core", "proactive-agent", "web-search"},
            ),
            frozenset({"core", "proactive-agent"}),
        )

    def test_node_and_python_public_entitlements_have_value_parity(self) -> None:
        script = """
import { publicEntitlements } from './auth/entitlements.js';
const plans = ['guest', 'free', 'plus', 'pro', 'invalid'];
const result = Object.fromEntries(plans.map((membership) => [
  membership,
  publicEntitlements({
    auth_type: membership === 'invalid' ? 'wechat' : (membership === 'guest' ? 'guest' : 'wechat'),
    membership,
  }),
]));
process.stdout.write(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        node_values = json.loads(result.stdout)
        for membership in ("guest", "free", "plus", "pro", "invalid"):
            identity = {
                "auth_type": (
                    "wechat"
                    if membership == "invalid"
                    else ("guest" if membership == "guest" else "wechat")
                ),
                "membership": membership,
            }
            python_value = public_entitlements(identity)
            node_value = node_values[membership]
            normalized_node_limits = {
                "search_depth": node_value["limits"]["searchDepth"],
                "concurrent_runs": node_value["limits"]["concurrentRuns"],
                "daily_tokens": node_value["limits"]["dailyTokens"],
                "user_skill_uploads": node_value["limits"]["userSkillUploads"],
            }
            self.assertEqual(node_value["plan"], python_value["plan"])
            self.assertEqual(normalized_node_limits, python_value["limits"])
            self.assertEqual(
                node_value["payment_available"],
                python_value["payment_available"],
            )


if __name__ == "__main__":
    unittest.main()
