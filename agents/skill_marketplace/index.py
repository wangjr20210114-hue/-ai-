"""Non-reserved EdgeOne route adapter for the Skill marketplace Controller."""

from __future__ import annotations

from .._controllers.skills_controller import handle_skills


async def handler(ctx):
    return await handle_skills(ctx)
