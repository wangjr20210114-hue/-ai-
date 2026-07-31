"""Thin EdgeOne route adapter for the stop controller."""

from .._controllers.stop_controller import handler as handle_stop


async def handler(ctx):
    return await handle_stop(ctx)
