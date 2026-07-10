"""Candidate generation for TravelAgent."""
from __future__ import annotations

from agents.travel.models import POICategory, ScoredPOI, TravelConstraints
from agents.travel.place_repository import PlaceRepository
from agents.travel.scorer import score_poi


class CandidateEngine:
    def __init__(self, repository: PlaceRepository) -> None:
        self.repository = repository

    async def generate(self, constraints: TravelConstraints) -> list[ScoredPOI]:
        scored = self.repository.recommend(constraints)
        if not scored:
            fetched = await self.repository.search_with_fallback(constraints.destination, constraints.destination, category="travel")
            scored = [score_poi(p, constraints) for p in fetched]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored

    def restaurants_near_area(self, city: str, area: str = "") -> list[ScoredPOI]:
        restaurants = self.repository.search_local(city, area, [POICategory.RESTAURANT]) if area else self.repository.search_local(city, "", [POICategory.RESTAURANT])
        restaurants.sort(key=lambda p: (-p.local_recommend_score, -p.rating, p.avg_cost, p.crowd_level, p.queue_risk))
        return [ScoredPOI(p, score=0.6, reasons=["路线附近餐饮", "可作为用餐补给"]) for p in restaurants[:5]]
