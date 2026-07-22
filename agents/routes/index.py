"""POST /routes: server-side real-road route planning and fare estimate."""

import copy
import hashlib
import json
import logging
import time

from .._shared.tencent_location import plan_verified_route
from .._shared.auth import require_user
from .._shared.data_version import namespace as data_namespace
from .._shared.http import error
from .._shared.intelligence import load_intelligence_state

CACHE_TTL_SECONDS = 6 * 60 * 60


def _cache_key(places: list[dict], optimize: bool) -> str:
    normalized = [{
        "place_id": str(item.get("place_id") or ""),
        "latitude": round(float(item.get("latitude") or 0), 6),
        "longitude": round(float(item.get("longitude") or 0), 6),
    } for item in places if isinstance(item, dict)]
    value = json.dumps({"places": normalized, "optimize": optimize}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _item_value(item):
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def handler(ctx):
    identity = require_user(ctx)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, str(identity["user_id"]))
    if not (intelligence.get("skill_preferences") or {}).get("maps", True):
        return error("地图 Skill 已关闭，请先到 Skills 广场开启", 403, code="SKILL_DISABLED")
    body = ctx.request.body or {}
    places = body.get("places") or []
    if not isinstance(places, list):
        return error("places must be a list")
    optimize = bool(body.get("optimize", False))
    try:
        cache_key = _cache_key(places, optimize)
    except (TypeError, ValueError):
        return error("地点坐标格式无效")
    # v1 may contain Tencent minutes mislabeled as seconds.
    namespace = data_namespace("route_cache", str(identity["user_id"]))
    store = getattr(ctx.store, "langgraph_store", None)
    now = int(time.time())
    if store is not None:
        try:
            cached = _item_value(await store.aget(namespace, cache_key))
            if cached and int(cached.get("expires_at") or 0) > now and isinstance(cached.get("route"), dict):
                route = copy.deepcopy(cached["route"])
                route["cache"] = {"hit": True, "expires_at": int(cached["expires_at"])}
                return {"route": route}
        except Exception as exc:
            logging.warning("route cache read failed: %s", exc)
    try:
        route = await plan_verified_route(
            str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or ""),
            places,
            optimize=optimize,
        )
        expires_at = now + CACHE_TTL_SECONDS
        if store is not None:
            try:
                await store.aput(namespace, cache_key, {"route": copy.deepcopy(route), "created_at": now, "expires_at": expires_at})
            except Exception as exc:
                logging.warning("route cache write failed: %s", exc)
        route = {**route, "cache": {"hit": False, "expires_at": expires_at}}
        return {"route": route}
    except Exception as exc:
        return error(str(exc))
