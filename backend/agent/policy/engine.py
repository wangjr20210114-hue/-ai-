"""Central policy engine for plan permission and side-effect confirmation."""
from __future__ import annotations

from agent.context import AgentContext
from agent.contracts import AgentPlan, PermissionLevel, PolicyDecision, RiskLevel


class AgentPolicy:
    """Decide whether a plan is denied, suggested, confirmed, or auto-executed."""

    def decide(self, plan: AgentPlan, context: AgentContext) -> PolicyDecision:
        del context  # reserved for preference, budget and enterprise policy inputs
        level = plan.permission_level
        risk = plan.risk_level

        if plan.confirmation.required:
            level = PermissionLevel.CONFIRM
        if level == PermissionLevel.DENY:
            return PolicyDecision(
                permission_level=level,
                allowed=False,
                reason="skill_policy_denied",
                risk_level=risk,
            )
        if level == PermissionLevel.CONFIRM:
            return PolicyDecision(
                permission_level=level,
                allowed=True,
                requires_confirmation=True,
                reason=plan.confirmation.reason or "confirmation_required",
                risk_level=risk,
                metadata={"reversible": plan.confirmation.reversible},
            )
        # HIGH risk + AUTO: only escalate to confirm for side_effect skills
        # (those that go through PendingAction + ActionExecutor). Non-side-effect
        # skills handle execution directly in suggest()/execute() and should
        # not be blocked by the confirmation guard in the orchestrator.
        if risk == RiskLevel.HIGH and level == PermissionLevel.AUTO and plan.side_effect:
            return PolicyDecision(
                permission_level=PermissionLevel.CONFIRM,
                allowed=True,
                requires_confirmation=True,
                reason="high_risk_side_effect_needs_confirmation",
                risk_level=risk,
            )
        return PolicyDecision(
            permission_level=level,
            allowed=True,
            requires_confirmation=False,
            reason="policy_allowed",
            risk_level=risk,
        )
