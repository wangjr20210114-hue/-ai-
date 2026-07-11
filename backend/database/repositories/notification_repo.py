"""Persistent notification inbox repository."""
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


async def create_notification(
    *,
    notification_type: str,
    title: str,
    body: str,
    dedup_key: str,
    run_id: str | None = None,
    event_id: str | None = None,
    action_id: str | None = None,
    reason: str = "",
    source_label: str = "Agent",
    priority: int = 0,
    metadata: dict[str, Any] | None = None,
    snoozed_until: float | None = None,
) -> tuple[dict[str, Any], bool]:
    db = await get_db()
    notification_id = f"notification-{uuid.uuid4().hex[:16]}"
    now = time.time()
    await db.execute(
        "INSERT OR IGNORE INTO notifications(id,user_id,run_id,event_id,type,title,body,reason,source_label,action_id,priority,dedup_key,metadata,created_at,snoozed_until) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            notification_id,
            LOCAL_USER_ID,
            run_id,
            event_id,
            notification_type,
            title[:200],
            body,
            reason,
            source_label,
            action_id,
            priority,
            dedup_key,
            json.dumps({"schema_version": 1, **(metadata or {})}, ensure_ascii=False),
            now,
            snoozed_until,
        ),
    )
    cursor = await db.execute("SELECT * FROM notifications WHERE dedup_key=?", (dedup_key,))
    row = await cursor.fetchone()
    await db.commit()
    if row is None:
        raise RuntimeError("notification persistence failed")
    return _decode(row), row["id"] == notification_id


async def list_notifications(
    *,
    since: float | None = None,
    include_dismissed: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    db = await get_db()
    conditions = ["user_id=?"]
    params: list[Any] = [LOCAL_USER_ID]
    if since is not None:
        conditions.append("created_at>?")
        params.append(since)
    if not include_dismissed:
        conditions.append("dismissed_at IS NULL")
    conditions.append("(snoozed_until IS NULL OR snoozed_until<=?)")
    params.append(time.time())
    params.append(max(1, min(limit, 500)))
    cursor = await db.execute(
        f"SELECT * FROM notifications WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    )
    return [_decode(row) for row in await cursor.fetchall()]


async def mark_read(notification_id: str) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute(
        "UPDATE notifications SET read_at=COALESCE(read_at, ?) WHERE id=? AND user_id=?",
        (time.time(), notification_id, LOCAL_USER_ID),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def dismiss(notification_id: str) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute(
        "UPDATE notifications SET dismissed_at=? WHERE id=? AND user_id=?",
        (time.time(), notification_id, LOCAL_USER_ID),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def snooze(notification_id: str, until: float) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute(
        "UPDATE notifications SET snoozed_until=? WHERE id=? AND user_id=?",
        (until, notification_id, LOCAL_USER_ID),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None

async def get_preferences() -> dict[str, Any]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM notification_preferences WHERE user_id=?", (LOCAL_USER_ID,)
    )
    row = await cursor.fetchone()
    if row is None:
        now = time.time()
        await db.execute(
            "INSERT INTO notification_preferences(user_id,updated_at) VALUES(?,?)",
            (LOCAL_USER_ID, now),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM notification_preferences WHERE user_id=?", (LOCAL_USER_ID,)
        )
        row = await cursor.fetchone()
    return dict(row)


async def update_preferences(**changes: Any) -> dict[str, Any]:
    allowed = {
        "quiet_hours_start",
        "quiet_hours_end",
        "daily_limit",
        "cooldown_seconds",
        "enabled",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return await get_preferences()
    await get_preferences()
    db = await get_db()
    assignments = ",".join(f"{key}=?" for key in values)
    params = list(values.values()) + [time.time(), LOCAL_USER_ID]
    await db.execute(
        f"UPDATE notification_preferences SET {assignments},updated_at=? WHERE user_id=?",
        tuple(params),
    )
    await db.commit()
    return await get_preferences()


async def count_notifications_since(since: float) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND created_at>=?",
        (LOCAL_USER_ID, since),
    )
    row = await cursor.fetchone()
    return int(row[0] if row else 0)


async def has_recent_notification(
    notification_type: str,
    source_label: str,
    since: float,
) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM notifications WHERE user_id=? AND type=? AND source_label=? "
        "AND created_at>=? LIMIT 1",
        (LOCAL_USER_ID, notification_type, source_label, since),
    )
    return await cursor.fetchone() is not None
