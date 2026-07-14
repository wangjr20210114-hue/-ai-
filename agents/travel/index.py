"""Makers travel data endpoint: schedules, places, memory, and daily routes."""

from agents.chat._travel import (
    _env_value,
    delete_schedule,
    list_schedules,
    load_profile,
    plan_daily_route,
    search_places,
    upsert_schedule,
)


async def handler(ctx):
    body = ctx.request.body or {}
    action = str(body.get("action") or "snapshot")
    user_id = str(body.get("user_id") or ctx.conversation_id or "anonymous")
    store = ctx.store.langgraph_store

    if action == "public_map_config":
        # A Tencent JS-SDK key is necessarily visible to the browser. Keep the
        # server WebService credential private and expose only the dedicated
        # browser key at runtime so Makers builds never depend on Vite inlining.
        return {
            "key": _env_value(ctx.env, "VITE_TENCENT_MAP_KEY").strip(),
        }

    if action == "snapshot":
        return {
            "schedules": await list_schedules(store, user_id),
            "profile": await load_profile(store, user_id),
        }

    if action == "search_places":
        places = await search_places(
            ctx.env,
            city=str(body.get("city") or ""),
            query=str(body.get("query") or body.get("keyword") or ""),
            category=str(body.get("category") or "other"),
            limit=int(body.get("limit") or 10),
        )
        return {"places": places}

    if action == "upsert_schedule":
        schedule = body.get("schedule")
        if not isinstance(schedule, dict):
            return {"error": "schedule is required"}, 400
        saved = await upsert_schedule(store, user_id, schedule)
        return {"ok": True, "schedule": saved, "schedule_id": saved["id"]}

    if action == "delete_schedule":
        schedule_id = str(body.get("schedule_id") or "")
        if not schedule_id:
            return {"error": "schedule_id is required"}, 400
        await delete_schedule(store, user_id, schedule_id)
        return {"ok": True}

    if action == "toggle_schedule":
        schedule_id = str(body.get("schedule_id") or "")
        existing = next(
            (item for item in await list_schedules(store, user_id) if item.get("id") == schedule_id),
            None,
        )
        if not existing:
            return {"error": "schedule not found"}, 404
        saved = await upsert_schedule(store, user_id, {**existing, "done": bool(body.get("done"))})
        return {"ok": True, "schedule": saved}

    if action == "daily_route":
        locations = body.get("locations")
        if not isinstance(locations, list):
            return {"error": "locations must be a list"}, 400
        return await plan_daily_route(ctx.env, str(body.get("city") or ""), locations)

    return {"error": f"unsupported action: {action}"}, 400
