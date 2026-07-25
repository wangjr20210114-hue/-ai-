"""POST /places: verified Tencent place autocomplete for direct UI edits."""

from .._shared.tencent_location import search_verified_places
from .._shared.auth import require_user
from .._shared.intelligence import load_intelligence_state
from .._shared.http import error
from .._shared.provider_metering import record_provider_usage


async def handler(ctx):
    identity = require_user(ctx)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, str(identity["user_id"]))
    if not (intelligence.get("skill_preferences") or {}).get("maps", True):
        return error("地图 Skill 已关闭，请先到 Skills 广场开启", 403, code="SKILL_DISABLED")
    body = ctx.request.body or {}
    query = str(body.get("query") or "").strip()
    if not query:
        return error("query is required")
    map_key = str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or "")
    try:
        try:
            places = await search_verified_places(
                map_key,
                query,
                city=str(body.get("city") or "全国"),
                limit=int(body.get("limit") or 10),
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
        return {"places": places}
    except Exception as exc:
        return error(str(exc))
