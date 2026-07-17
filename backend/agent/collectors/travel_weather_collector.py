"""Travel weather guardian for upcoming travel schedules."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from agent.collectors.base import CollectedSignal, CollectionBatch
from config import settings
from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID
from services.map_service import map_service


class WeatherProvider(Protocol):
    async def get_weather(self, city: str) -> dict[str, Any]: ...


_RISK_TERMS = ("雨", "雪", "雷", "暴", "台风", "大风", "冰雹", "沙尘", "高温")
_OUTDOOR_TYPES = {"scenic", "outdoor", "park", "hiking", "beach", "mountain"}


class TravelWeatherCollector:
    name = "travel_weather"

    def __init__(
        self,
        horizon_days: int = 7,
        temperature_delta: float = 5.0,
        scan_interval_seconds: int = 1800,
        provider: WeatherProvider | None = None,
    ) -> None:
        self.horizon_days = max(1, horizon_days)
        self.temperature_delta = max(1.0, temperature_delta)
        self.scan_interval_seconds = max(60, scan_interval_seconds)
        self.provider = provider or map_service
        self._uses_default_provider = provider is None

    async def collect(
        self,
        checkpoint: dict[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> CollectionBatch:
        previous = dict((checkpoint or {}).get("cities") or {})
        ts = now or time.time()
        if self._uses_default_provider and not settings.tencent_map_key:
            return CollectionBatch(
                next_checkpoint={"schema_version": 1, "cities": previous, "checked_at": ts},
                next_run_at=ts + self.scan_interval_seconds,
                diagnostics={"skipped": "tencent_map_key_not_configured"},
            )

        db = await get_db()
        cursor = await db.execute(
            "SELECT id,title,start_time,location,extra FROM schedules WHERE session_id=? AND done=0 "
            "AND category='travel' AND start_time>? AND start_time<=? ORDER BY start_time,id",
            (LOCAL_USER_ID, ts, ts + self.horizon_days * 86400),
        )
        city_schedules: dict[str, list[dict[str, Any]]] = {}
        for row in await cursor.fetchall():
            item = dict(row)
            try:
                extra = json.loads(item.get("extra") or "{}")
            except (json.JSONDecodeError, TypeError):
                extra = {}
            item["extra_json"] = extra
            city = str(extra.get("city") or item.get("location") or "").strip()
            if city:
                city_schedules.setdefault(city, []).append(item)

        events: list[CollectedSignal] = []
        next_cities: dict[str, Any] = {}
        provider_errors: dict[str, str] = {}
        for city, schedules in city_schedules.items():
            try:
                weather = await self.provider.get_weather(city)
            except Exception as error:  # provider boundary; preserve old snapshot
                provider_errors[city] = f"{type(error).__name__}: {error}"
                next_cities[city] = previous.get(city, {})
                continue
            if weather.get("error"):
                provider_errors[city] = str(weather.get("error"))
                next_cities[city] = previous.get(city, {})
                continue
            current = {
                "weather": str(weather.get("weather") or ""),
                "temperature": float(weather.get("temperature") or 0),
                "tips": str(weather.get("tips") or ""),
                "observed_at": ts,
            }
            old = previous.get(city) or {}
            next_cities[city] = current
            if not old:
                continue  # establish a baseline before alerting

            weather_changed = current["weather"] != str(old.get("weather") or "")
            temp_changed = (
                abs(current["temperature"] - float(old.get("temperature") or 0))
                >= self.temperature_delta
            )
            if not (weather_changed or temp_changed):
                continue

            outdoor_ids = []
            for item in schedules:
                extra = item.get("extra_json") or {}
                place_type = str(extra.get("place_type") or "").lower()
                if place_type in _OUTDOOR_TYPES or bool(extra.get("outdoor")):
                    outdoor_ids.append(str(item["id"]))
            risk_weather = any(term in current["weather"] for term in _RISK_TERMS)
            event_type = "travel.outdoor_risk" if risk_weather and outdoor_ids else "travel.weather_changed"
            fingerprint_source = {
                "weather": current["weather"],
                "temperature_bucket": round(current["temperature"] / self.temperature_delta),
                "event_type": event_type,
                "outdoor_ids": outdoor_ids,
            }
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_source, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:16]
            earliest = min(schedules, key=lambda item: item["start_time"])
            summary = (
                f"{city}天气由 {old.get('weather') or '未知'} / {old.get('temperature', '-')}℃ "
                f"变化为 {current['weather'] or '未知'} / {current['temperature']}℃。{current['tips']}"
            )
            events.append(
                CollectedSignal(
                    event_type=event_type,
                    source="travel_weather_collector",
                    subject_id=str(earliest["id"]),
                    occurred_at=ts,
                    dedup_key=f"travel-weather:{city}:{fingerprint}",
                    payload={
                        "city": city,
                        "summary": summary,
                        "weather": current,
                        "previous_weather": old,
                        "schedule_ids": [str(item["id"]) for item in schedules],
                        "outdoor_schedule_ids": outdoor_ids,
                        "earliest_start_time": earliest["start_time"],
                        "requires_alternative_draft": event_type == "travel.outdoor_risk",
                    },
                )
            )
        return CollectionBatch(
            events=events,
            next_checkpoint={
                "schema_version": 1,
                "cities": next_cities,
                "checked_at": ts,
            },
            next_run_at=ts + self.scan_interval_seconds,
            diagnostics={
                "cities_checked": len(city_schedules),
                "events": len(events),
                "provider_errors": provider_errors,
            },
        )
