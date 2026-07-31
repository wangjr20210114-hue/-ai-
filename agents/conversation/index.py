"""Thin EdgeOne route adapter for the conversation controller."""

from .._controllers.conversation_controller import handler as handle_conversation


async def handler(ctx):
    return await handle_conversation(ctx)
