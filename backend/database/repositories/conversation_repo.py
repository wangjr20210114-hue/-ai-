"""Persistent local identity, conversations, and UI messages."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from database.connection import get_db

LOCAL_USER_ID = "local-user"
DEFAULT_CONVERSATION_ID = "default-conversation"


async def ensure_local_identity() -> None:
    db = await get_db()
    now = time.time()
    await db.execute(
        "INSERT OR IGNORE INTO users(id, display_name, timezone, created_at, updated_at) VALUES(?,?,?,?,?)",
        (LOCAL_USER_ID, "我", "Asia/Shanghai", now, now),
    )
    await db.execute(
        "INSERT OR IGNORE INTO conversations(id, user_id, title, summary, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (DEFAULT_CONVERSATION_ID, LOCAL_USER_ID, "默认会话", "", now, now),
    )
    await db.commit()


async def create_conversation(title: str = "新会话") -> dict[str, Any]:
    await ensure_local_identity()
    db = await get_db()
    conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
    now = time.time()
    await db.execute(
        "INSERT INTO conversations(id, user_id, title, summary, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (conversation_id, LOCAL_USER_ID, title[:80] or "新会话", "", now, now),
    )
    await db.commit()
    return {"id": conversation_id, "user_id": LOCAL_USER_ID, "title": title[:80] or "新会话", "summary": "", "created_at": now, "updated_at": now}


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM conversations WHERE id=? AND user_id=?",
        (conversation_id, LOCAL_USER_ID),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_conversations() -> list[dict[str, Any]]:
    await ensure_local_identity()
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
        (LOCAL_USER_ID,),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def save_message(
    conversation_id: str,
    message_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    created_at: float | None = None,
) -> dict[str, Any]:
    if role not in {"user", "ai", "system"}:
        raise ValueError("invalid message role")
    if await get_conversation(conversation_id) is None:
        raise ValueError("conversation not found")
    db = await get_db()
    ts = created_at or time.time()
    encoded = json.dumps(metadata or {}, ensure_ascii=False)
    await db.execute(
        "INSERT INTO messages(id, conversation_id, role, content, metadata, created_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET content=excluded.content, metadata=excluded.metadata",
        (message_id, conversation_id, role, content, encoded, ts),
    )
    await db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (time.time(), conversation_id))
    await db.commit()
    return {"id": message_id, "conversation_id": conversation_id, "role": role, "content": content, "metadata": metadata or {}, "created_at": ts}


async def list_messages(conversation_id: str, limit: int = 500) -> list[dict[str, Any]]:
    if await get_conversation(conversation_id) is None:
        return []
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC",
        (conversation_id, max(1, min(limit, 2000))),
    )
    items: list[dict[str, Any]] = []
    for row in await cursor.fetchall():
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["metadata"] = {}
        items.append(item)
    return items


async def history_lines(conversation_id: str, limit: int = 24) -> list[str]:
    result = []
    for message in await list_messages(conversation_id, limit):
        prefix = "用户: " if message["role"] == "user" else "AI(chat): "
        result.append(prefix + message["content"])
    return result
