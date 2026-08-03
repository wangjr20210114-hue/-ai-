"""Thin application controller for an authenticated chat turn."""

from .turn_service import ChatTurnService


class ChatTurnController:
    """Own route-to-use-case delegation for one authenticated chat turn."""

    def __init__(self, ctx) -> None:
        self._service = ChatTurnService(ctx)

    async def handle(self):
        return await self._service.handle()
__all__ = ("ChatTurnController",)
