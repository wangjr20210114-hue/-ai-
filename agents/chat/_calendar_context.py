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
