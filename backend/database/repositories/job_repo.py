"""Persistent scheduler job repository with leases and checkpoints."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID

_write_lock = asyncio.Lock()


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("payload", "checkpoint"):
        try:
            item[key] = json.loads(item.get(key) or "{}")
        except (json.JSONDecodeError, TypeError):
            item[key] = {}
    return item


async def upsert_job(
    job_id: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    next_run_at: float,
    interval_seconds: int | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    await db.execute(
        "INSERT INTO scheduled_jobs(id,user_id,job_type,payload,next_run_at,interval_seconds,status,max_attempts,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET job_type=excluded.job_type,payload=excluded.payload,"
        "interval_seconds=excluded.interval_seconds,max_attempts=excluded.max_attempts,updated_at=excluded.updated_at",
        (
            job_id,
            LOCAL_USER_ID,
            job_type,
            json.dumps({"schema_version": 1, **payload}, ensure_ascii=False),
            next_run_at,
            interval_seconds,
            "enabled",
            max(1, max_attempts),
            now,
            now,
        ),
    )
    await db.commit()
    result = await get_job(job_id)
    if result is None:
        raise RuntimeError("scheduled job persistence failed")
    return result


async def get_job(job_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM scheduled_jobs WHERE id=? AND user_id=?", (job_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM scheduled_jobs WHERE user_id=? ORDER BY next_run_at LIMIT ?",
        (LOCAL_USER_ID, max(1, min(limit, 500))),
    )
    return [_decode(row) for row in await cursor.fetchall()]


async def claim_due_job(
    worker_id: str,
    *,
    now: float | None = None,
    lease_seconds: int = 60,
) -> dict[str, Any] | None:
    db = await get_db()
    ts = now or time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT id FROM scheduled_jobs WHERE user_id=? AND status='enabled' AND next_run_at<=? "
                "AND (lease_until IS NULL OR lease_until<=?) ORDER BY next_run_at LIMIT 1",
                (LOCAL_USER_ID, ts, ts),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.commit()
                return None
            updated = await db.execute(
                "UPDATE scheduled_jobs SET status='running',lease_owner=?,lease_until=?,attempt=attempt+1,updated_at=? "
                "WHERE id=? AND status='enabled'",
                (worker_id, ts + max(5, lease_seconds), ts, row["id"]),
            )
            if updated.rowcount != 1:
                await db.rollback()
                return None
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return await get_job(row["id"])


async def complete_job(
    job_id: str,
    *,
    checkpoint: dict[str, Any] | None = None,
    next_run_at: float | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    db = await get_db()
    ts = now or time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT interval_seconds,status FROM scheduled_jobs WHERE id=? AND user_id=?",
                (job_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None or row["status"] != "running":
                raise ValueError("job is not running")
            interval = row["interval_seconds"]
            status = "enabled" if interval or next_run_at is not None else "completed"
            next_run = (
                max(ts, float(next_run_at))
                if next_run_at is not None
                else (ts + interval if interval else ts)
            )
            await db.execute(
                "UPDATE scheduled_jobs SET status=?,next_run_at=?,checkpoint=?,last_error='',attempt=0,"
                "lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                (
                    status,
                    next_run,
                    json.dumps({"schema_version": 1, **(checkpoint or {})}, ensure_ascii=False),
                    ts,
                    job_id,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_job(job_id)
    if result is None:
        raise RuntimeError("job disappeared")
    return result


async def fail_job(
    job_id: str,
    error: str,
    *,
    retry_delay_seconds: int = 60,
    now: float | None = None,
) -> dict[str, Any]:
    db = await get_db()
    ts = now or time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT attempt,max_attempts FROM scheduled_jobs WHERE id=? AND user_id=?",
                (job_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("job not found")
            exhausted = int(row["attempt"]) >= int(row["max_attempts"])
            status = "failed" if exhausted else "enabled"
            await db.execute(
                "UPDATE scheduled_jobs SET status=?,next_run_at=?,last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                (status, ts + max(1, retry_delay_seconds), error[:1000], ts, job_id),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_job(job_id)
    if result is None:
        raise RuntimeError("job disappeared")
    return result


async def recover_expired_jobs(now: float | None = None) -> int:
    db = await get_db()
    ts = now or time.time()
    cursor = await db.execute(
        "UPDATE scheduled_jobs SET status='enabled',lease_owner=NULL,lease_until=NULL,next_run_at=?,"
        "last_error='scheduler lease expired',updated_at=? WHERE user_id=? AND status='running' "
        "AND lease_until IS NOT NULL AND lease_until<=?",
        (ts, ts, LOCAL_USER_ID, ts),
    )
    await db.commit()
    return max(0, cursor.rowcount)


async def count_jobs_by_status() -> dict[str, int]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT status,COUNT(*) AS count FROM scheduled_jobs WHERE user_id=? GROUP BY status",
        (LOCAL_USER_ID,),
    )
    return {str(row["status"]): int(row["count"]) for row in await cursor.fetchall()}


async def pause_job(job_id: str) -> dict[str, Any] | None:
    db = await get_db()
    await db.execute(
        "UPDATE scheduled_jobs SET status='paused',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND user_id=?",
        (time.time(), job_id, LOCAL_USER_ID),
    )
    await db.commit()
    return await get_job(job_id)


async def resume_job(job_id: str) -> dict[str, Any] | None:
    db = await get_db()
    now = time.time()
    await db.execute(
        "UPDATE scheduled_jobs SET status='enabled',next_run_at=MIN(next_run_at,?),last_error='',updated_at=? WHERE id=? AND user_id=?",
        (now, now, job_id, LOCAL_USER_ID),
    )
    await db.commit()
    return await get_job(job_id)
