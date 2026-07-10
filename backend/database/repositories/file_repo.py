"""Persistent file metadata repository."""
from __future__ import annotations

import json
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(item.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        item["metadata"] = {}
    return item


async def get_file(file_id: str, owner_id: str = LOCAL_USER_ID) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM files WHERE id=? AND owner_id=?", (file_id, owner_id))
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def get_file_by_hash(sha256: str, owner_id: str = LOCAL_USER_ID) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM files WHERE sha256=? AND owner_id=?", (sha256, owner_id))
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def save_file(item: dict[str, Any]) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO files(id, owner_id, conversation_id, sha256, original_name, stored_name, storage_path, mime_type, size_bytes, page_count, extracted_text, metadata, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "conversation_id=excluded.conversation_id, sha256=excluded.sha256, "
        "original_name=excluded.original_name, stored_name=excluded.stored_name, "
        "storage_path=excluded.storage_path, mime_type=excluded.mime_type, "
        "size_bytes=excluded.size_bytes, page_count=excluded.page_count, "
        "extracted_text=excluded.extracted_text, metadata=excluded.metadata",
        (
            item["id"], item["owner_id"], item.get("conversation_id"), item["sha256"],
            item["original_name"], item["stored_name"], item["storage_path"], item["mime_type"],
            item["size_bytes"], item["page_count"], item.get("extracted_text", ""),
            json.dumps(item.get("metadata", {}), ensure_ascii=False), item["created_at"],
        ),
    )
    await db.commit()
