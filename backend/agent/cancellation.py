"""Explicit cancellation primitives for long-running Agent work."""
from __future__ import annotations

import asyncio


class AgentCancelledError(asyncio.CancelledError):
    """Raised only when the user or an authorized API explicitly cancels a Run."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise AgentCancelledError("run cancelled by user")


class RunCancellationService:
    """Process-local token registry paired with persistent Run cancellation."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, run_id: str) -> CancellationToken:
        async with self._lock:
            token = self._tokens.get(run_id)
            if token is None:
                token = CancellationToken()
                self._tokens[run_id] = token
            return token

    async def cancel(self, run_id: str) -> bool:
        async with self._lock:
            token = self._tokens.get(run_id)
            if token is None:
                return False
            token.cancel()
            return True

    async def release(self, run_id: str) -> None:
        async with self._lock:
            self._tokens.pop(run_id, None)
