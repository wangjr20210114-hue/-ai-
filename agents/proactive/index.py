"""Thin EdgeOne route adapter for the proactive controller."""

from .._controllers.proactive_controller import handler as handle_proactive


async def handler(ctx):
    return await handle_proactive(ctx)
