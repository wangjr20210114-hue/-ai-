"""Controller for the read-only Skill marketplace route."""

from __future__ import annotations

from .._models.skill_marketplace import (
    decorate_catalog,
    downloadable_skill,
    marketplace_identity,
)
from .._shared.auth import require_user
from .._shared.component_api import public_component_api
from .._shared.entitlements import effective_skill_preferences, public_entitlements
from .._shared.intelligence import (
    load_intelligence_state,
    public_skill_connections,
    skill_runtime_env,
)
from .._shared.skill_registry import (
    public_skill_catalog,
    public_skill_package,
    skill_dependency_graph,
)
from .._views.skill_marketplace import (
    marketplace_view,
    skill_error_view,
    skill_package_view,
)


async def handle_skills(ctx):
    """Authenticate, orchestrate Skill Models, and select one JSON View."""
    identity = require_user(ctx)
    state = await load_intelligence_state(
        getattr(getattr(ctx, "store", None), "langgraph_store", None),
        str(identity["user_id"]),
    )
    preferences = effective_skill_preferences(
        identity,
        state.get("skill_preferences"),
    )
    skills = decorate_catalog(
        public_skill_catalog(skill_runtime_env(
            getattr(ctx, "env", {}) or {},
            state,
        )),
        identity=identity,
        preferences=preferences,
    )
    body = getattr(getattr(ctx, "request", None), "body", None) or {}
    if str(body.get("operation") or "") == "package":
        skill_id = str(body.get("skill_id") or "")
        if not downloadable_skill(skills, skill_id):
            return skill_error_view(
                "Only installed Skills can be downloaded",
                code="SKILL_NOT_INSTALLED",
                status=403,
            )
        return skill_package_view(public_skill_package(skill_id))
    return marketplace_view(
        skills=skills,
        preferences=preferences,
        entitlements=public_entitlements(identity),
        dependency_graph=skill_dependency_graph(),
        component_api=public_component_api(),
        connections=public_skill_connections(state),
        identity=marketplace_identity(identity),
    )
