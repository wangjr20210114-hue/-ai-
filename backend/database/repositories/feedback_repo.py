"""User feedback persistence with optional client idempotency keys."""
from __future__ import annotations

import json
import time
import uuid
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


async def record_feedback(
    *,
    run_id: str | None,
    action_id: str | None,
    feedback_action: str,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    client_feedback_id: str = "",
) -> dict[str, Any]:
    if feedback_action not in {"helpful", "unhelpful", "dismissed", "corrected"}:
        raise ValueError("invalid feedback action")
    db = await get_db()
    feedback_id = f"feedback-{uuid.uuid4().hex[:16]}"
    now = time.time()
    await db.execute(
        "INSERT OR IGNORE INTO feedback_records(id,user_id,run_id,action_id,feedback_action,reason,metadata,created_at,client_feedback_id) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            feedback_id,
            LOCAL_USER_ID,
            run_id,
            action_id,
            feedback_action,
            reason,
            json.dumps({"schema_version": 1, **(metadata or {})}, ensure_ascii=False),
            now,
            client_feedback_id,
        ),
    )
    if client_feedback_id:
        cursor = await db.execute(
            "SELECT * FROM feedback_records WHERE user_id=? AND client_feedback_id=?",
            (LOCAL_USER_ID, client_feedback_id),
        )
    else:
        cursor = await db.execute("SELECT * FROM feedback_records WHERE id=?", (feedback_id,))
    row = await cursor.fetchone()
    await db.commit()
    if row is None:
        raise RuntimeError("feedback persistence failed")
    return _decode(row)


async def list_feedback(
    *,
    run_id: str | None = None,
    action_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    db = await get_db()
    conditions = ["user_id=?"]
    params: list[Any] = [LOCAL_USER_ID]
    if run_id:
        conditions.append("run_id=?")
        params.append(run_id)
    if action_id:
        conditions.append("action_id=?")
        params.append(action_id)
    params.append(max(1, min(limit, 500)))
    cursor = await db.execute(
        f"SELECT * FROM feedback_records WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    )
    return [_decode(row) for row in await cursor.fetchall()]


async def count_recent_negative_feedback(source_label: str, since: float) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM feedback_records WHERE user_id=? AND feedback_action IN ('unhelpful','dismissed') "
        "AND created_at>=? AND json_extract(metadata,'$.source_label')=?",
        (LOCAL_USER_ID, since, source_label),
    )
    row = await cursor.fetchone()
    return int(row[0] if row else 0)
