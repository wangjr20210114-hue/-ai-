"""Durable external side-effect call ledger.

A provider response is committed here before the Action is marked succeeded. This
closes the most dangerous crash window: an external meeting/image may have been
created even when the process dies before updating ``pending_actions``.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID

_write_lock = asyncio.Lock()


class ProviderCallConflict(ValueError):
    """An idempotency key was reused with a different immutable request."""


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["response_json"] = json.loads(item.get("response_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        item["response_json"] = {}
    return item


async def begin_call(
    *,
    call_id: str,
    run_id: str,
    action_id: str,
    provider: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    """Create a call record or return the exact prior call for this request."""
    db = await get_db()
    now = time.time()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT * FROM provider_calls WHERE user_id=? AND idempotency_key=?",
                (LOCAL_USER_ID, idempotency_key),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                item = _decode(existing)
                if (
                    item["run_id"] != run_id
                    or item["action_id"] != action_id
                    or item["request_hash"] != request_hash
                ):
                    raise ProviderCallConflict(
                        "provider call idempotency key belongs to a different request"
                    )
                await db.commit()
                return item, False

            await db.execute(
                "INSERT INTO provider_calls(id,user_id,run_id,action_id,provider,operation,"
                "idempotency_key,request_hash,status,started_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    call_id,
                    LOCAL_USER_ID,
                    run_id,
                    action_id,
                    provider,
                    operation,
                    idempotency_key,
                    request_hash,
                    "started",
                    now,
                    now,
                ),
            )
            await db.commit()
        except Exception:
            if db.in_transaction:
                await db.rollback()
            raise
    result = await get_call(call_id)
    if result is None:
        raise RuntimeError("provider call persistence failed")
    return result, True


async def get_call(call_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM provider_calls WHERE id=? AND user_id=?",
        (call_id, LOCAL_USER_ID),
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def get_call_for_action(action_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM provider_calls WHERE action_id=? AND user_id=? "
        "ORDER BY started_at DESC LIMIT 1",
        (action_id, LOCAL_USER_ID),
    )
    row = await cursor.fetchone()
    return _decode(row) if row else None


async def complete_call(
    call_id: str,
    *,
    response: dict[str, Any],
    external_resource_id: str = "",
) -> dict[str, Any]:
    """Persist a provider success before the enclosing Action commits."""
    db = await get_db()
    now = time.time()
    encoded = json.dumps(
        {"schema_version": 1, **response},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE provider_calls SET status='succeeded',external_resource_id=?,"
            "response_json=?,error='',updated_at=?,finished_at=? "
            "WHERE id=? AND user_id=? AND status IN ('started','succeeded')",
            (external_resource_id, encoded, now, now, call_id, LOCAL_USER_ID),
        )
        if cursor.rowcount != 1:
            await db.rollback()
            raise ProviderCallConflict("provider call cannot be completed")
        await db.commit()
    result = await get_call(call_id)
    if result is None:
        raise RuntimeError("completed provider call disappeared")
    return result


async def fail_call(call_id: str, error: str, *, result_unknown: bool = False) -> dict[str, Any]:
    db = await get_db()
    now = time.time()
    status = "unknown" if result_unknown else "failed"
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE provider_calls SET status=?,error=?,updated_at=?,finished_at=? "
            "WHERE id=? AND user_id=? AND status='started'",
            (status, error[:2000], now, now, call_id, LOCAL_USER_ID),
        )
        if cursor.rowcount == 0:
            current = await get_call(call_id)
            if current is None:
                await db.rollback()
                raise ProviderCallConflict("provider call not found")
            await db.commit()
            return current
        await db.commit()
    result = await get_call(call_id)
    if result is None:
        raise RuntimeError("failed provider call disappeared")
    return result


async def mark_started_call_unknown(call_id: str, reason: str) -> dict[str, Any]:
    """Convert a stale in-flight call to unknown without changing known outcomes."""
    return await fail_call(call_id, reason, result_unknown=True)


async def list_calls(*, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    db = await get_db()
    bounded = max(1, min(limit, 500))
    if status:
        cursor = await db.execute(
            "SELECT * FROM provider_calls WHERE user_id=? AND status=? "
            "ORDER BY updated_at DESC LIMIT ?",
            (LOCAL_USER_ID, status, bounded),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM provider_calls WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
            (LOCAL_USER_ID, bounded),
        )
    return [_decode(row) for row in await cursor.fetchall()]
