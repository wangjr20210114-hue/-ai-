"""Small Makers Blob pointers for listing native conversations.

Conversation messages and checkpoints remain in the Makers Conversation and
Agent stores.  The pointer only compensates for deployed runtimes whose native
``list_conversations(user_id=...)`` index returns an empty page after a
successful append.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from .identity import tenant_storage_prefix


POINTER_PATH = "conversation-index/v1/"
_SCOPED_ID = re.compile(r"^yb7_[0-9a-f]{32}$", re.IGNORECASE)


def conversation_pointer_key(user_id: str, conversation_id: str) -> str:
    scoped_id = str(conversation_id or "").strip()
    if not _SCOPED_ID.fullmatch(scoped_id):
        raise ValueError("Invalid scoped conversation id")
    return f"{tenant_storage_prefix(user_id)}{POINTER_PATH}{scoped_id}.json"


async def persist_conversation_pointer(
    user_id: str,
    tenant_id: str,
    conversation_id: str,
    client_conversation_id: str,
    *,
    title: str = "",
    message_count: int = 0,
    store: Any = None,
    now_ms: int | None = None,
    only_if_missing: bool = False,
) -> dict[str, Any] | None:
    """Upsert one tenant-scoped pointer without making chat persistence depend on it."""
    try:
        key = conversation_pointer_key(user_id, conversation_id)
        if store is None:
            from pages_blob import get_store

            store = get_store("yuanbao-files", consistency="strong")
        existing = await store.get(key, type="json", consistency="strong")
        if not isinstance(existing, dict):
            existing = {}
        existing_metadata = existing.get("metadata")
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        if (
            only_if_missing
            and str(existing.get("conversationId") or "") == str(conversation_id)
            and str(existing_metadata.get("owner_user_id") or "") == str(user_id)
            and str(existing_metadata.get("tenant_id") or "") == str(tenant_id)
        ):
            return existing
        now = int(now_ms or time.time() * 1000)
        try:
            created_at = int(existing.get("createdAt") or now)
        except (TypeError, ValueError):
            created_at = now
        record = {
            "schemaVersion": 1,
            "conversationId": str(conversation_id),
            "createdAt": created_at,
            "lastMessageAt": now,
            "messageCount": max(
                int(existing.get("messageCount") or 0),
                max(0, int(message_count or 0)),
            ),
            "metadata": {
                "client_conversation_id": str(client_conversation_id or ""),
                "owner_user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "title": str(title or existing_metadata.get("title") or "历史对话"),
            },
        }
        await store.set_json(key, record, cache_control="private, no-store")
        return record
    except ModuleNotFoundError as exc:
        if exc.name == "pages_blob":
            # EdgeOne injects this official SDK into deployed Agent builds;
            # plain local unit-test environments intentionally do not install it.
            return None
        raise
    except Exception:
        logging.exception("maker conversation pointer write failed conversation=%s", conversation_id)
        return None
