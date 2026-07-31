"""POST /routes: server-side real-road route planning and fare estimate."""

import asyncio

from .._infrastructure.providers.tencent_location import plan_verified_route
from .._infrastructure.makers.identity import require_user
from .._infrastructure.http import error
from .._application.intelligence.service import load_intelligence_state
from .._infrastructure.makers.provider_usage_repository import record_provider_usage
from .._infrastructure.makers.route_repository import load_route_cache, save_route_cache
from .._application.skills.registry import capability_is_enabled
from .._domain.entitlements.policy import effective_skill_preferences


async def handler(ctx):
    identity = require_user(ctx)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, str(identity["user_id"]))
    if not capability_is_enabled(
        "route",
        effective_skill_preferences(identity, intelligence.get("skill_preferences")),
    ):
        return error("地图 Skill 已关闭，请先到 Skills 广场开启", 403, code="SKILL_DISABLED")
    body = ctx.request.body or {}
    places = body.get("places") or []
    if not isinstance(places, list):
        return error("places must be a list")
    optimize = bool(body.get("optimize", False))
    preferences = intelligence.get("map_preferences") or {}
    mode = str(body.get("mode") or preferences.get("preferred_route_mode") or "driving").strip().lower()
    if mode not in {"driving", "transit", "walking", "bicycling"}:
        return error("路线方式必须是 driving、transit、walking 或 bicycling")
    strategy = str(
        body.get("strategy") or preferences.get("route_strategy") or "time_then_cost"
    ).strip().lower()
    if strategy not in {"time_then_cost", "least_time", "least_cost"}:
        return error("路线策略必须是 time_then_cost、least_time 或 least_cost")
    near_time_tolerance = max(
        0,
        min(30, int(preferences.get("near_time_tolerance_minutes", 10) or 0)),
    )
    route_stop_limit = max(2, min(12, int(preferences.get("route_stop_limit") or 8)))
    if not 2 <= len(places) <= route_stop_limit:
        return error(
            f"当前地图设置允许单条路线包含 2 到 {route_stop_limit} 个地点；"
            "请调整地点数量或到设置中提高上限"
        )
    search_timeout = max(10.0, min(55.0, float(preferences.get("search_timeout_seconds") or 30)))
    route_timeout = min(18.0, max(8.0, 58.0 - search_timeout))
    try:
        cached_route = await load_route_cache(
            getattr(ctx.store, "langgraph_store", None),
            str(identity["user_id"]),
            places,
            optimize,
            mode=mode,
            strategy=strategy,
            near_time_tolerance_minutes=near_time_tolerance,
        )
    except (TypeError, ValueError):
        return error("地点坐标格式无效")
    store = getattr(ctx.store, "langgraph_store", None)
    if cached_route is not None:
        return {"route": cached_route}
    try:
        map_key = str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or "")
        try:
            route = await asyncio.wait_for(
                plan_verified_route(
                    map_key,
                    places,
                    optimize=optimize,
                    **({"mode": mode} if mode != "driving" else {}),
                    strategy=strategy,
                    near_time_tolerance_minutes=near_time_tolerance,
                ),
                timeout=route_timeout,
            )
        finally:
            if map_key:
                await record_provider_usage(
                    store,
                    str(identity["user_id"]),
                    "tencent_maps",
                    "requests",
                    1,
                    source="routes_endpoint",
                )
        route = await save_route_cache(
            store,
            str(identity["user_id"]),
            places,
            optimize,
            route,
            mode=mode,
            strategy=strategy,
            near_time_tolerance_minutes=near_time_tolerance,
        )
        provider_places = route.get("places")
        if isinstance(provider_places, list) and provider_places != places:
            route = await save_route_cache(
                store,
                str(identity["user_id"]),
                provider_places,
                optimize,
                route,
                mode=mode,
                strategy=strategy,
                near_time_tolerance_minutes=near_time_tolerance,
            )
        return {"route": route}
    except Exception as exc:
        return error(str(exc))
