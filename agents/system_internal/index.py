"""Thin EdgeOne route adapter for the system controller."""

from .._controllers.system_controller import handler as handle_system


async def handler(ctx):
    return await handle_system(ctx)
