"""Read-only installed Skill catalog and EdgeOne package entry point."""

from __future__ import annotations

from .._shared.auth import require_user
from .._shared.skill_registry import public_skill_catalog


async def handler(ctx):
    require_user(ctx)
    return {
        "skills": public_skill_catalog(getattr(ctx, "env", {}) or {}),
    }
