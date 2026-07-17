"""PendingAction confirmation use cases."""
from __future__ import annotations

import time
from typing import Any

from agent.contracts import AgentPlan
from database.repositories import runtime_repo
from skills.base_skill import BaseSkill


class ActionService:
    def __init__(self, default_expiry_seconds: int = 24 * 60 * 60) -> None:
        self.default_expiry_seconds = default_expiry_seconds

    async def create_pending_action(
        self,
        run_id: str,
        plan: AgentPlan,
        skill: BaseSkill,
        *,
        expires_at: float | None = None,
    ) -> dict[str, Any]:
        if not skill.side_effect or skill.action_input_model is None:
            raise ValueError(f"skill {skill.name} is not a side-effecting action")
        input_model = await skill.prepare_action_input(plan.user_message, plan.params)
        estimated_cost = skill.estimated_cost_cny(input_model)
        confirmation = {
            "action_label": plan.confirmation.action_label,
            "reason": plan.confirmation.reason,
            "reversible": plan.confirmation.reversible,
            "risk_level": plan.risk_level.value,
            "estimated_cost_cny": estimated_cost,
        }
        snapshot = {
            "skill_name": skill.name,
            "input_model": skill.action_input_model.__name__,
            "input": input_model.model_dump(mode="json"),
            "confirmation": confirmation,
            "source": {
                "run_id": run_id,
                "event_type": plan.event_type,
                "intent": plan.intent,
            },
        }
        idempotency_key = skill.action_idempotency_key(input_model, run_id)
        return await runtime_repo.create_action(
            run_id,
            skill.name,
            snapshot,
            idempotency_key,
            expires_at=expires_at or time.time() + self.default_expiry_seconds,
        )

    async def confirm_action(
        self,
        action_id: str,
        version: int,
        actor_id: str = "local-user",
    ) -> dict[str, Any]:
        del actor_id  # single-user baseline; kept in the contract for future auth
        return await runtime_repo.confirm_action(action_id, version)

    async def cancel_action(self, action_id: str, actor_id: str = "local-user") -> dict[str, Any]:
        del actor_id
        return await runtime_repo.cancel_action(action_id)
