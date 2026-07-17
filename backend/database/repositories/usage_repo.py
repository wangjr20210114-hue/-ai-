"""Usage and cost persistence."""
from __future__ import annotations

import time
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID


async def record_usage(
    *,
    run_id: str | None,
    provider: str,
    operation: str,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    units: float = 0,
    estimated_cost: float = 0,
    currency: str = "CNY",
    status: str = "succeeded",
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    cursor = await db.execute(
        "INSERT INTO usage_records(user_id,run_id,provider,operation,model,input_tokens,output_tokens,units,estimated_cost,currency,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            LOCAL_USER_ID,
            run_id,
            provider,
            operation,
            model,
            max(0, input_tokens),
            max(0, output_tokens),
            max(0.0, units),
            max(0.0, estimated_cost),
            currency,
            status,
            now,
        ),
    )
    await db.commit()
    return {
        "id": cursor.lastrowid,
        "run_id": run_id,
        "provider": provider,
        "operation": operation,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "units": units,
        "estimated_cost": estimated_cost,
        "currency": currency,
        "status": status,
        "created_at": now,
    }


async def summarize_since(since: float) -> dict[str, Any]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) AS calls,COALESCE(SUM(input_tokens),0) AS input_tokens,"
        "COALESCE(SUM(output_tokens),0) AS output_tokens,COALESCE(SUM(units),0) AS units,"
        "COALESCE(SUM(estimated_cost),0) AS estimated_cost FROM usage_records "
        "WHERE user_id=? AND created_at>=?",
        (LOCAL_USER_ID, since),
    )
    return dict(await cursor.fetchone())


async def list_usage(limit: int = 100) -> list[dict[str, Any]]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM usage_records WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (LOCAL_USER_ID, max(1, min(limit, 1000))),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def get_preferences() -> dict[str, Any]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM usage_preferences WHERE user_id=?", (LOCAL_USER_ID,)
    )
    row = await cursor.fetchone()
    if row is None:
        now = time.time()
        await db.execute(
            "INSERT INTO usage_preferences(user_id,updated_at) VALUES(?,?)",
            (LOCAL_USER_ID, now),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM usage_preferences WHERE user_id=?", (LOCAL_USER_ID,)
        )
        row = await cursor.fetchone()
    return dict(row)


async def update_preferences(**changes: Any) -> dict[str, Any]:
    allowed = {
        "daily_budget_cny",
        "monthly_budget_cny",
        "enforcement",
        "alert_threshold_percent",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if "enforcement" in values and values["enforcement"] not in {"off", "soft", "hard"}:
        raise ValueError("invalid budget enforcement")
    if "daily_budget_cny" in values:
        values["daily_budget_cny"] = max(0.0, float(values["daily_budget_cny"]))
    if "monthly_budget_cny" in values:
        values["monthly_budget_cny"] = max(0.0, float(values["monthly_budget_cny"]))
    if "alert_threshold_percent" in values:
        values["alert_threshold_percent"] = min(100, max(1, int(values["alert_threshold_percent"])))
    if not values:
        return await get_preferences()
    await get_preferences()
    db = await get_db()
    assignments = ",".join(f"{key}=?" for key in values)
    params = list(values.values()) + [time.time(), LOCAL_USER_ID]
    await db.execute(
        f"UPDATE usage_preferences SET {assignments},updated_at=? WHERE user_id=?",
        tuple(params),
    )
    await db.commit()
    return await get_preferences()
