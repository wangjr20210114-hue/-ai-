"""Bounded current-calendar context injected into every Agent turn."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone


def calendar_context(workspace: dict, *, now: int | None = None) -> str:
    timezone_beijing = timezone(timedelta(hours=8))
    timestamp = int(time.time() if now is None else now)
    all_schedules = [
        item for item in (workspace.get("schedules") or {}).values()
        if isinstance(item, dict)
    ]
    upcoming = sorted(
        (item for item in all_schedules if int(item.get("start_time") or 0) >= timestamp),
        key=lambda item: int(item.get("start_time") or 0),
    )[:80]
    recent = sorted(
        (item for item in all_schedules if int(item.get("start_time") or 0) < timestamp),
        key=lambda item: int(item.get("start_time") or 0),
        reverse=True,
    )[:20]
    # Upcoming events are the primary mutation target. Recent history remains
    # available for references such as “和上次一样”, without allowing years
    # of old schedules to evict tomorrow's events from the model context.
    schedules = upcoming + recent
    public = []
    for item in schedules:
        start = int(item.get("start_time") or 0)
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        place = extra.get("place") if isinstance(extra.get("place"), dict) else {}
        public.append({
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "")[:120],
            "start_time": datetime.fromtimestamp(start, timezone_beijing).isoformat() if start else "",
            "duration_minutes": int(item.get("duration_minutes") or 60),
            "location": str(item.get("location") or "")[:160],
            **({
                "place": {
                    "place_id": str(place.get("place_id") or ""),
                    "name": str(place.get("name") or "")[:120],
                    "address": str(place.get("address") or "")[:160],
                    "latitude": place.get("latitude"),
                    "longitude": place.get("longitude"),
                },
            } if place else {}),
        })
    return json.dumps(public, ensure_ascii=False, separators=(",", ":"))


def latest_route_context(workspace: dict) -> str:
    """Expose one bounded, provider-verified route for calendar continuation."""
    route = workspace.get("latest_route_plan")
    if not isinstance(route, dict) or not str(route.get("id") or ""):
        return "无"
    stops = []
    for item in (route.get("ordered_stops") or [])[:12]:
        if not isinstance(item, dict):
            continue
        stops.append({
            "place_id": str(item.get("place_id") or ""),
            "name": str(item.get("name") or "")[:120],
            "address": str(item.get("address") or "")[:180],
        })
    if len(stops) < 2:
        return "无"
    public = {
        "id": str(route.get("id") or ""),
        "created_at": int(route.get("created_at") or 0),
        "ordered_stops": stops,
        "distance_meters": int(route.get("distance_meters") or 0),
        "duration_seconds": int(route.get("duration_seconds") or 0),
    }
    return json.dumps(public, ensure_ascii=False, separators=(",", ":"))
