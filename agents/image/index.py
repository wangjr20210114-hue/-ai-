"""Thin EdgeOne route adapter for the image controller."""

from .._controllers.image_controller import handler as handle_image


async def handler(ctx):
    return await handle_image(ctx)
