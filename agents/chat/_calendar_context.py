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
        return "[]"
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
        return "[]"
    public = {
        "id": str(route.get("id") or ""),
        "created_at": int(route.get("created_at") or 0),
        "ordered_stops": stops,
        "distance_meters": int(route.get("distance_meters") or 0),
        "duration_seconds": int(route.get("duration_seconds") or 0),
        "mode": str(route.get("mode") or ""),
        "calendar_hint": str(route.get("calendar_hint") or "")[:240],
    }
    # One recommended-place pair is one leg, but a leg may contain several
    # provider-selected transport sections.  Keep this compact composition in
    # the continuation contract so a later calendar/map turn does not flatten
    # walk -> bus -> rail into a single generic mode.
    legs = []
    for raw_leg in (route.get("legs") or [])[:11]:
        if not isinstance(raw_leg, dict):
            continue
        item = {
            "mode": str(raw_leg.get("mode") or public["mode"]),
            "distance_meters": int(raw_leg.get("distance_meters") or 0),
            "duration_seconds": int(raw_leg.get("duration_seconds") or 0),
        }
        sections = []
        for raw_section in (raw_leg.get("sections") or [])[:8]:
            if not isinstance(raw_section, dict):
                continue
            section = {
                "mode": str(raw_section.get("mode") or item["mode"]),
                "distance_meters": int(raw_section.get("distance_meters") or 0),
                "duration_seconds": int(raw_section.get("duration_seconds") or 0),
            }
            for key in ("line", "vehicle", "geton", "getoff", "station_count", "instruction"):
                value = raw_section.get(key)
                if value not in (None, ""):
                    section[key] = str(value)[:240] if key != "station_count" else max(0, int(value or 0))
            sections.append(section)
        if sections:
            item["sections"] = sections
        legs.append(item)
    if legs:
        public["legs"] = legs
    return json.dumps(public, ensure_ascii=False, separators=(",", ":"))
