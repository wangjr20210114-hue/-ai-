"""Thin EdgeOne route adapter for the routes controller."""

from .._controllers.routes_controller import handler as handle_routes


async def handler(ctx):
    return await handle_routes(ctx)
