from __future__ import annotations

import json
import unittest
from pathlib import Path

from agents._domain.entitlements.generated_contract import (
    ENTITLEMENT_CONTRACT,
    GUEST_SKILL_IDS,
    MEMBERSHIP_PLANS,
    PAYMENT_AVAILABLE,
    PLAN_LIMITS,
)


ROOT = Path(__file__).resolve().parents[3]


class EntitlementContractTests(unittest.TestCase):
    def test_generated_python_values_equal_canonical_contract(self) -> None:
        contract = json.loads(
            (ROOT / "contracts" / "entitlements.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(ENTITLEMENT_CONTRACT, contract)
        self.assertEqual(MEMBERSHIP_PLANS, tuple(contract["plans"]))
        self.assertEqual(GUEST_SKILL_IDS, frozenset(contract["guest_skill_ids"]))
        self.assertEqual(PLAN_LIMITS, contract["limits"])
        self.assertEqual(PAYMENT_AVAILABLE, contract["payment_available"])

    def test_plan_order_is_stable(self) -> None:
        self.assertEqual(MEMBERSHIP_PLANS, ("guest", "free", "plus", "pro"))


if __name__ == "__main__":
    unittest.main()
