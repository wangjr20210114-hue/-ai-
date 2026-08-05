"""Bounded public-stream journal persisted through the native Maker Store."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from ..._infrastructure.makers.presentation_repository import (
    save_presentation_snapshot,
)


SNAPSHOT_INTERVAL_SECONDS = 0.45
SEARCH_ACTIVITIES = frozenset({"web_search", "paper_search", "place_search"})


def _timestamp_ms(value: Any, fallback: int | None = None) -> int:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        numeric = 0
    if numeric > 0:
        if numeric < 100_000_000_000:
            return numeric * 1000
        if numeric > 10_000_000_000_000:
            return round(numeric / 1000)
        return numeric
    return int(fallback or time.time() * 1000)


def normalize_public_turn_started_at(
    client_value: Any,
    server_value: Any = None,
    *,
    now_ms: int | None = None,
) -> int:
    """Bound an untrusted client clock around the Maker admission time."""
    now = int(now_ms or time.time() * 1000)
    server_started_at = _timestamp_ms(server_value, now)
    client_started_at = _timestamp_ms(client_value, server_started_at)
    if now - 86_400_000 <= client_started_at <= now + 60_000:
        return client_started_at
    return server_started_at


def _json_payload(frame: bytes) -> dict[str, Any] | None:
    try:
        text = frame.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        return None
    data = "\n".join(
        line[5:].strip()
        for line in text.splitlines()
        if line.startswith("data:")
    )
    if not data or data == "[DONE]":
        return None
    try:
        value = json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _merge_progress(
    current: list[dict[str, Any]],
    incoming: dict[str, Any],
) -> list[dict[str, Any]]:
    stage = str(incoming.get("stage") or "")
    activity = str(incoming.get("activity") or "general")
    if not stage:
        return current
    key = (stage, activity)
    output = [
        item for item in current
        if (str(item.get("stage") or ""), str(item.get("activity") or "general")) != key
    ]
    return [*output, dict(incoming)][-12:]


class PresentationJournalQueue:
    """Async queue that also checkpoints a compact public UI projection.

    The response queue remains the fast path. At a bounded cadence, the same
    already-public events are projected into Maker Store so a new browser
    transport can resume without replaying model work or exposing reasoning.
    """

    def __init__(
        self,
        *,
        store: Any,
        conversation_id: str,
        run_id: str,
        client_message_id: str,
        turn_started_at: int | float | str | None = None,
    ) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._store = store
        self._conversation_id = conversation_id
        self._run_id = run_id
        self._revision = 0
        self._dirty = False
        self._last_saved_at = 0.0
        self._scheduled_flush: asyncio.Task | None = None
        started_at = _timestamp_ms(turn_started_at)
        self._snapshot: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "client_message_id": str(client_message_id or ""),
            "revision": 0,
            "updated_at": started_at,
            "turn_started_at": started_at,
            "search_selected": False,
            "active_activity": "general",
            "content": "",
            "progress": [],
            "workspace_actions": [],
        }

    @property
    def turn_started_at(self) -> int:
        return int(self._snapshot["turn_started_at"])

    @property
    def search_selected(self) -> bool:
        return bool(self._snapshot.get("search_selected"))

    async def get(self) -> Any:
        return await self._queue.get()

    async def put(self, item: Any) -> None:
        # Deliver to the current subscriber before performing a durable write.
        await self._queue.put(item)
        if isinstance(item, bytes):
            payload = _json_payload(item)
            if payload is not None and self._apply(payload):
                await self._persist_if_due()
            return
        # The completion sentinel is the final flush boundary.
        if self._scheduled_flush is not None and not self._scheduled_flush.done():
            self._scheduled_flush.cancel()
            self._scheduled_flush = None
        await self.flush()

    def _apply(self, event: dict[str, Any]) -> bool:
        now_ms = int(time.time() * 1000)
        event_type = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        changed = True
        if event_type == "ai_response":
            self._snapshot["content"] += str(event.get("content") or "")
        elif event_type == "ai_response_reset":
            self._snapshot["content"] = ""
        elif event_type == "progress_event":
            progress_payload = {**payload, "updated_at": now_ms}
            self._snapshot["progress"] = _merge_progress(
                self._snapshot.get("progress") or [], progress_payload,
            )
            activity = str(payload.get("activity") or "general")
            if str(payload.get("status") or "") == "active":
                self._snapshot["active_activity"] = activity
            if activity in SEARCH_ACTIVITIES:
                self._snapshot["search_selected"] = True
                self._snapshot.setdefault(
                    "search_started_at", self._snapshot["turn_started_at"],
                )
        elif event_type == "search_results":
            self._snapshot["search_results"] = dict(payload)
            self._snapshot["search_selected"] = True
            self._snapshot.setdefault(
                "search_started_at", self._snapshot["turn_started_at"],
            )
        elif event_type == "search_media":
            self._snapshot["search_media"] = dict(payload)
        elif event_type == "paper_results":
            self._snapshot["papers"] = dict(payload)
        elif event_type in {"map_action", "calendar_action", "side_effect_action"}:
            action = payload.get("action")
            if not isinstance(action, dict) or not str(action.get("id") or ""):
                return False
            actions = [
                item for item in (self._snapshot.get("workspace_actions") or [])
                if str(item.get("id") or "") != str(action.get("id") or "")
            ]
            self._snapshot["workspace_actions"] = [*actions, dict(action)][-16:]
        elif event_type == "clarification_action":
            clarification = payload.get("clarification")
            if not isinstance(clarification, dict):
                return False
            self._snapshot["clarification"] = dict(clarification)
        elif event_type == "follow_ups":
            self._snapshot["follow_ups"] = [
                str(item) for item in (payload.get("items") or []) if str(item)
            ][:3]
        elif event_type == "experience_hint":
            self._snapshot["experience_hints"] = list(payload.get("items") or [])[:4]
        elif event_type == "error_message":
            self._snapshot["error"] = str(event.get("content") or "")
        elif event_type == "answer_complete":
            self._snapshot["active_activity"] = "general"
            if self._snapshot.get("search_selected"):
                self._snapshot["search_completed_at"] = now_ms
        else:
            changed = False
        if changed:
            self._revision += 1
            self._snapshot.update({
                "revision": self._revision,
                "updated_at": now_ms,
            })
            self._dirty = True
        return changed

    async def _persist_if_due(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_saved_at
        if elapsed < SNAPSHOT_INTERVAL_SECONDS:
            if self._scheduled_flush is None or self._scheduled_flush.done():
                self._scheduled_flush = asyncio.create_task(
                    self._flush_after(SNAPSHOT_INTERVAL_SECONDS - elapsed)
                )
            return
        await self.flush()

    async def _flush_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            await self.flush()
        finally:
            self._scheduled_flush = None

    async def flush(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        self._last_saved_at = time.monotonic()
        await save_presentation_snapshot(
            self._store,
            self._conversation_id,
            self._run_id,
            self._snapshot,
        )


def presentation_queue_for_turn(
    *,
    store: Any,
    conversation_id: str,
    run_id: str,
    body: dict[str, Any],
    run_state: dict[str, Any],
) -> PresentationJournalQueue:
    client_message = body.get("client_message")
    return PresentationJournalQueue(
        store=store,
        conversation_id=conversation_id,
        run_id=run_id,
        client_message_id=str(body.get("client_message_id") or ""),
        turn_started_at=normalize_public_turn_started_at(
            client_message.get("ts") if isinstance(client_message, dict) else None,
            run_state.get("started_at"),
        ),
    )
