"""Travel domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class POICategory(str, Enum):
    SCENIC = "scenic"
    MUSEUM = "museum"
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    HOTEL = "hotel"
    SHOPPING = "shopping"
    TRANSPORT = "transport"
    ACTIVITY = "activity"
    OTHER = "other"


class IndoorOutdoor(str, Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    MIXED = "mixed"


@dataclass(slots=True)
class POI:
    poi_id: str
    name: str
    city: str
    country: str = "中国"
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    category: POICategory = POICategory.OTHER
    sub_category: str = ""
    scene_type: str = ""
    alias: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    review_count: int = 0
    avg_cost: float = 0.0
    ticket_price: float = 0.0
    price_level: int = 0
    duration_minutes: int = 90
    opening_hours: str = ""
    closed_days: list[str] = field(default_factory=list)
    best_time: list[str] = field(default_factory=list)
    avoid_time: list[str] = field(default_factory=list)
    popularity: float = 0.5
    rating: float = 0.0
    local_recommend_score: float = 0.0
    crowd_level: float = 0.5
    queue_risk: float = 0.5
    indoor_outdoor: IndoorOutdoor = IndoorOutdoor.MIXED
    weather_sensitivity: float = 0.5
    energy_cost: float = 0.5
    family_friendly: float = 0.5
    elderly_friendly: float = 0.5
    photo_score: float = 0.5
    cluster_id: str = ""
    nearby_poi_ids: list[str] = field(default_factory=list)
    nearest_transport: str = ""
    business_area: str = ""
    nearby_area: str = ""
    recommended_for: list[str] = field(default_factory=list)
    avoid_for: list[str] = field(default_factory=list)
    alternative_group_id: str = ""
    source: str = "seed"
    source_confidence: float = 0.8
    confidence: float = 0.8
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        return max(self.avg_cost, 0) + max(self.ticket_price, 0)


@dataclass(slots=True)
class Alternative:
    from_poi_id: str
    to_poi_id: str
    reason: str
    similarity_score: float = 0.0
    distance_score: float = 0.0
    cost_score: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TravelConstraints:
    destination: str
    departure: str = ""
    start_date: str = ""
    end_date: str = ""
    days: int = 1
    travel_style: str = "深度游"
    scenery_preference: str = "人文景观"
    budget: str = ""
    extra_notes: str = ""
    must_visit: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoredPOI:
    poi: POI
    score: float
    reasons: list[str] = field(default_factory=list)
    alternatives: list[POI] = field(default_factory=list)


@dataclass(slots=True)
class ItineraryStop:
    poi: POI
    day: int
    start_hour: int
    start_minute: int
    duration_minutes: int
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    alternatives: list[POI] = field(default_factory=list)


@dataclass(slots=True)
class DayItinerary:
    day: int
    stops: list[ItineraryStop] = field(default_factory=list)
    total_cost: float = 0.0
    total_duration_minutes: int = 0
    map_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TravelPlanDraft:
    constraints: TravelConstraints
    days: list[DayItinerary]
    candidate_count: int = 0
    summary: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)
