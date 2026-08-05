"""Controller for one authenticated chat turn."""

from .._application.chat.turn_service import ChatTurnService


class ChatTurnController:
    """Translate the EdgeOne route context into one application service call."""

    def __init__(self, ctx) -> None:
        self._service = ChatTurnService(ctx)

    async def handle(self):
        return await self._service.handle()


__all__ = ("ChatTurnController",)
