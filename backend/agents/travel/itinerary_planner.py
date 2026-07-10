"""Itinerary planning for TravelAgent v1."""
from __future__ import annotations

from agents.travel.alternative_engine import AlternativeEngine
from agents.travel.candidate_engine import CandidateEngine
from agents.travel.map_renderer import MapRenderer
from agents.travel.models import DayItinerary, ItineraryStop, POICategory, ScoredPOI, TravelConstraints, TravelPlanDraft
from agents.travel.route_optimizer import RouteOptimizer


class ItineraryPlanner:
    def __init__(self, candidates: CandidateEngine, alternatives: AlternativeEngine, optimizer: RouteOptimizer, map_renderer: MapRenderer) -> None:
        self.candidates = candidates
        self.alternatives = alternatives
        self.optimizer = optimizer
        self.map_renderer = map_renderer

    async def plan(self, constraints: TravelConstraints) -> TravelPlanDraft:
        scored = await self.candidates.generate(constraints)
        scored = self.alternatives.attach(scored)
        non_food = [s for s in scored if s.poi.category not in {POICategory.RESTAURANT, POICategory.CAFE, POICategory.HOTEL, POICategory.TRANSPORT}]
        food = [s for s in scored if s.poi.category == POICategory.RESTAURANT]
        per_day = 5 if "特种兵" in constraints.travel_style else 3
        days: list[DayItinerary] = []
        used: set[str] = set()
        for day_idx in range(1, max(1, constraints.days) + 1):
            day_candidates = [s for s in non_food if s.poi.poi_id not in used][:per_day]
            for item in day_candidates:
                used.add(item.poi.poi_id)
            ordered = self.optimizer.order(day_candidates)
            stops: list[ItineraryStop] = []
            hour = 9
            minute = 0
            for idx, item in enumerate(ordered):
                if idx == 2:
                    restaurant = self._pick_restaurant(constraints.destination, item, food)
                    if restaurant:
                        stops.append(ItineraryStop(restaurant.poi, day_idx, 12, 10, restaurant.poi.duration_minutes, restaurant.score, restaurant.reasons, restaurant.alternatives))
                        hour = 13
                        minute = 20
                stops.append(ItineraryStop(item.poi, day_idx, hour, minute, item.poi.duration_minutes, item.score, item.reasons, item.alternatives))
                hour += max(1, item.poi.duration_minutes // 60) + 1
                minute = 0
            day = DayItinerary(day=day_idx, stops=stops)
            day.total_cost = round(sum(s.poi.total_cost for s in stops), 2)
            day.total_duration_minutes = sum(s.duration_minutes for s in stops)
            day.map_data = self.map_renderer.build_day_map(day)
            days.append(day)
        return TravelPlanDraft(
            constraints=constraints,
            days=days,
            candidate_count=len(scored),
            summary=f"为{constraints.destination}生成{len(days)}天{constraints.travel_style}次优行程，优先考虑{constraints.scenery_preference}。",
            diagnostics={"per_day": per_day, "selected_pois": len(used)},
        )

    def _pick_restaurant(self, city: str, anchor: ScoredPOI, restaurants: list[ScoredPOI]) -> ScoredPOI | None:
        same_area = [r for r in restaurants if r.poi.nearby_area and r.poi.nearby_area == anchor.poi.nearby_area]
        pool = same_area or restaurants or self.candidates.restaurants_near_area(city, anchor.poi.nearby_area)
        return pool[0] if pool else None