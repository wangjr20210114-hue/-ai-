"""EdgeOne Makers cache and single-flight for search evidence models."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..._models.search_evidence import cacheable_evidence
from .data_version import namespace as data_namespace


@dataclass(frozen=True)
class EvidenceCacheResult:
    metadata: dict[str, Any]
    cache_hit: bool
    coalesced: bool


_FLIGHTS: dict[tuple[int, str, str], asyncio.Task] = {}


def _item_value(item: Any) -> dict[str, Any] | None:
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def load_search_evidence(
    store: Any,
    user_id: str,
    cache_key: str,
    *,
    now: int | None = None,
) -> dict[str, Any] | None:
    if store is None:
        return None
    timestamp = int(time.time() if now is None else now)
    try:
        value = _item_value(await store.aget(
            data_namespace("search_evidence_cache", str(user_id)),
            str(cache_key),
        ))
        evidence = value.get("evidence") if isinstance(value, dict) else None
        if (
            int((value or {}).get("expires_at") or 0) > timestamp
            and isinstance(evidence, dict)
            and not evidence.get("media_pending")
        ):
            return copy.deepcopy(evidence)
    except Exception as exc:
        logging.warning("search evidence cache read failed: %s", exc)
    return None


async def save_search_evidence(
    store: Any,
    user_id: str,
    cache_key: str,
    metadata: dict[str, Any],
    *,
    ttl_seconds: int,
    now: int | None = None,
) -> None:
    if store is None or metadata.get("media_pending"):
        return
    timestamp = int(time.time() if now is None else now)
    evidence = cacheable_evidence(metadata)
    try:
        await store.aput(
            data_namespace("search_evidence_cache", str(user_id)),
            str(cache_key),
            {
                "schema_version": 1,
                "evidence": evidence,
                "created_at": timestamp,
                "expires_at": timestamp + max(60, min(60 * 60, int(ttl_seconds))),
            },
        )
    except Exception as exc:
        logging.warning("search evidence cache write failed: %s", exc)


async def get_or_compute_search_evidence(
    store: Any,
    user_id: str,
    cache_key: str,
    compute: Callable[[], Awaitable[dict[str, Any]]],
    *,
    ttl_seconds: int,
    bypass_cache: bool = False,
) -> EvidenceCacheResult:
    """Reuse fresh evidence and coalesce identical in-flight provider calls."""
    if not bypass_cache:
        cached = await load_search_evidence(store, user_id, cache_key)
        if cached is not None:
            return EvidenceCacheResult(cached, cache_hit=True, coalesced=False)

    loop = asyncio.get_running_loop()
    flight_cache_key = (
        f"refresh:{cache_key}" if bypass_cache else str(cache_key)
    )
    flight_key = (id(loop), str(user_id), flight_cache_key)
    task = _FLIGHTS.get(flight_key)
    coalesced = task is not None and not task.done()
    if not coalesced:
        async def run() -> dict[str, Any]:
            metadata = await compute()
            await save_search_evidence(
                store,
                user_id,
                cache_key,
                metadata,
                ttl_seconds=ttl_seconds,
            )
            return metadata

        task = asyncio.create_task(run())
        _FLIGHTS[flight_key] = task
    try:
        metadata = await asyncio.shield(task)
        return EvidenceCacheResult(
            copy.deepcopy(metadata),
            cache_hit=False,
            coalesced=coalesced,
        )
    finally:
        if task.done() and _FLIGHTS.get(flight_key) is task:
            _FLIGHTS.pop(flight_key, None)
