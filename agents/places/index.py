"""POST /places: verified Tencent place autocomplete for direct UI edits."""

from .._shared.tencent_location import search_verified_places
from .._shared.auth import require_user


async def handler(ctx):
    require_user(ctx)
    body = ctx.request.body or {}
    query = str(body.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}, 400
    try:
        places = await search_verified_places(
            str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or ""),
            query,
            city=str(body.get("city") or "全国"),
            limit=int(body.get("limit") or 10),
        )
        return {"places": places}
    except Exception as exc:
        return {"error": str(exc)}, 400
