"""Thin EdgeOne route adapter for the messages controller."""

from .._controllers.messages_controller import handler as handle_messages


async def handler(ctx):
    return await handle_messages(ctx)
