"""Controller for bounded Tencent-first place search."""

import asyncio

from .._infrastructure.providers.tencent_location import search_verified_places_bounded
from .._infrastructure.makers.identity import require_user
from .._application.intelligence.service import load_intelligence_state
from .._infrastructure.http import error
from .._infrastructure.makers.provider_usage_repository import record_provider_usage
from .._infrastructure.makers.place_repository import load_place_cache, save_place_cache
from .._application.skills.access import resolve_skill_access


async def handler(ctx):
    identity = require_user(ctx)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, str(identity["user_id"]))
    access = resolve_skill_access(identity, intelligence.get("skill_preferences"))
    if not access.allows_capability("places"):
        if access.reason_for_capability("places") == "login_required":
            return error("请登录后使用地点搜索", 403, code="LOGIN_REQUIRED")
        return error("地图 Skill 已关闭，请先到 Skills 广场开启", 403, code="SKILL_DISABLED")
    body = ctx.request.body or {}
    query = str(body.get("query") or "").strip()
    if not query:
        return error("query is required")
    map_key = str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or "")
    preferences = intelligence.get("map_preferences") or {}
    result_limit = max(3, min(12, int(preferences.get("place_result_limit") or 6)))
    timeout_seconds = max(10.0, min(55.0, float(preferences.get("search_timeout_seconds") or 30)))
    try:
        limit = min(result_limit, int(body.get("limit") or result_limit))
        city = str(body.get("city") or "全国")
        cached = await load_place_cache(
            ctx.store.langgraph_store,
            str(identity["user_id"]),
            query,
            city,
            limit,
        )
        if cached is not None:
            return {"places": cached, "cache": {"hit": True}}
        try:
            places = await asyncio.wait_for(
                search_verified_places_bounded(
                    map_key,
                    query,
                    city=city,
                    limit=limit,
                    timeout_seconds=timeout_seconds,
                ),
                timeout=timeout_seconds,
            )
        finally:
            if map_key:
                await record_provider_usage(
                    ctx.store.langgraph_store,
                    str(identity["user_id"]),
                    "tencent_maps",
                    "requests",
                    1,
                    source="places_endpoint",
                )
        await save_place_cache(
            ctx.store.langgraph_store,
            str(identity["user_id"]),
            query,
            city,
            limit,
            places,
        )
        return {"places": places, "cache": {"hit": False}}
    except Exception as exc:
        return error(str(exc))
