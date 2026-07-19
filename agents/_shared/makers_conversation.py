"""Thin run-lifecycle metadata over the native Makers Conversation Store.

Message content and graph progress deliberately stay in the platform's
LangGraph checkpointer.  This module only gives the UI a small durable marker
for deciding whether it should keep polling that checkpoint after a refresh.
"""

from __future__ import annotations

import time
import re
from typing import Any


RUN_METADATA_KEY = "yuanbao_chat_run_v1"
RUNNING_STATES = {"running", "cancel_requested"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
STALE_AFTER_SECONDS = 35 * 60


def conversation_title(content: str) -> str:
    value = re.sub(r"\s+", " ", str(content or "")).strip().lstrip("#>*`- ")
    return (value[:32] + "…") if len(value) > 32 else (value or "新对话")


async def ensure_conversation_title(
    conversation_store: Any, conversation_id: str, content: str, user_id: str,
) -> None:
    if not hasattr(conversation_store, "get_conversation") or not hasattr(conversation_store, "update_conversation"):
        return
    conversation = await conversation_store.get_conversation(conversation_id=conversation_id)
    metadata = _field(conversation, "metadata", {}) or {}
    current = str(metadata.get("title") or "") if isinstance(metadata, dict) else ""
    if current in {"", "新对话", "历史对话"}:
        await conversation_store.update_conversation(
            conversation_id=conversation_id,
            metadata={"title": conversation_title(content), "owner_user_id": user_id},
        )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def read_chat_run(conversation_store: Any, conversation_id: str) -> dict[str, Any] | None:
    if not hasattr(conversation_store, "get_conversation"):
        return None
    try:
        conversation = await conversation_store.get_conversation(conversation_id=conversation_id)
    except Exception:
        return None
    metadata = _field(conversation, "metadata", {}) or {}
    run = metadata.get(RUN_METADATA_KEY) if isinstance(metadata, dict) else None
    return dict(run) if isinstance(run, dict) else None


async def write_chat_run(
    conversation_store: Any,
    conversation_id: str,
    *,
    run_id: str,
    status: str,
    error: str = "",
) -> dict[str, Any]:
    now = int(time.time())
    previous = await read_chat_run(conversation_store, conversation_id) or {}
    started_at = now if status == "running" else int(previous.get("started_at") or now)
    run = {
        "run_id": str(run_id or previous.get("run_id") or ""),
        "status": str(status),
        "error": str(error or ""),
        "started_at": started_at,
        "updated_at": now,
        "completed_at": now if status in TERMINAL_STATES else None,
    }
    if hasattr(conversation_store, "update_conversation"):
        try:
            # update_conversation performs the Makers-documented shallow merge,
            # so unrelated title/owner metadata is preserved by the platform.
            await conversation_store.update_conversation(
                conversation_id=conversation_id,
                metadata={RUN_METADATA_KEY: run},
            )
        except Exception:
            # The first user message may still be racing to create the native
            # conversation. The LangGraph checkpoint remains authoritative.
            pass
    return run


def public_chat_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return None
    return {
        key: run.get(key)
        for key in ("run_id", "status", "error", "started_at", "updated_at", "completed_at")
    }


def is_stale(run: dict[str, Any] | None, now: int | None = None) -> bool:
    if not isinstance(run, dict) or run.get("status") not in RUNNING_STATES:
        return False
    updated_at = int(run.get("updated_at") or run.get("started_at") or 0)
    return bool(updated_at and int(now or time.time()) - updated_at > STALE_AFTER_SECONDS)
