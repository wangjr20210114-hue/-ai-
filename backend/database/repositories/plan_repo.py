"""旅游计划 CRUD 仓储。"""
from __future__ import annotations

import json
import time

from database.connection import get_db
from models.schemas import TravelPlan


async def save_plan(plan: TravelPlan) -> None:
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO travel_plans"
        "(id, session_id, title, departure, destination, days, travel_style,"
        " scenery_preference, budget, extra_notes, markdown_content, baike_info,"
        " created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            plan.id,
            plan.session_id,
            plan.title,
            plan.departure,
            plan.destination,
            plan.days,
            plan.travel_style,
            plan.scenery_preference,
            plan.budget,
            plan.extra_notes,
            plan.markdown_content,
            json.dumps(plan.baike_info, ensure_ascii=False),
            plan.created_at,
            plan.updated_at,
        ),
    )
    await db.commit()


async def update_plan(plan: TravelPlan) -> None:
    plan.updated_at = time.time()
    await save_plan(plan)


async def delete_plan(plan_id: str) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM travel_plans WHERE id=?", (plan_id,))
    await db.commit()
    return cur.rowcount > 0


async def get_plan(plan_id: str) -> TravelPlan | None:
    db = await get_db()
    cur = await db.execute("SELECT * FROM travel_plans WHERE id=?", (plan_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    return _row_to_plan(row)


async def list_plans(session_id: str) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM travel_plans WHERE session_id=? ORDER BY updated_at DESC",
        (session_id,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


def _row_to_plan(row) -> TravelPlan:
    baike_raw = row["baike_info"] or "{}"
    try:
        baike = json.loads(baike_raw)
    except (json.JSONDecodeError, TypeError):
        baike = {}
    return TravelPlan(
        id=row["id"],
        session_id=row["session_id"],
        title=row["title"],
        departure=row["departure"],
        destination=row["destination"],
        days=row["days"],
        travel_style=row["travel_style"],
        scenery_preference=row["scenery_preference"],
        budget=row["budget"],
        extra_notes=row["extra_notes"],
        markdown_content=row["markdown_content"],
        baike_info=baike,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
