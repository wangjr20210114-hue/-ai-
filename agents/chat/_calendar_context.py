"""Bounded current-calendar context injected into every Agent turn."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def calendar_context(workspace: dict) -> str:
    timezone_beijing = timezone(timedelta(hours=8))
    schedules = sorted(
        (item for item in (workspace.get("schedules") or {}).values() if isinstance(item, dict)),
        key=lambda item: int(item.get("start_time") or 0),
    )[:100]
    public = []
    for item in schedules:
        start = int(item.get("start_time") or 0)
        public.append({
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "")[:120],
            "start_time": datetime.fromtimestamp(start, timezone_beijing).isoformat() if start else "",
            "duration_minutes": int(item.get("duration_minutes") or 60),
            "location": str(item.get("location") or "")[:160],
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
