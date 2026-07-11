"""Explicit, user-confirmed memory repository with optimistic versions."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID


class MemoryConflict(ValueError):
    """Memory proposal or version no longer matches persisted state."""


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("candidate_json", "value_json"):
        if key in item:
            try:
                item[key] = json.loads(item.get(key) or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {}
    return item


async def create_proposal(source_message_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    memory_key = str(candidate.get("key") or "").strip()
    if not memory_key:
        raise ValueError("memory candidate key is required")
    db = await get_db()
    now = time.time()
    proposal_id = f"memory-proposal-{uuid.uuid4().hex[:16]}"
    normalized = {
        "schema_version": 1,
        **candidate,
        "key": memory_key,
        "sensitivity": str(candidate.get("sensitivity") or "normal"),
    }
    await db.execute(
        "INSERT INTO memory_proposals(id,user_id,source_message_id,candidate_json,status,version,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            proposal_id,
            LOCAL_USER_ID,
            source_message_id,
            json.dumps(normalized, ensure_ascii=False),
            "awaiting_confirmation",
            1,
            now,
            now,
        ),
    )
    await db.commit()
    result = await get_proposal(proposal_id)
    if result is None:
        raise RuntimeError("memory proposal persistence failed")
    return result


async def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM memory_proposals WHERE id=? AND user_id=?", (proposal_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def list_proposals(status: str | None = "awaiting_confirmation") -> list[dict[str, Any]]:
    db = await get_db()
    if status:
        cursor = await db.execute(
            "SELECT * FROM memory_proposals WHERE user_id=? AND status=? ORDER BY created_at DESC",
            (LOCAL_USER_ID, status),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM memory_proposals WHERE user_id=? ORDER BY created_at DESC",
            (LOCAL_USER_ID,),
        )
    return [_decode(row) for row in await cursor.fetchall()]


async def confirm_proposal(proposal_id: str, version: int) -> tuple[dict[str, Any], dict[str, Any]]:
    db = await get_db()
    now = time.time()
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            "SELECT * FROM memory_proposals WHERE id=? AND user_id=?", (proposal_id, LOCAL_USER_ID)
        )
        row = await cursor.fetchone()
        if row is None:
            raise MemoryConflict("memory proposal not found")
        if int(row["version"]) != version:
            raise MemoryConflict("memory proposal version conflict")
        candidate = json.loads(row["candidate_json"] or "{}")
        memory_key = str(candidate.get("key") or "").strip()
        if not memory_key:
            raise MemoryConflict("memory proposal key is missing")

        memory_cursor = await db.execute(
            "SELECT * FROM memories WHERE user_id=? AND memory_key=?",
            (LOCAL_USER_ID, memory_key),
        )
        existing = await memory_cursor.fetchone()
        if row["status"] == "confirmed":
            await db.commit()
            if existing is None:
                raise RuntimeError("confirmed memory is missing")
            return _decode(row), _decode(existing)
        if row["status"] != "awaiting_confirmation":
            raise MemoryConflict("memory proposal cannot be confirmed")

        expected_memory_version = candidate.get("expected_memory_version")
        if expected_memory_version is not None:
            actual_version = int(existing["version"]) if existing else 0
            if actual_version != int(expected_memory_version):
                raise MemoryConflict("memory value changed after proposal creation")

        if existing is None:
            memory_id = f"memory-{uuid.uuid4().hex[:16]}"
            await db.execute(
                "INSERT INTO memories(id,user_id,memory_key,value_json,confidence,source_message_id,created_at,updated_at,version,sensitivity) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    memory_id,
                    LOCAL_USER_ID,
                    memory_key,
                    json.dumps(candidate.get("value"), ensure_ascii=False),
                    float(candidate.get("confidence") or 1.0),
                    row["source_message_id"],
                    now,
                    now,
                    1,
                    str(candidate.get("sensitivity") or "normal"),
                ),
            )
        else:
            await db.execute(
                "UPDATE memories SET value_json=?,confidence=?,source_message_id=?,updated_at=?,"
                "version=version+1,sensitivity=? WHERE id=? AND user_id=?",
                (
                    json.dumps(candidate.get("value"), ensure_ascii=False),
                    float(candidate.get("confidence") or 1.0),
                    row["source_message_id"],
                    now,
                    str(candidate.get("sensitivity") or "normal"),
                    existing["id"],
                    LOCAL_USER_ID,
                ),
            )
        await db.execute(
            "UPDATE memory_proposals SET status='confirmed',updated_at=? WHERE id=?", (now, proposal_id)
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    proposal = await get_proposal(proposal_id)
    cursor = await db.execute(
        "SELECT * FROM memories WHERE user_id=? AND memory_key=?", (LOCAL_USER_ID, memory_key)
    )
    memory = await cursor.fetchone()
    if proposal is None or memory is None:
        raise RuntimeError("memory confirmation failed")
    return proposal, _decode(memory)


async def reject_proposal(proposal_id: str) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            "SELECT status FROM memory_proposals WHERE id=? AND user_id=?",
            (proposal_id, LOCAL_USER_ID),
        )
        row = await cursor.fetchone()
        if row is None:
            await db.commit()
            return None
        if row["status"] == "rejected":
            await db.commit()
            return await get_proposal(proposal_id)
        if row["status"] != "awaiting_confirmation":
            raise MemoryConflict("memory proposal cannot be rejected")
        await db.execute(
            "UPDATE memory_proposals SET status='rejected',updated_at=? WHERE id=?",
            (time.time(), proposal_id),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return await get_proposal(proposal_id)


async def list_memories() -> list[dict[str, Any]]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM memories WHERE user_id=? ORDER BY updated_at DESC", (LOCAL_USER_ID,)
    )
    return [_decode(row) for row in await cursor.fetchall()]


async def get_memory(memory_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM memories WHERE id=? AND user_id=?", (memory_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def update_memory(
    memory_id: str,
    *,
    value: Any,
    version: int,
    confidence: float | None = None,
    sensitivity: str | None = None,
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    assignments = ["value_json=?", "version=version+1", "updated_at=?"]
    params: list[Any] = [json.dumps(value, ensure_ascii=False), now]
    if confidence is not None:
        assignments.append("confidence=?")
        params.append(min(1.0, max(0.0, float(confidence))))
    if sensitivity is not None:
        assignments.append("sensitivity=?")
        params.append(str(sensitivity))
    params.extend([memory_id, LOCAL_USER_ID, version])
    cursor = await db.execute(
        f"UPDATE memories SET {','.join(assignments)} WHERE id=? AND user_id=? AND version=?",
        tuple(params),
    )
    if cursor.rowcount != 1:
        await db.rollback()
        if await get_memory(memory_id) is None:
            raise MemoryConflict("memory not found")
        raise MemoryConflict("memory version conflict")
    await db.commit()
    result = await get_memory(memory_id)
    if result is None:
        raise RuntimeError("memory disappeared after update")
    return result


async def delete_memory(memory_id: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM memories WHERE id=? AND user_id=?", (memory_id, LOCAL_USER_ID)
    )
    await db.commit()
    return cursor.rowcount == 1


async def clear_memories() -> int:
    db = await get_db()
    cursor = await db.execute("DELETE FROM memories WHERE user_id=?", (LOCAL_USER_ID,))
    await db.commit()
    return max(0, cursor.rowcount)
