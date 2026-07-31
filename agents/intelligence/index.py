"""EdgeOne route adapter for the intelligence MVC controller."""

from __future__ import annotations

from .._controllers.intelligence_controller import handler as handle_intelligence


async def handler(ctx):
    return await handle_intelligence(ctx)
