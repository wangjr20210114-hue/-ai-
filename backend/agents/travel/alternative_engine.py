"""Alternative generation for disruption-aware travel planning."""
from __future__ import annotations

from agents.travel.models import POI, ScoredPOI
from agents.travel.place_repository import PlaceRepository


class AlternativeEngine:
    def __init__(self, repository: PlaceRepository) -> None:
        self.repository = repository

    def attach(self, scored: list[ScoredPOI], *, reason: str = "") -> list[ScoredPOI]:
        for item in scored:
            item.alternatives = self.repository.alternatives_for(item.poi, reason=reason)[:3]
        return scored

    def alternatives_for(self, poi: POI, *, reason: str = "") -> list[POI]:
        return self.repository.alternatives_for(poi, reason=reason)