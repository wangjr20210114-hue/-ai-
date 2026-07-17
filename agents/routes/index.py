"""POST /routes: server-side real-road route planning and fare estimate."""

from ..shared.tencent_location import plan_verified_route
from ..shared.auth import require_user


async def handler(ctx):
    require_user(ctx)
    body = ctx.request.body or {}
    places = body.get("places") or []
    if not isinstance(places, list):
        return {"error": "places must be a list"}, 400
    try:
        route = await plan_verified_route(
            str(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY") or ctx.env.get("VITE_TENCENT_MAP_KEY") or ""),
            places,
            optimize=bool(body.get("optimize", False)),
        )
        return {"route": route}
    except Exception as exc:
        return {"error": str(exc)}, 400
