"""Maker-backed short-lived repository for Tencent road routes."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from typing import Any

from .data_version import namespace as data_namespace


DEFAULT_ROUTE_CACHE_TTL_SECONDS = 30 * 60


def route_cache_key(
    places: list[dict],
    optimize: bool,
    mode: str = "driving",
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
) -> str:
    normalized = [{
        "place_id": str(item.get("place_id") or ""),
        "latitude": round(float(item.get("latitude") or 0), 6),
        "longitude": round(float(item.get("longitude") or 0), 6),
    } for item in places if isinstance(item, dict)]
    value = json.dumps(
        {
            "places": normalized,
            "optimize": bool(optimize),
            "mode": str(mode or "driving"),
            "strategy": str(strategy or "time_then_cost"),
            "near_time_tolerance_minutes": max(
                0, min(30, int(near_time_tolerance_minutes or 0)),
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _item_value(item: Any) -> dict[str, Any] | None:
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def load_route_cache(
    store: Any,
    user_id: str,
    places: list[dict],
    optimize: bool,
    *,
    mode: str = "driving",
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
    now: int | None = None,
) -> dict[str, Any] | None:
    if store is None:
        return None
    timestamp = int(time.time() if now is None else now)
    try:
        cached = _item_value(await store.aget(
            data_namespace("route_cache", str(user_id)),
            route_cache_key(
                places,
                optimize,
                mode,
                strategy,
                near_time_tolerance_minutes,
            ),
        ))
        if (
            cached
            and int(cached.get("expires_at") or 0) > timestamp
            and isinstance(cached.get("route"), dict)
        ):
            route = copy.deepcopy(cached["route"])
            route["cache"] = {
                "hit": True,
                "expires_at": int(cached["expires_at"]),
            }
            return route
    except Exception as exc:
        logging.warning("route cache read failed: %s", exc)
    return None


async def save_route_cache(
    store: Any,
    user_id: str,
    places: list[dict],
    optimize: bool,
    route: dict[str, Any],
    *,
    mode: str = "driving",
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
    now: int | None = None,
    ttl_seconds: int = DEFAULT_ROUTE_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    timestamp = int(time.time() if now is None else now)
    expires_at = timestamp + max(60, min(6 * 60 * 60, int(ttl_seconds)))
    if store is not None:
        try:
            await store.aput(
                data_namespace("route_cache", str(user_id)),
                route_cache_key(
                    places,
                    optimize,
                    mode,
                    strategy,
                    near_time_tolerance_minutes,
                ),
                {
                    "route": copy.deepcopy(route),
                    "created_at": timestamp,
                    "expires_at": expires_at,
                },
            )
        except Exception as exc:
            logging.warning("route cache write failed: %s", exc)
    return {**route, "cache": {"hit": False, "expires_at": expires_at}}
