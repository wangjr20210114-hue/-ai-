from __future__ import annotations

import unittest

from agent.context import AgentContext
from agent.contracts import AgentPlan, ConfirmationPolicy, PermissionLevel, RiskLevel
from agent.policy import AgentPolicy


def make_plan(
    permission: PermissionLevel,
    risk: RiskLevel = RiskLevel.LOW,
    confirmation: bool = False,
) -> AgentPlan:
    return AgentPlan(
        run_id="run-1",
        session_id="session-1",
        event_type="user_activity",
        user_message="test",
        intent="test",
        permission_level=permission,
        risk_level=risk,
        confirmation=ConfirmationPolicy(required=confirmation),
    )


class AgentPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = AgentContext(session_id="session-1", history=[])
        self.policy = AgentPolicy()

    def test_high_risk_auto_action_is_downgraded_to_confirmation(self) -> None:
        decision = self.policy.decide(make_plan(PermissionLevel.AUTO, RiskLevel.HIGH), self.context)
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual(decision.permission_level, PermissionLevel.CONFIRM)

    def test_deny_action_is_blocked(self) -> None:
        decision = self.policy.decide(make_plan(PermissionLevel.DENY), self.context)
        self.assertFalse(decision.allowed)

    def test_explicit_confirmation_is_honored(self) -> None:
        decision = self.policy.decide(make_plan(PermissionLevel.AUTO, confirmation=True), self.context)
        self.assertTrue(decision.requires_confirmation)
