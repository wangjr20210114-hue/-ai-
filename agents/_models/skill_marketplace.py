"""Pure Skill marketplace domain projection.

This module deliberately has no EdgeOne request/context dependency. It turns
Skill manifests plus an authenticated identity into marketplace domain state.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .._domain.entitlements.policy import allowed_skill_ids


PUBLIC_IDENTITY_FIELDS = (
    "user_id",
    "subject_id",
    "tenant_id",
    "display_name",
    "avatar_url",
    "auth_type",
    "membership",
    "roles",
)


def marketplace_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only identity fields needed by the marketplace View."""
    return {
        key: identity.get(key)
        for key in PUBLIC_IDENTITY_FIELDS
    }


def decorate_catalog(
    catalog: Iterable[Mapping[str, Any]],
    *,
    identity: Mapping[str, Any],
    preferences: Mapping[str, bool],
) -> list[dict[str, Any]]:
    """Apply tenant/user entitlement and installation state to catalog Models."""
    skills = [dict(item) for item in catalog]
    requirements = {
        str(item.get("id") or ""): str(item.get("required_plan") or "free")
        for item in skills
    }
    for item in skills:
        skill_id = str(item.get("id") or "")
        eligible = skill_id in allowed_skill_ids(
            identity,
            [skill_id],
            required_plans=requirements,
        )
        item["eligible"] = eligible
        item["installed"] = eligible and bool(preferences.get(skill_id, False))
        item["eligibility_reason"] = (
            ""
            if eligible
            else "login_required"
            if str(identity.get("auth_type") or "guest") == "guest"
            else "membership_required"
        )
    return skills


def downloadable_skill(
    catalog: Iterable[Mapping[str, Any]],
    skill_id: str,
) -> bool:
    """A user may download only a package already installed for that identity."""
    return any(
        str(item.get("id") or "") == skill_id
        and bool(item.get("installed"))
        for item in catalog
    )
