"""Persistent Agent events, runs, observations, leases, and pending actions.

This repository is the only module allowed to mutate Agent execution state.  Every
state change is committed together with an observation so the UI and recovery
worker can reconstruct what happened after a restart.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID

RUN_TRANSITIONS: dict[str, set[str]] = {
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
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled", "skipped"}

_write_lock = asyncio.Lock()


class StateConflict(ValueError):
    """Requested version or state transition no longer matches persisted state."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def snapshot_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("payload", "plan_json", "snapshot", "result_json", "metadata", "checkpoint"):
        if key in item:
            try:
                item[key] = json.loads(item[key] or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {}
    if "reconciliation_required" in item:
        item["reconciliation_required"] = bool(item["reconciliation_required"])
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
    if not event_type.strip() or not dedup_key.strip():
        raise ValueError("event_type and dedup_key are required")
    db = await get_db()
    now = time.time()
    event_id = f"evt-{uuid.uuid4().hex[:16]}"
    versioned_payload = {"schema_version": 1, **payload}
    async with _write_lock:
        await db.execute(
            "INSERT OR IGNORE INTO agent_events(id,type,source,user_id,subject_id,payload,dedup_key,occurred_at,received_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                event_type,
                source,
                LOCAL_USER_ID,
                subject_id,
                canonical_json(versioned_payload),
                dedup_key,
                occurred_at or now,
                now,
            ),
        )
        cursor = await db.execute("SELECT * FROM agent_events WHERE dedup_key=?", (dedup_key,))
        row = await cursor.fetchone()
        await db.commit()
    if row is None:  # defensive: INSERT OR IGNORE + SELECT should always return a row
        raise RuntimeError("event persistence failed")
    return _decode(row), row["id"] == event_id


async def get_event(event_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM agent_events WHERE id=? AND user_id=?", (event_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def mark_event_processed(event_id: str, processed_at: float | None = None) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE agent_events SET processed_at=COALESCE(processed_at, ?) WHERE id=? AND user_id=?",
        (processed_at or time.time(), event_id, LOCAL_USER_ID),
    )
    await db.commit()


async def get_run_for_event(event_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM agent_runs WHERE event_id=? AND user_id=? ORDER BY created_at LIMIT 1",
        (event_id, LOCAL_USER_ID),
    )
    row = await cursor.fetchone()
    return await get_run(row["id"]) if row else None


async def create_run(
    event_id: str | None,
    *,
    intent: str = "",
    plan: dict[str, Any] | None = None,
    max_attempts: int = 1,
    execution_lane: str = "interactive",
) -> dict[str, Any]:
    if event_id:
        existing = await get_run_for_event(event_id)
        if existing is not None:
            return existing
        if await get_event(event_id) is None:
            raise StateConflict("event not found")
    if execution_lane not in {"interactive", "background"}:
        raise ValueError("invalid execution lane")
    db = await get_db()
    now = time.time()
    run_id = f"run-{uuid.uuid4().hex[:16]}"
    plan_value = plan or {"schema_version": 1}
    async with _write_lock:
        await db.execute(
            "INSERT INTO agent_runs(id,event_id,user_id,status,intent,plan_json,plan_hash,attempt,max_attempts,created_at,updated_at,execution_lane) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                event_id,
                LOCAL_USER_ID,
                "created",
                intent,
                canonical_json(plan_value),
                snapshot_hash(plan_value),
                0,
                max(1, max_attempts),
                now,
                now,
                execution_lane,
            ),
        )
        await db.execute(
            "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
            (run_id, "created", "run_created", canonical_json({"schema_version": 1}), "", now),
        )
        await db.commit()
    result = await get_run(run_id)
    if result is None:
        raise RuntimeError("run persistence failed")
    return result


async def get_run(run_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    item = _decode(row)
    cursor = await db.execute(
        "SELECT * FROM agent_observations WHERE run_id=? ORDER BY id", (run_id,)
    )
    item["observations"] = [_decode(observation) for observation in await cursor.fetchall()]
    action = await get_action_for_run(run_id)
    if action:
        item["action"] = action
    return item


async def list_runs(limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
    db = await get_db()
    if status:
        cursor = await db.execute(
            "SELECT id FROM agent_runs WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
            (LOCAL_USER_ID, status, max(1, min(limit, 500))),
        )
    else:
        cursor = await db.execute(
            "SELECT id FROM agent_runs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (LOCAL_USER_ID, max(1, min(limit, 500))),
        )
    return [run for row in await cursor.fetchall() if (run := await get_run(row["id"])) is not None]


async def transition_run(
    run_id: str,
    status: str,
    *,
    step: str,
    payload: dict[str, Any] | None = None,
    error: str = "",
    expected_status: str | None = None,
    intent: str | None = None,
    plan: dict[str, Any] | None = None,
    execution_lane: str | None = None,
    lease_owner: str | None = None,
    lease_until: float | None = None,
    increment_attempt: bool = False,
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT status FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("run not found")
            current = row["status"]
            if expected_status is not None and current != expected_status:
                raise StateConflict(f"run state conflict: expected {expected_status}, got {current}")
            if status not in RUN_TRANSITIONS.get(current, set()):
                raise StateConflict(f"invalid run transition: {current} -> {status}")
            if execution_lane is not None and execution_lane not in {"interactive", "background"}:
                raise StateConflict("invalid execution lane")
            finished_at = now if status in TERMINAL_RUN_STATUSES else None
            plan_value = canonical_json(plan) if plan is not None else None
            plan_digest = snapshot_hash(plan) if plan is not None else None
            await db.execute(
                "UPDATE agent_runs SET status=?, error=?, updated_at=?, finished_at=?, "
                "intent=COALESCE(?, intent), plan_json=COALESCE(?, plan_json), plan_hash=COALESCE(?, plan_hash), "
                "execution_lane=COALESCE(?, execution_lane), lease_owner=?, lease_until=?, "
                "attempt=attempt+? WHERE id=?",
                (
                    status,
                    error,
                    now,
                    finished_at,
                    intent,
                    plan_value,
                    plan_digest,
                    execution_lane,
                    lease_owner,
                    lease_until,
                    1 if increment_attempt else 0,
                    run_id,
                ),
            )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (run_id, status, step, canonical_json({"schema_version": 1, **(payload or {})}), error, now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_run(run_id)
    if result is None:
        raise RuntimeError("run disappeared after transition")
    return result


async def append_observation(
    run_id: str,
    *,
    step: str,
    payload: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    cursor = await db.execute(
        "SELECT status FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    if row is None:
        raise StateConflict("run not found")
    await db.execute(
        "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
        (run_id, row["status"], step, canonical_json({"schema_version": 1, **(payload or {})}), error, now),
    )
    await db.execute("UPDATE agent_runs SET updated_at=? WHERE id=?", (now, run_id))
    await db.commit()
    result = await get_run(run_id)
    if result is None:
        raise RuntimeError("run disappeared after observation")
    return result


async def set_run_classification(run_id: str, intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await transition_run(
        run_id,
        "classified",
        expected_status="created",
        step="classification_completed",
        intent=intent,
        payload=payload,
    )


async def set_run_plan(
    run_id: str,
    plan: dict[str, Any],
    *,
    execution_lane: str,
    max_attempts: int,
) -> dict[str, Any]:
    db = await get_db()
    # max_attempts is metadata rather than a state transition field, so update it first.
    await db.execute(
        "UPDATE agent_runs SET max_attempts=? WHERE id=? AND user_id=?",
        (max(1, max_attempts), run_id, LOCAL_USER_ID),
    )
    await db.commit()
    return await transition_run(
        run_id,
        "planned",
        expected_status="classified",
        step="plan_created",
        plan={"schema_version": 1, **plan},
        execution_lane=execution_lane,
        payload={
            "intent": plan.get("intent", ""),
            "skill_name": plan.get("skill_name", ""),
            "permission_level": plan.get("permission_level", ""),
            "risk_level": plan.get("risk_level", ""),
        },
    )


async def claim_run(run_id: str, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
    db = await get_db()
    now = time.time()
    lease_until = now + max(5, lease_seconds)
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "UPDATE agent_runs SET status='executing', lease_owner=?, lease_until=?, updated_at=?, attempt=attempt+1 "
                "WHERE id=? AND user_id=? AND status='queued'",
                (worker_id, lease_until, now, run_id, LOCAL_USER_ID),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return None
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    "executing",
                    "run_claimed",
                    canonical_json({"schema_version": 1, "worker_id": worker_id, "lease_until": lease_until}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return await get_run(run_id)


async def claim_queued_run(
    worker_id: str,
    lease_seconds: int = 60,
    *,
    execution_lane: str = "background",
) -> dict[str, Any] | None:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT id FROM agent_runs WHERE user_id=? AND status='queued' AND execution_lane=? "
                "ORDER BY updated_at LIMIT 1",
                (LOCAL_USER_ID, execution_lane),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.commit()
                return None
            run_id = row["id"]
            lease_until = now + max(5, lease_seconds)
            updated = await db.execute(
                "UPDATE agent_runs SET status='executing', lease_owner=?, lease_until=?, updated_at=?, attempt=attempt+1 "
                "WHERE id=? AND status='queued'",
                (worker_id, lease_until, now, run_id),
            )
            if updated.rowcount != 1:
                await db.rollback()
                return None
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    "executing",
                    "run_claimed",
                    canonical_json({"schema_version": 1, "worker_id": worker_id, "lease_until": lease_until}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return await get_run(run_id)


async def complete_run(run_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return await transition_run(
        run_id,
        "succeeded",
        expected_status="executing",
        step="run_succeeded",
        payload={"result": result or {}},
    )


async def fail_run(run_id: str, error: str, *, retryable: bool = False) -> dict[str, Any]:
    run = await get_run(run_id)
    if run is None:
        raise StateConflict("run not found")
    failed = await transition_run(
        run_id,
        "failed",
        expected_status="executing",
        step="run_failed",
        error=error,
        payload={"retryable": retryable},
    )
    return failed


async def cancel_run(run_id: str, *, reason: str = "cancelled_by_user") -> dict[str, Any]:
    """Cancel a non-terminal Run and any not-yet-executing pending action.

    External side effects are deliberately not cancellable after execution starts: the
    provider may already have committed the operation, so reporting cancellation would
    create an unsafe false state. Repeated cancellation is idempotent.
    """
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT status FROM agent_runs WHERE id=? AND user_id=?",
                (run_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("run not found")
            current = str(row["status"])
            if current == "cancelled":
                await db.commit()
                result = await get_run(run_id)
                if result is None:
                    raise RuntimeError("cancelled run disappeared")
                return result
            if current in TERMINAL_RUN_STATUSES:
                raise StateConflict(f"terminal run cannot be cancelled: {current}")

            action_cursor = await db.execute(
                "SELECT id,status FROM pending_actions WHERE run_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id, LOCAL_USER_ID),
            )
            action = await action_cursor.fetchone()
            if action is not None and action["status"] == "executing":
                raise StateConflict("executing side effect cannot be cancelled safely")
            if action is not None and action["status"] in {"draft", "awaiting_confirmation", "confirmed"}:
                await db.execute(
                    "UPDATE pending_actions SET status='cancelled', updated_at=? WHERE id=?",
                    (now, action["id"]),
                )

            updated = await db.execute(
                "UPDATE agent_runs SET status='cancelled', error='', lease_owner=NULL, lease_until=NULL, "
                "updated_at=?, finished_at=? WHERE id=? AND user_id=? AND status=?",
                (now, now, run_id, LOCAL_USER_ID, current),
            )
            if updated.rowcount != 1:
                raise StateConflict("run changed while cancellation was being applied")
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    "cancelled",
                    "run_cancelled",
                    canonical_json({"schema_version": 1, "reason": reason}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            if db.in_transaction:
                await db.rollback()
            raise
    result = await get_run(run_id)
    if result is None:
        raise RuntimeError("run disappeared after cancellation")
    return result


async def recover_expired_runs(now: float | None = None) -> dict[str, Any]:
    """Recover expired execution leases without blindly retrying side effects."""
    db = await get_db()
    ts = now or time.time()
    report: dict[str, Any] = {"scanned": 0, "requeued": 0, "reconciliation_required": 0, "failed": []}
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT r.id, r.attempt, r.max_attempts, a.id AS action_id FROM agent_runs r "
                "LEFT JOIN pending_actions a ON a.run_id=r.id AND a.status='executing' "
                "WHERE r.user_id=? AND r.status='executing' AND r.lease_until IS NOT NULL AND r.lease_until<=?",
                (LOCAL_USER_ID, ts),
            )
            rows = await cursor.fetchall()
            report["scanned"] = len(rows)
            for row in rows:
                if row["action_id"]:
                    await db.execute(
                        "UPDATE pending_actions SET reconciliation_required=1, error=?, updated_at=? WHERE id=?",
                        ("execution lease expired; external result may be unknown", ts, row["action_id"]),
                    )
                    await db.execute(
                        "UPDATE agent_runs SET status='failed', error=?, lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=? WHERE id=?",
                        ("side effect requires reconciliation", ts, ts, row["id"]),
                    )
                    report["reconciliation_required"] += 1
                    step = "side_effect_reconciliation_required"
                    error = "side effect requires reconciliation"
                elif row["attempt"] < row["max_attempts"]:
                    await db.execute(
                        "UPDATE agent_runs SET status='queued', error='', lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=NULL WHERE id=?",
                        (ts, row["id"]),
                    )
                    report["requeued"] += 1
                    step = "expired_lease_requeued"
                    error = ""
                else:
                    await db.execute(
                        "UPDATE agent_runs SET status='failed', error=?, lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=? WHERE id=?",
                        ("execution lease expired and attempts exhausted", ts, ts, row["id"]),
                    )
                    report["failed"].append(row["id"])
                    step = "expired_lease_failed"
                    error = "execution lease expired and attempts exhausted"
                await db.execute(
                    "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) "
                    "SELECT id,status,?,?,?,? FROM agent_runs WHERE id=?",
                    (step, canonical_json({"schema_version": 1}), error, ts, row["id"]),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return report


async def count_runs_by_status() -> dict[str, int]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT status,COUNT(*) AS count FROM agent_runs WHERE user_id=? GROUP BY status",
        (LOCAL_USER_ID,),
    )
    return {str(row["status"]): int(row["count"]) for row in await cursor.fetchall()}


async def count_actions_by_status() -> dict[str, int]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT status,COUNT(*) AS count FROM pending_actions WHERE user_id=? GROUP BY status",
        (LOCAL_USER_ID,),
    )
    return {str(row["status"]): int(row["count"]) for row in await cursor.fetchall()}


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
    versioned_snapshot = {"schema_version": 1, **snapshot}
    encoded = canonical_json(versioned_snapshot)
    digest = snapshot_hash(versioned_snapshot)
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            existing_cursor = await db.execute(
                "SELECT * FROM pending_actions WHERE idempotency_key=? AND user_id=?",
                (idempotency_key, LOCAL_USER_ID),
            )
            existing = await existing_cursor.fetchone()
            if existing is not None:
                item = _decode(existing)
                if item["snapshot_hash"] != digest or item["run_id"] != run_id:
                    raise StateConflict("idempotency key already belongs to a different action")
                await db.commit()
                return item
            cursor = await db.execute(
                "SELECT status FROM agent_runs WHERE id=? AND user_id=?", (run_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None or row["status"] != "waiting_confirmation":
                raise StateConflict("run is not waiting for confirmation")
            await db.execute(
                "INSERT INTO pending_actions(id,run_id,user_id,skill_name,snapshot,snapshot_hash,version,idempotency_key,status,expires_at,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    action_id,
                    run_id,
                    LOCAL_USER_ID,
                    skill_name,
                    encoded,
                    digest,
                    1,
                    idempotency_key,
                    "awaiting_confirmation",
                    expires_at,
                    now,
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_action(action_id)
    if result is None:
        raise RuntimeError("action persistence failed")
    return result


async def get_action(action_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def get_action_for_run(run_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM pending_actions WHERE run_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
        (run_id, LOCAL_USER_ID),
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def list_actions(status: str | None = "awaiting_confirmation", limit: int = 100) -> list[dict[str, Any]]:
    await expire_actions()
    db = await get_db()
    if status:
        cursor = await db.execute(
            "SELECT * FROM pending_actions WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
            (LOCAL_USER_ID, status, max(1, min(limit, 500))),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM pending_actions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (LOCAL_USER_ID, max(1, min(limit, 500))),
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
                await db.execute(
                    "UPDATE pending_actions SET status='expired', updated_at=? WHERE id=?", (ts, row["id"])
                )
                await db.execute(
                    "UPDATE agent_runs SET status='cancelled', updated_at=?, finished_at=? "
                    "WHERE id=? AND status='waiting_confirmation'",
                    (ts, ts, row["run_id"]),
                )
                await db.execute(
                    "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                    (
                        row["run_id"],
                        "cancelled",
                        "action_expired",
                        canonical_json({"schema_version": 1, "action_id": row["id"]}),
                        "",
                        ts,
                    ),
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
            cursor = await db.execute(
                "SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["version"] != version:
                raise StateConflict("action version conflict")
            if row["expires_at"] is not None and row["expires_at"] <= now:
                await db.execute(
                    "UPDATE pending_actions SET status='expired', updated_at=? WHERE id=?", (now, action_id)
                )
                await db.execute(
                    "UPDATE agent_runs SET status='cancelled', updated_at=?, finished_at=? "
                    "WHERE id=? AND status='waiting_confirmation'",
                    (now, now, row["run_id"]),
                )
                await db.commit()
                raise StateConflict("action expired")
            if hashlib.sha256(row["snapshot"].encode("utf-8")).hexdigest() != row["snapshot_hash"]:
                raise StateConflict("action snapshot hash mismatch")
            # Confirmation is deliberately idempotent: repeated UI clicks return the same action.
            if row["status"] in {"confirmed", "executing", "succeeded"}:
                await db.commit()
                return _decode(row)
            if row["status"] != "awaiting_confirmation":
                raise StateConflict("action cannot be confirmed")
            await db.execute(
                "UPDATE pending_actions SET status='confirmed', updated_at=? WHERE id=?", (now, action_id)
            )
            run_update = await db.execute(
                "UPDATE agent_runs SET status='queued', execution_lane='background', updated_at=? "
                "WHERE id=? AND status='waiting_confirmation'",
                (now, row["run_id"]),
            )
            if run_update.rowcount != 1:
                raise StateConflict("run is no longer waiting for confirmation")
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "queued",
                    "action_confirmed",
                    canonical_json({"schema_version": 1, "action_id": action_id, "version": version}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except StateConflict:
            if db.in_transaction:
                await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
    result = await get_action(action_id)
    if result is None:
        raise RuntimeError("action disappeared after confirmation")
    return result


async def cancel_action(action_id: str) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["status"] == "cancelled":
                await db.commit()
                return _decode(row)
            if row["status"] not in {"awaiting_confirmation", "confirmed"}:
                raise StateConflict("action cannot be cancelled")
            await db.execute(
                "UPDATE pending_actions SET status='cancelled', updated_at=? WHERE id=?", (now, action_id)
            )
            await db.execute(
                "UPDATE agent_runs SET status='cancelled', lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=? "
                "WHERE id=? AND status IN ('waiting_confirmation','queued')",
                (now, now, row["run_id"]),
            )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "cancelled",
                    "action_cancelled",
                    canonical_json({"schema_version": 1, "action_id": action_id}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_action(action_id)
    if result is None:
        raise RuntimeError("action disappeared after cancellation")
    return result


async def start_action_execution(action_id: str) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["status"] == "executing":
                await db.commit()
                return _decode(row)
            if row["status"] != "confirmed":
                raise StateConflict("action is not confirmed")
            if hashlib.sha256(row["snapshot"].encode("utf-8")).hexdigest() != row["snapshot_hash"]:
                raise StateConflict("action snapshot hash mismatch")
            await db.execute(
                "UPDATE pending_actions SET status='executing', execution_started_at=?, updated_at=?, error='' WHERE id=?",
                (now, now, action_id),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_action(action_id)
    if result is None:
        raise RuntimeError("action disappeared after execution start")
    return result


async def complete_action_and_run(
    action_id: str,
    result: dict[str, Any],
    *,
    provider_request_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT run_id,status FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["status"] == "succeeded":
                await db.commit()
                action = await get_action(action_id)
                run = await get_run(row["run_id"])
                if action is None or run is None:
                    raise RuntimeError("completed action or run missing")
                return action, run
            if row["status"] != "executing":
                raise StateConflict("action is not executing")
            await db.execute(
                "UPDATE pending_actions SET status='succeeded', result_json=?, provider_request_id=?, error='', "
                "reconciliation_required=0, executed_at=?, updated_at=? WHERE id=?",
                (canonical_json({"schema_version": 1, **result}), provider_request_id, now, now, action_id),
            )
            run_update = await db.execute(
                "UPDATE agent_runs SET status='succeeded', error='', lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=? "
                "WHERE id=? AND status='executing'",
                (now, now, row["run_id"]),
            )
            if run_update.rowcount != 1:
                raise StateConflict("run is not executing")
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "succeeded",
                    "action_succeeded",
                    canonical_json({"schema_version": 1, "action_id": action_id, "result": result}),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    action = await get_action(action_id)
    run = await get_run(row["run_id"])
    if action is None or run is None:
        raise RuntimeError("completed action or run missing")
    return action, run


async def fail_action_and_run(
    action_id: str,
    error: str,
    *,
    retryable: bool = False,
    reconciliation_required: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT run_id FROM pending_actions WHERE id=? AND user_id=?", (action_id, LOCAL_USER_ID)
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            await db.execute(
                "UPDATE pending_actions SET status='failed', error=?, reconciliation_required=?, updated_at=? WHERE id=?",
                (error, 1 if reconciliation_required else 0, now, action_id),
            )
            await db.execute(
                "UPDATE agent_runs SET status='failed', error=?, lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=? "
                "WHERE id=? AND status='executing'",
                (error, now, now, row["run_id"]),
            )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "failed",
                    "action_failed",
                    canonical_json(
                        {
                            "schema_version": 1,
                            "action_id": action_id,
                            "retryable": retryable,
                            "reconciliation_required": reconciliation_required,
                        }
                    ),
                    error,
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    action = await get_action(action_id)
    run = await get_run(row["run_id"])
    if action is None or run is None:
        raise RuntimeError("failed action or run missing")
    return action, run


async def recover_action_success(
    action_id: str,
    result: dict[str, Any],
    *,
    provider_request_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve an unknown Action from a durable successful provider call.

    This is intentionally narrower than normal completion: it only accepts an
    Action marked for reconciliation and a Run left in ``failed``/``executing``.
    """
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT run_id,status,reconciliation_required FROM pending_actions "
                "WHERE id=? AND user_id=?",
                (action_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["status"] == "succeeded":
                await db.commit()
                action = await get_action(action_id)
                run = await get_run(row["run_id"])
                if action is None or run is None:
                    raise RuntimeError("reconciled action or run missing")
                return action, run
            if not row["reconciliation_required"] or row["status"] not in {"executing", "failed"}:
                raise StateConflict("action is not awaiting reconciliation")
            await db.execute(
                "UPDATE pending_actions SET status='succeeded',result_json=?,provider_request_id=?,"
                "error='',reconciliation_required=0,executed_at=COALESCE(executed_at,?),updated_at=? "
                "WHERE id=?",
                (
                    canonical_json({"schema_version": 1, **result}),
                    provider_request_id,
                    now,
                    now,
                    action_id,
                ),
            )
            updated = await db.execute(
                "UPDATE agent_runs SET status='succeeded',error='',lease_owner=NULL,lease_until=NULL,"
                "updated_at=?,finished_at=? WHERE id=? AND status IN ('failed','executing')",
                (now, now, row["run_id"]),
            )
            if updated.rowcount != 1:
                raise StateConflict("run is not recoverable")
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "succeeded",
                    "action_reconciled_succeeded",
                    canonical_json(
                        {
                            "schema_version": 1,
                            "action_id": action_id,
                            "provider_request_id": provider_request_id,
                        }
                    ),
                    "",
                    now,
                ),
            )
            await db.commit()
        except Exception:
            if db.in_transaction:
                await db.rollback()
            raise
    action = await get_action(action_id)
    run = await get_run(row["run_id"])
    if action is None or run is None:
        raise RuntimeError("reconciled action or run missing")
    return action, run


async def resolve_action_reconciliation_failure(
    action_id: str,
    error: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve an unknown Action when the durable provider ledger proves failure."""
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT run_id,status,reconciliation_required FROM pending_actions "
                "WHERE id=? AND user_id=?",
                (action_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("action not found")
            if row["status"] == "failed" and not row["reconciliation_required"]:
                await db.commit()
                action = await get_action(action_id)
                run = await get_run(row["run_id"])
                if action is None or run is None:
                    raise RuntimeError("resolved action or run missing")
                return action, run
            if not row["reconciliation_required"]:
                raise StateConflict("action is not awaiting reconciliation")
            await db.execute(
                "UPDATE pending_actions SET status='failed',error=?,reconciliation_required=0,updated_at=? "
                "WHERE id=?",
                (error[:2000], now, action_id),
            )
            await db.execute(
                "UPDATE agent_runs SET status='failed',error=?,lease_owner=NULL,lease_until=NULL,"
                "updated_at=?,finished_at=COALESCE(finished_at,?) WHERE id=?",
                (error[:2000], now, now, row["run_id"]),
            )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (
                    row["run_id"],
                    "failed",
                    "action_reconciled_failed",
                    canonical_json({"schema_version": 1, "action_id": action_id}),
                    error[:2000],
                    now,
                ),
            )
            await db.commit()
        except Exception:
            if db.in_transaction:
                await db.rollback()
            raise
    action = await get_action(action_id)
    run = await get_run(row["run_id"])
    if action is None or run is None:
        raise RuntimeError("resolved action or run missing")
    return action, run


async def retry_run(run_id: str) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT attempt,max_attempts FROM agent_runs WHERE id=? AND user_id=? AND status='failed'",
                (run_id, LOCAL_USER_ID),
            )
            row = await cursor.fetchone()
            if row is None or row["attempt"] >= row["max_attempts"]:
                raise StateConflict("run cannot be retried")
            action_cursor = await db.execute(
                "SELECT id,reconciliation_required FROM pending_actions WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            )
            action = await action_cursor.fetchone()
            if action is not None and action["reconciliation_required"]:
                raise StateConflict("run requires side-effect reconciliation before retry")
            await db.execute(
                "UPDATE agent_runs SET status='queued', error='', lease_owner=NULL, lease_until=NULL, updated_at=?, finished_at=NULL "
                "WHERE id=?",
                (now, run_id),
            )
            if action is not None:
                await db.execute(
                    "UPDATE pending_actions SET status='confirmed', error='', updated_at=? WHERE id=? AND status='failed'",
                    (now, action["id"]),
                )
            await db.execute(
                "INSERT INTO agent_observations(run_id,status,step,payload,error,ts) VALUES(?,?,?,?,?,?)",
                (run_id, "queued", "run_retried", canonical_json({"schema_version": 1}), "", now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    result = await get_run(run_id)
    if result is None:
        raise RuntimeError("run disappeared after retry")
    return result
