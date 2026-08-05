"""Thin EdgeOne adapter for reconnectable chat run state."""

from .._controllers.run_controller import handler as handle_run


async def handler(ctx):
    return await handle_run(ctx)
