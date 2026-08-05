"""Application policy that reconciles semantic plans with Skill access."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

from ..skills.registry import (
    capability_skill_map,
    known_skill_ids,
    skill_plan_flags,
)
from ...chat._capability_plan import DEFAULT_PLAN, reconcile_capability_contract


KNOWN_SKILLS = known_skill_ids()
CAPABILITY_SKILLS = capability_skill_map()
SKILL_PLAN_FLAGS = skill_plan_flags()


def apply_runtime_skill_policy(
    plan: dict[str, Any],
    disabled_skills: Iterable[Any],
    disabled_skill_reasons: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Remove unavailable adapters and preserve a safe model fallback."""
    reconciled = reconcile_capability_contract(plan)
    if reconciled.get("reuse_latest_route"):
        # A verified workspace route is a resolved reference, so a calendar
        # action may consume it without invoking the map provider again.
        reconciled["needs_route"] = False
        reconciled["route_stops"] = []
        reconciled["_capabilities"] = [
            capability
            for capability in (reconciled.get("_capabilities") or [])
            if str(capability) != "route"
        ]
    reconciled["blocked_skill"] = ""
    disabled = {
        str(skill_id or "").strip()
        for skill_id in disabled_skills
        if str(skill_id or "").strip() in KNOWN_SKILLS
    }
    required_skills: list[str] = []
    for capability in reconciled.get("_capabilities") or []:
        skill_id = CAPABILITY_SKILLS.get(str(capability or "").strip())
        if skill_id and skill_id in disabled and skill_id not in required_skills:
            required_skills.append(skill_id)
    for skill_id, flags in SKILL_PLAN_FLAGS.items():
        if (
            skill_id in disabled
            and any(bool(reconciled.get(flag)) for flag in flags)
            and skill_id not in required_skills
        ):
            required_skills.append(skill_id)
    if not required_skills:
        return reconciled

    for skill_id in required_skills:
        for flag in SKILL_PLAN_FLAGS.get(skill_id, ()):
            reconciled[flag] = False
    reconciled["_capabilities"] = [
        capability
        for capability in (reconciled.get("_capabilities") or [])
        if CAPABILITY_SKILLS.get(str(capability)) not in required_skills
    ]
    reasons = disabled_skill_reasons or {}
    fallback_reasons = {
        skill_id: (
            "login_required"
            if str(reasons.get(skill_id) or "") == "login_required"
            else "degraded"
        )
        for skill_id in required_skills
    }
    reconciled["_runtime_model_fallback_skills"] = list(required_skills)
    reconciled["_runtime_omitted_skills"] = list(required_skills)
    reconciled["_runtime_fallback_reasons"] = fallback_reasons

    remaining_component = bool(reconciled.get("_capabilities")) or any(
        any(bool(reconciled.get(flag)) for flag in flags)
        for skill_id, flags in SKILL_PLAN_FLAGS.items()
        if skill_id not in required_skills
    )
    if remaining_component:
        return reconciled

    # Preparatory arguments and clarification cards belong to the components
    # that just degraded. They must not reshape the ordinary model answer.
    fallback = copy.deepcopy(DEFAULT_PLAN)
    fallback["_runtime_model_fallback_skills"] = list(required_skills)
    fallback["_runtime_omitted_skills"] = list(required_skills)
    fallback["_runtime_fallback_reasons"] = fallback_reasons
    fallback["_runtime_model_only_fallback"] = True
    return fallback


__all__ = ["apply_runtime_skill_policy"]
