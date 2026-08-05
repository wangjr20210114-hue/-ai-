"""Thin run-lifecycle repository over the native Makers Conversation Store.

Message content and graph progress deliberately stay in the platform's
LangGraph checkpointer.  This module only gives the UI a small durable marker
for deciding whether it should keep polling that checkpoint after a refresh.
"""

from __future__ import annotations

import time
import re
from typing import Any
from ..._application.i18n import text


RUN_METADATA_KEY = "yuanbao_chat_run_v1"
RUNNING_STATES = {"running", "cancel_requested"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
STALE_AFTER_SECONDS = 35 * 60
# `/messages` restores at most the product's bounded recent transcript.  Keep
# more tombstones than that window so a stopped turn cannot reappear after many
# later cancellations, while remaining comfortably inside Maker metadata.
DISCARDED_TURN_LIMIT = 120


def conversation_title(content: str, response_language: object = "zh-CN") -> str:
    value = re.sub(r"\s+", " ", str(content or "")).strip().lstrip("#>*`- ")
    return (value[:32] + "…") if len(value) > 32 else (
        value or text("conversation.new_title", response_language)
    )


async def ensure_conversation_title(
    conversation_store: Any, conversation_id: str, content: str, user_id: str,
    *,
    tenant_id: str = "",
    client_conversation_id: str = "",
    response_language: object = "zh-CN",
) -> None:
    if not hasattr(conversation_store, "get_conversation") or not hasattr(conversation_store, "update_conversation"):
        return
    conversation = await conversation_store.get_conversation(conversation_id=conversation_id)
    metadata = _field(conversation, "metadata", {}) or {}
    current = str(metadata.get("title") or "") if isinstance(metadata, dict) else ""
    updates = {
        "owner_user_id": str(user_id or ""),
        "tenant_id": str(tenant_id or ""),
        "client_conversation_id": str(client_conversation_id or ""),
    }
    default_titles = {
        "",
        *(
            text(key, language)
            for key in ("conversation.new_title", "conversation.history_title")
            for language in ("zh-CN", "zh-TW", "en", "cat-cute", "cat-cold")
        ),
    }
    if current in default_titles:
        updates["title"] = conversation_title(content, response_language)
    await conversation_store.update_conversation(
        conversation_id=conversation_id,
        metadata=updates,
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
    diagnostics: dict[str, Any] | None = None,
    client_message_id: str = "",
) -> dict[str, Any]:
    now = int(time.time())
    previous = await read_chat_run(conversation_store, conversation_id) or {}
    same_run = str(previous.get("run_id") or "") == str(run_id or "")
    resolved_client_message_id = str(
        client_message_id
        or (previous.get("client_message_id") if same_run else "")
        or ""
    )
    discarded_client_message_ids = list(dict.fromkeys(
        str(value)
        for value in (previous.get("discarded_client_message_ids") or [])
        if str(value)
    ))[-DISCARDED_TURN_LIMIT:]
    resolved_status = str(status)
    if (
        resolved_client_message_id
        and resolved_client_message_id in discarded_client_message_ids
    ):
        resolved_status = "cancelled"
    started_at = (
        now
        if resolved_status == "running"
        else int(previous.get("started_at") or now)
    )
    run = {
        "run_id": str(run_id or previous.get("run_id") or ""),
        "client_message_id": resolved_client_message_id,
        "status": resolved_status,
        "error": str(error or ""),
        "diagnostics": dict(diagnostics or {}),
        "started_at": started_at,
        "updated_at": now,
        "completed_at": now if resolved_status in TERMINAL_STATES else None,
        "discarded_client_message_ids": discarded_client_message_ids,
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


async def discard_chat_turn(
    conversation_store: Any,
    conversation_id: str,
    *,
    client_message_id: str = "",
) -> tuple[dict[str, Any], bool]:
    """Persist a user cancellation tombstone in the native conversation.

    Maker's abort primitive stops live compute.  The tombstone is the durable
    presentation boundary: checkpoint tokens from that turn remain useful to
    the platform for diagnostics, but no client may render them after reload.
    """
    now = int(time.time())
    previous = await read_chat_run(conversation_store, conversation_id) or {}
    current_client_id = str(previous.get("client_message_id") or "")
    explicit_client_id = str(client_message_id or "")
    requested_client_id = str(
        explicit_client_id
        or (
            current_client_id
            if previous.get("status") in RUNNING_STATES
            else ""
        )
    )
    matches_current = bool(
        (
            requested_client_id
            and (not current_client_id or requested_client_id == current_client_id)
        )
        or (
            not explicit_client_id
            and previous.get("status") in RUNNING_STATES
        )
    )
    active_match = bool(
        matches_current and previous.get("status") in RUNNING_STATES
    )
    discarded = list(dict.fromkeys([
        *(
            str(value)
            for value in (previous.get("discarded_client_message_ids") or [])
            if str(value)
        ),
        *([requested_client_id] if requested_client_id else []),
    ]))[-DISCARDED_TURN_LIMIT:]
    run = {
        **previous,
        "discarded_client_message_ids": discarded,
        "updated_at": now,
    }
    if matches_current:
        run.update({
            "status": "cancelled",
            "error": "",
            "diagnostics": {},
            "completed_at": now,
        })
    if hasattr(conversation_store, "update_conversation"):
        try:
            await conversation_store.update_conversation(
                conversation_id=conversation_id,
                metadata={RUN_METADATA_KEY: run},
            )
        except Exception:
            pass
    return run, active_match


def public_chat_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return None
    return {
        key: run.get(key)
        for key in (
            "run_id", "client_message_id", "status", "error", "diagnostics",
            "started_at", "updated_at", "completed_at",
        )
    }


def is_stale(run: dict[str, Any] | None, now: int | None = None) -> bool:
    if not isinstance(run, dict) or run.get("status") not in RUNNING_STATES:
        return False
    updated_at = int(run.get("updated_at") or run.get("started_at") or 0)
    return bool(updated_at and int(now or time.time()) - updated_at > STALE_AFTER_SECONDS)
