"""Public JSON View for the authenticated intelligence Model."""

from __future__ import annotations

from typing import Any, Mapping

from .._models.skill_marketplace import decorate_catalog
from .._shared.entitlements import effective_skill_preferences, public_entitlements
from .._shared.intelligence import (
    public_intelligence_state,
    public_skill_connections,
    skill_runtime_env,
)
from .._shared.skill_registry import public_skill_catalog


def public_intelligence_view(
    state: Mapping[str, Any],
    env: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Project private user state into the safe representation used by Views."""
    public = public_intelligence_state(state)
    effective_preferences = effective_skill_preferences(
        identity,
        public.get("skill_preferences"),
    )
    public["skill_preferences"] = effective_preferences
    catalog = decorate_catalog(
        public_skill_catalog(skill_runtime_env(env, state)),
        identity=identity,
        preferences=effective_preferences,
    )
    public["skill_catalog"] = catalog
    public["skill_connections"] = public_skill_connections(state)
    public["providers"] = {
        item["id"]: bool(item["configured"])
        for item in catalog
        if item.get("external")
    }
    public["identity"] = {
        key: identity.get(key)
        for key in (
            "user_id",
            "subject_id",
            "tenant_id",
            "username",
            "display_name",
            "avatar_url",
            "auth_type",
            "membership",
            "roles",
        )
    }
    public["entitlements"] = public_entitlements(identity)
    return public
