"""EdgeOne route adapter for the Skill marketplace MVC controller."""

from __future__ import annotations

from .._controllers.skills_controller import handle_skills


async def handler(ctx):
    return await handle_skills(ctx)
