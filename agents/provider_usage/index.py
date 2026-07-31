"""Thin EdgeOne route adapter for the provider usage controller."""

from .._controllers.provider_usage_controller import handler as handle_provider_usage


async def handler(ctx):
    return await handle_provider_usage(ctx)
