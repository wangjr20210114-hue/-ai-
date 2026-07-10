"""TravelAgent v1: explainable suboptimal itinerary planner."""
from __future__ import annotations

from dataclasses import asdict

from agents.travel.alternative_engine import AlternativeEngine
from agents.travel.candidate_engine import CandidateEngine
from agents.travel.constraints import normalize_constraints
from agents.travel.disruption_engine import DisruptionEngine
from agents.travel.itinerary_planner import ItineraryPlanner
from agents.travel.map_renderer import MapRenderer
from agents.travel.models import TravelConstraints, TravelPlanDraft
from agents.travel.place_repository import PlaceRepository
from agents.travel.route_optimizer import RouteOptimizer


class TravelAgent:
    def __init__(self, repository: PlaceRepository | None = None) -> None:
        self.repository = repository or PlaceRepository()
        self.candidates = CandidateEngine(self.repository)
        self.alternatives = AlternativeEngine(self.repository)
        self.optimizer = RouteOptimizer()
        self.map_renderer = MapRenderer()
        self.planner = ItineraryPlanner(self.candidates, self.alternatives, self.optimizer, self.map_renderer)
        self.disruption = DisruptionEngine(self.repository)

    async def plan_trip(self, raw_constraints: dict | TravelConstraints) -> TravelPlanDraft:
        constraints = raw_constraints if isinstance(raw_constraints, TravelConstraints) else normalize_constraints(raw_constraints)
        return await self.planner.plan(constraints)

    async def plan_trip_dict(self, raw_constraints: dict | TravelConstraints) -> dict:
        draft = await self.plan_trip(raw_constraints)
        return self.to_dict(draft)

    def to_dict(self, draft: TravelPlanDraft) -> dict:
        return {
            "summary": draft.summary,
            "candidate_count": draft.candidate_count,
            "diagnostics": draft.diagnostics,
            "constraints": asdict(draft.constraints),
            "clusters": self.repository.cluster_summary(draft.constraints.destination)[:12],
            "days": [
                {
                    "day": day.day,
                    "total_cost": day.total_cost,
                    "total_duration_minutes": day.total_duration_minutes,
                    "map_data": day.map_data,
                    "stops": [
                        {
                            "poi_id": stop.poi.poi_id,
                            "name": stop.poi.name,
                            "category": stop.poi.category.value,
                            "address": stop.poi.address,
                            "cluster_id": stop.poi.cluster_id,
                            "nearby_poi_ids": stop.poi.nearby_poi_ids,
                            "recommended_for": stop.poi.recommended_for,
                            "start_time": f"{stop.start_hour:02d}:{stop.start_minute:02d}",
                            "duration_minutes": stop.duration_minutes,
                            "lat": stop.poi.lat,
                            "lng": stop.poi.lng,
                            "cost": stop.poi.total_cost,
                            "score": stop.score,
                            "reasons": stop.reasons,
                            "tags": stop.poi.tags,
                            "alternatives": [
                                {
                                    "poi_id": alt.poi_id,
                                    "name": alt.name,
                                    "category": alt.category.value,
                                    "lat": alt.lat,
                                    "lng": alt.lng,
                                    "tags": alt.tags,
                                    "cluster_id": alt.cluster_id,
                                    "recommended_for": alt.recommended_for,
                                }
                                for alt in stop.alternatives
                            ],
                        }
                        for stop in day.stops
                    ],
                }
                for day in draft.days
            ],
        }
