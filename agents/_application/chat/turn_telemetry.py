"""Turn performance telemetry backed by the Makers tracer."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any


class TurnTelemetry:
    """Record monotonic turn milestones without making tracing a dependency."""

    def __init__(
        self,
        tracer: Any,
        timings_ms: dict[str, int | bool],
        *,
        started_at: float | None = None,
        request_id: str = "",
    ) -> None:
        self.timings_ms = timings_ms
        self._started_at = time.monotonic() if started_at is None else started_at
        self._event = getattr(tracer, "event", None)
        self._request_id = str(request_id or "").strip()
        self._emitted_events: set[str] = set()

    def bind_request_id(self, request_id: str) -> None:
        """Bind the server-trusted Makers id once admission has completed."""
        clean = str(request_id or "").strip()
        if clean and not self._request_id:
            self._request_id = clean

    def elapsed_ms(self) -> int:
        return max(0, round((time.monotonic() - self._started_at) * 1000))

    def mark_once(self, name: str, *, elapsed_ms: int | None = None) -> bool:
        """Record the first occurrence of a public milestone."""
        if name in self.timings_ms:
            return False
        self.timings_ms[name] = (
            self.elapsed_ms() if elapsed_ms is None else max(0, int(elapsed_ms))
        )
        return True

    def emit(
        self,
        event_name: str,
        attributes: Mapping[str, Any] | None = None,
        *,
        once: bool = True,
    ) -> None:
        """Emit one non-blocking Makers trace event with the current timings."""
        if once and event_name in self._emitted_events:
            return
        if once:
            self._emitted_events.add(event_name)
        if not callable(self._event):
            return
        payload = {
            f"chat.timing.{key}": value
            for key, value in self.timings_ms.items()
            if isinstance(value, (bool, int))
        }
        if self._request_id:
            payload["chat.request_id"] = self._request_id
        payload.update(dict(attributes or {}))
        try:
            self._event(event_name, payload)
        except Exception as exc:
            # Observability must never change the public answer or durable run.
            logging.warning("Makers chat trace event failed event=%s error=%s", event_name, exc)

    def mark_and_emit(
        self,
        milestone: str,
        event_name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> bool:
        marked = self.mark_once(milestone)
        if marked:
            self.emit(event_name, attributes)
        return marked

    def request_received(self) -> None:
        self.mark_once("request_received", elapsed_ms=0)
        self.emit("chat.request_received")

    def pre_graph(self) -> None:
        self.emit("chat.pre_graph_timing")

    def answer_first_token(self) -> None:
        self.mark_and_emit("answer_first_token", "chat.answer_first_token")

    def answer_completed(self) -> None:
        self.mark_and_emit("answer_completed", "chat.answer_completed")

    def media_completed(
        self,
        outcome: str,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        attributes = {"chat.media.outcome": outcome}
        attributes.update({
            f"chat.media.{key}": value
            for key, value in dict(diagnostics or {}).items()
            if isinstance(value, (int, str))
        })
        self.mark_and_emit(
            "media_completed",
            "chat.media_completed",
            attributes,
        )

    def settle(self, outcome: str) -> None:
        self.mark_and_emit(
            "request_settled",
            "chat.request_settled",
            {"chat.outcome": outcome},
        )
