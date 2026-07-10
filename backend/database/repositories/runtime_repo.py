"""Persistent M2 Agent events, runs, observations, and pending actions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID

RUN_TRANSITIONS = {
    "created": {"classified", "failed", "cancelled"},
    "classified": {"planned", "failed", "cancelled"},
    "planned": {"policy_checked", "failed", "cancelled"},
    "policy_checked": {"waiting_confirmation", "queued", "skipped", "failed", "cancelled"},
    "waiting_confirmation": {"queued", "cancelled", "failed"},
    "queued": {"executing", "cancelled", "failed"},
    "executing": {"succeeded", "failed", "cancelled"},
    "failed": {"queued"},
    "succeeded": set(),
    "cancelled": set(),
    "skipped": set(),
}

_write_lock = asyncio.Lock()


class StateConflict(ValueError):
    """Requested version or state transition no longer matches persisted state."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("payload", "plan_json", "snapshot"):
        if key in item:
            try:
                item[key] = json.loads(item[key] or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {}
    return item


async def create_event(
    event_type: str,
    payload: dict[str, Any],
    dedup_key: str,
    *,
    source: str = "user",
    subject_id: str | None = None,
    occurred_at: float | None = None,
) -> tuple[dict[str, Any], bool]:
    db = await get_db()
    now = time.time()
    event_id = f"evt-{uuid.uuid4().hex[:16]}"
    async with _write_lock:
        await db.execute(
            "INSERT OR IGNORE INTO agent_events(id,type,source,user_id,subject_id,payload,dedup_key,occurred_at,received_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (event_id, event_type, source, LOCAL_USER_ID, subject_id, canonical_json(payload), dedup_key, occurred_at or now, now),
        )
        cursor = await db.execute("SELECT * FROM agent_events WHERE dedup_key=?", (dedup_key,))
        row = await cursor.fetchone()
        await db.commit()
    return _decode(row), row["id"] == event_id


async def create_run(
    event_id: str | None,
    *,
    intent: str = "",
    plan: dict[str, Any] | None = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    run_id = f"run-{uuid.uuid4().hex[:16]}"
    plan_value = plan or {}
    async with _write_lock:
        await db.execute(
            "INSERT INTO agent_runs(id,event_id,user_id,status,intent,plan_json,plan_hash,attempt,max_attempts,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, event_id, LOCAL_USER_ID, "created", intent, canonical_json(plan_value), snapshot_hash(plan_value), 0, max(1, max_attempts), now, now),
        )
        await db.execute(
            "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
            (run_id, "created", "run_created", "{}", "", now),
        )
        await db.commit()
    return await get_run(run_id)


async def get_run(run_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID))
    row = await cursor.fetchone()
    if row is None:
        return None
    item = _decode(row)
    cursor = await db.execute("SELECT * FROM agent_observations WHERE run_id=? ORDER BY id", (run_id,))
    item["observations"] = [_decode(observation) for observation in await cursor.fetchall()]
    return item


async def transition_run(
    run_id: str,
    status: str,
    *,
    step: str,
    payload: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute("SELECT status FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID))
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("run not found")
            current = row["status"]
            if status not in RUN_TRANSITIONS.get(current, set()):
                raise StateConflict(f"invalid run transition: {current} -> {status}")
            finished_at = now if status in {"succeeded", "failed", "cancelled", "skipped"} else None
            await db.execute(
                "UPDATE agent_runs SET status=?, error=?, updated_at=?, finished_at=? WHERE id=?",
                (status, error, now, finished_at, run_id),
            )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (run_id, status, step, canonical_json(payload or {}), error, now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return await get_run(run_id)


async def create_action(
    run_id: str,
    skill_name: str,
    snapshot: dict[str, Any],
    idempotency_key: str,
    *,
    expires_at: float | None = None,
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    action_id = f"action-{uuid.uuid4().hex[:16]}"
    encoded = canonical_json(snapshot)
    digest = snapshot_hash(snapshot)
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT status FROM agent_runs WHERE id=? AND user_id=?",
                (run_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None or row["status"] != "waiting_confirmation":
                raise StateConflict("run is not waiting for confirmation")
            await db.execute(
                "INSERT INTO pending_actions(id,run_id,user_id,skill_name,snapshot,snapshot_hash,version,idempotency_key,status,expires_at,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (action_id, run_id, LOCAL_USER_ID, skill_name, encoded, digest, 1, idempotency_key, "awaiting_confirmation", expires_at, now, now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return await get_action(action_id)


async def get_action(action_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID))
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def list_actions(status: str = "awaiting_confirmation") -> list[dict[str, Any]]:
    await expire_actions()
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM pending_actions WHERE user_id=? AND status=? ORDER BY created_at DESC",
        (LOCAL_USER_ID, status),
    )
    return [_decode(row) for row in await cursor.fetchall()]


async def expire_actions(now: float | None = None) -> int:
    db = await get_db()
    ts = now or time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT id, run_id FROM pending_actions WHERE user_id=? AND status='awaiting_confirmation' "
                "AND expires_at IS NOT NULL AND expires_at<=?",
                (LOCAL_USER_ID, ts),
            )
            expired = await cursor.fetchall()
            for row in expired:
                await db.execute("UPDATE pending_actions SET status='expired', updated_at=? WHERE id=?", (ts, row["id"]))
                await db.execute(
                    "UPDATE agent_runs SET status='cancelled', updated_at=?, finished_at=? "
                    "WHERE id=? AND status='waiting_confirmation'",
                    (ts, ts, row["run_id"]),
                )
                await db.execute(
                    "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                    (row["run_id"], "cancelled", "action_expired", canonical_json({"action_id": row["id"]}), "", ts),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return len(expired)


async def confirm_action(action_id: str, version: int) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute("SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID))
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["expires_at"] is not None and row["expires_at"] <= now:
                await db.execute("UPDATE pending_actions SET status='expired', updated_at=? WHERE id=?", (now, action_id))
                await db.execute(
                    "UPDATE agent_runs SET status='cancelled', updated_at=?, finished_at=? "
                    "WHERE id=? AND status='waiting_confirmation'",
                    (now, now, row["run_id"]),
                )
                await db.execute(
                    "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                    (row["run_id"], "cancelled", "action_expired", canonical_json({"action_id": action_id}), "", now),
                )
                await db.commit()
                raise StateConflict("action expired")
            if row["status"] != "awaiting_confirmation" or row["version"] != version:
                raise StateConflict("action state or version conflict")
            if hashlib.sha256(row["snapshot"].encode("utf-8")).hexdigest() != row["snapshot_hash"]:
                raise StateConflict("action snapshot hash mismatch")
            await db.execute("UPDATE pending_actions SET status='confirmed', updated_at=? WHERE id=?", (now, action_id))
            await db.execute("UPDATE agent_runs SET status='queued', updated_at=? WHERE id=?", (now, row["run_id"]))
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (row["run_id"], "queued", "action_confirmed", canonical_json({"action_id": action_id, "version": version}), "", now),
            )
            await db.commit()
        except StateConflict:
            if db.in_transaction:
                await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
    return await get_action(action_id)


async def cancel_action(action_id: str) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE pending_actions SET status='cancelled', updated_at=? "
            "WHERE id=? AND user_id=? AND status IN ('awaiting_confirmation','confirmed')",
            (now, action_id, LOCAL_USER_ID),
        )
        if cursor.rowcount != 1:
            await db.rollback()
            raise StateConflict("action cannot be cancelled")
        action_cursor = await db.execute("SELECT run_id FROM pending_actions WHERE id=?", (action_id,))
        run_id = (await action_cursor.fetchone())["run_id"]
        await db.execute("UPDATE agent_runs SET status='cancelled', updated_at=?, finished_at=? WHERE id=?", (now, now, run_id))
        await db.execute(
            "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
            (run_id, "cancelled", "action_cancelled", canonical_json({"action_id": action_id}), "", now),
        )
        await db.commit()
    return await get_action(action_id)


async def retry_run(run_id: str) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE agent_runs SET status='queued', attempt=attempt+1, error='', updated_at=?, finished_at=NULL "
            "WHERE id=? AND user_id=? AND status='failed' AND attempt<max_attempts",
            (now, run_id, LOCAL_USER_ID),
        )
        if cursor.rowcount != 1:
            await db.rollback()
            raise StateConflict("run cannot be retried")
        await db.execute(
            "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
            (run_id, "queued", "run_retried", "{}", "", now),
        )
        await db.commit()
    return await get_run(run_id)
