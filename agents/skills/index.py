"""Read-only installed Skill catalog and EdgeOne package entry point."""

from __future__ import annotations

from .._shared.auth import require_user
from .._shared.intelligence import load_intelligence_state, skill_runtime_env
from .._shared.skill_registry import public_skill_catalog


async def handler(ctx):
    identity = require_user(ctx)
    state = await load_intelligence_state(
        getattr(getattr(ctx, "store", None), "langgraph_store", None),
        str(identity["user_id"]),
    )
    return {
        "skills": public_skill_catalog(skill_runtime_env(
            getattr(ctx, "env", {}) or {},
            state,
        )),
    }
