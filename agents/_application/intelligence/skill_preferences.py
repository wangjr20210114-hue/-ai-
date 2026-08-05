"""Partial-success batch semantics for backend-authoritative Skill switches."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..._domain.entitlements.policy import (
    allowed_skill_ids,
    effective_skill_preferences,
)
from ..skills.registry import skill_manifest


def _eligible(identity: Mapping[str, Any], skill_id: str) -> bool:
    manifest = skill_manifest(skill_id)
    required_plan = manifest.required_plan if manifest is not None else "free"
    return skill_id in allowed_skill_ids(
        identity,
        [skill_id],
        required_plans={skill_id: required_plan},
    )


def _dependency_closure(skill_id: str) -> set[str]:
    closure: set[str] = set()
    pending = [skill_id]
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        closure.add(current)
        manifest = skill_manifest(current)
        if manifest is not None:
            pending.extend(manifest.requires)
    return closure


def apply_skill_preference_batch(
    identity: Mapping[str, Any],
    previous: Mapping[str, Any],
    defaults: Mapping[str, bool],
    requested: Mapping[str, Any],
) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    current = {
        skill_id: bool(previous.get(skill_id, enabled))
        for skill_id, enabled in defaults.items()
    }
    rejections: dict[str, str] = {}

    for raw_id, enabled in requested.items():
        skill_id = str(raw_id or "")
        manifest = skill_manifest(skill_id)
        if skill_id not in defaults or manifest is None:
            rejections[skill_id] = "UNKNOWN_SKILL"
        elif not bool(enabled) and manifest.locked:
            rejections[skill_id] = "SKILL_LOCKED"
        elif not bool(enabled):
            current[skill_id] = False

    for raw_id, enabled in requested.items():
        skill_id = str(raw_id or "")
        if not bool(enabled) or skill_id in rejections:
            continue
        closure = _dependency_closure(skill_id)
        unavailable = next(
            (item for item in closure if not _eligible(identity, item)),
            "",
        )
        if unavailable:
            rejections[skill_id] = (
                "LOGIN_REQUIRED"
                if str(identity.get("auth_type") or "guest") == "guest"
                else "MEMBERSHIP_REQUIRED"
            )
            continue
        for item in closure:
            if item in current:
                current[item] = True

    current = effective_skill_preferences(identity, current)
    for skill_id in defaults:
        manifest = skill_manifest(skill_id)
        if manifest is not None and manifest.locked:
            current[skill_id] = True

    results = []
    for raw_id, enabled in requested.items():
        skill_id = str(raw_id or "")
        desired = bool(enabled)
        effective = bool(current.get(skill_id, False))
        code = rejections.get(skill_id, "")
        if not code and effective != desired:
            code = "DEPENDENCY_REQUIRED" if not desired else "POLICY_REJECTED"
        results.append({
            "skill_id": skill_id,
            "requested_enabled": desired,
            "effective_enabled": effective,
            "applied": not code,
            "code": code,
        })
    return current, results
