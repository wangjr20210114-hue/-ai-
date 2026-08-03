"""Thin EdgeOne route adapter for the chat turn application."""

from .._controllers.chat_controller import ChatTurnController


async def handler(ctx):
    return await ChatTurnController(ctx).handle()
__all__ = ("handler",)
