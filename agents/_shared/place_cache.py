"""Persistent bounded cache for Tencent-first POI search results."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from typing import Any

from .data_version import namespace as data_namespace


def _cache_key(query: str, city: str, limit: int) -> str:
    value = json.dumps({
        "query": " ".join(str(query or "").casefold().split())[:160],
        "city": " ".join(str(city or "全国").casefold().split())[:80],
        "limit": max(1, min(20, int(limit))),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _item_value(item: Any) -> dict[str, Any] | None:
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def load_place_cache(
    store: Any,
    user_id: str,
    query: str,
    city: str,
    limit: int,
    *,
    now: int | None = None,
) -> list[dict[str, Any]] | None:
    if store is None:
        return None
    timestamp = int(time.time() if now is None else now)
    try:
        value = _item_value(await store.aget(
            data_namespace("place_search_cache", str(user_id)),
            _cache_key(query, city, limit),
        ))
        places = value.get("places") if isinstance(value, dict) else None
        if int((value or {}).get("expires_at") or 0) > timestamp and isinstance(places, list):
            return copy.deepcopy([item for item in places if isinstance(item, dict)])
    except Exception as exc:
        logging.warning("place cache read failed: %s", exc)
    return None


async def save_place_cache(
    store: Any,
    user_id: str,
    query: str,
    city: str,
    limit: int,
    places: list[dict[str, Any]],
    *,
    now: int | None = None,
) -> None:
    if store is None or not places:
        return
    timestamp = int(time.time() if now is None else now)
    # Public fallback data is deliberately short-lived so a recovered Tencent
    # service quickly becomes authoritative again.
    providers = {str(item.get("provider") or "") for item in places if isinstance(item, dict)}
    ttl_seconds = 2 * 60 * 60 if "openstreetmap" in providers else 24 * 60 * 60
    try:
        await store.aput(
            data_namespace("place_search_cache", str(user_id)),
            _cache_key(query, city, limit),
            {
                "places": copy.deepcopy(places),
                "providers": sorted(providers),
                "created_at": timestamp,
                "expires_at": timestamp + ttl_seconds,
            },
        )
    except Exception as exc:
        logging.warning("place cache write failed: %s", exc)
