"""Pure Skill membership policy."""

from __future__ import annotations

from collections.abc import Iterable

from ..entitlements.policy import GUEST_SKILL_IDS, plan_allows


def accessible_skill_ids(
    *,
    auth_type: str,
    membership: str,
    requested: Iterable[str],
    required_plans: dict[str, str],
) -> frozenset[str]:
    skill_ids = frozenset(str(value) for value in requested if str(value))
    if auth_type == "guest":
        return skill_ids & GUEST_SKILL_IDS
    return frozenset(
        skill_id
        for skill_id in skill_ids
        if plan_allows(membership, required_plans.get(skill_id, "free"))
    )
