"""Thin EdgeOne route adapter for the places controller."""

from .._controllers.places_controller import handler as handle_places


async def handler(ctx):
    return await handle_places(ctx)
