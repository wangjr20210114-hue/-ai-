"""通用日程 CRUD 仓储。"""
from __future__ import annotations

import json
import time

from database.connection import get_db
from models.schemas import ScheduleItem


async def save_schedule(item: ScheduleItem) -> None:
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO schedules"
        "(id, session_id, title, category, start_time, duration_minutes,"
        " duration_days, location, description, markdown_content, extra, done,"
        " created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            item.id,
            item.session_id,
            item.title,
            item.category,
            item.start_time,
            item.duration_minutes,
            item.duration_days,
            item.location,
            item.description,
            item.markdown_content,
            json.dumps(item.extra, ensure_ascii=False),
            1 if item.done else 0,
            item.created_at,
            item.updated_at,
        ),
    )
    await db.commit()


async def update_schedule(item: ScheduleItem) -> None:
    item.updated_at = time.time()
    await save_schedule(item)


async def delete_schedule(schedule_id: str) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    await db.commit()
    return cur.rowcount > 0


async def get_schedule(schedule_id: str) -> ScheduleItem | None:
    db = await get_db()
    cur = await db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    return _row_to_item(row)


async def list_schedules(session_id: str) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM schedules WHERE session_id=? ORDER BY "
        "CASE WHEN start_time > 0 THEN start_time ELSE 9999999999 END ASC, "
        "created_at DESC",
        (session_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def toggle_done(schedule_id: str, done: bool) -> bool:
    db = await get_db()
    cur = await db.execute(
        "UPDATE schedules SET done=?, updated_at=? WHERE id=?",
        (1 if done else 0, time.time(), schedule_id),
    )
    await db.commit()
    return cur.rowcount > 0


async def check_conflict(
    session_id: str, start_time: float, duration_minutes: int, exclude_id: str = ""
) -> list[dict]:
    """检查时间冲突：返回与 [start_time, start_time+duration) 有重叠的日程列表。

    多天日程（duration_days>0）也按天检测冲突。
    """
    if start_time <= 0 or duration_minutes <= 0:
        return []

    end_time = start_time + duration_minutes * 60
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM schedules WHERE session_id=? AND start_time > 0 "
        "AND duration_minutes > 0",
        (session_id,),
    )
    rows = await cur.fetchall()

    conflicts = []
    for row in rows:
        if row["id"] == exclude_id:
            continue
        r_start = row["start_time"]
        r_end = r_start + row["duration_minutes"] * 60
        # 区间重叠检测
        if start_time < r_end and end_time > r_start:
            conflicts.append(dict(row))
    return conflicts


def _row_to_item(row) -> ScheduleItem:
    extra_raw = row["extra"] or "{}"
    try:
        extra = json.loads(extra_raw)
    except (json.JSONDecodeError, TypeError):
        extra = {}
    return ScheduleItem(
        id=row["id"],
        session_id=row["session_id"],
        title=row["title"],
        category=row["category"],
        start_time=row["start_time"],
        duration_minutes=row["duration_minutes"],
        duration_days=row["duration_days"],
        location=row["location"],
        description=row["description"],
        markdown_content=row["markdown_content"],
        extra=extra,
        done=bool(row["done"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
