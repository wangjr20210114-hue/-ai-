"""Disruption handling for proactive travel changes."""
from __future__ import annotations

from agents.travel.models import POI
from agents.travel.place_repository import PlaceRepository


class DisruptionEngine:
    def __init__(self, repository: PlaceRepository) -> None:
        self.repository = repository

    def alternatives_for_weather(self, poi: POI, weather: str = "") -> list[POI]:
        if poi.weather_sensitivity > 0.5 or "雨" in weather:
            return self.repository.alternatives_for(poi, reason="雨天")
        return self.repository.alternatives_for(poi)

    def explain_weather_risk(self, poi: POI, weather: str = "") -> str:
        if poi.weather_sensitivity > 0.7:
            return f"{poi.name} 对天气较敏感，{weather or '恶劣天气'}时建议准备平替。"
        return f"{poi.name} 天气风险较低。"