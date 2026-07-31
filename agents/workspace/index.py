"""Thin EdgeOne route adapter for the workspace controller."""

from .._controllers.workspace_controller import handler as handle_workspace


async def handler(ctx):
    return await handle_workspace(ctx)
