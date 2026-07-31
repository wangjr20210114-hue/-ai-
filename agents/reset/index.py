"""Thin EdgeOne route adapter for the reset controller."""

from .._controllers.reset_controller import handler as handle_reset


async def handler(ctx):
    return await handle_reset(ctx)
