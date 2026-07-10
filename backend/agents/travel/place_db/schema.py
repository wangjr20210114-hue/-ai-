"""Schema for medium and large scale travel place data."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from agents.travel.models import IndoorOutdoor, POI, POICategory


class DataLayer(str, Enum):
    RAW = "l0_raw"
    CLEAN = "l1_clean"
    ONLINE = "l2_online"


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _category(value: Any) -> POICategory:
    if isinstance(value, POICategory):
        return value
    text = str(value or "").strip().lower()
    aliases = {
        "attraction": POICategory.SCENIC,
        "sight": POICategory.SCENIC,
        "景点": POICategory.SCENIC,
        "博物馆": POICategory.MUSEUM,
        "food": POICategory.RESTAURANT,
        "dining": POICategory.RESTAURANT,
        "餐厅": POICategory.RESTAURANT,
        "酒店": POICategory.HOTEL,
        "交通": POICategory.TRANSPORT,
        "活动": POICategory.ACTIVITY,
    }
    if text in aliases:
        return aliases[text]
    try:
        return POICategory(text)
    except ValueError:
        return POICategory.OTHER


def _indoor_outdoor(value: Any) -> IndoorOutdoor:
    if isinstance(value, IndoorOutdoor):
        return value
    text = str(value or "").strip().lower()
    aliases = {"室内": IndoorOutdoor.INDOOR, "户外": IndoorOutdoor.OUTDOOR, "室内外": IndoorOutdoor.MIXED}
    if text in aliases:
        return aliases[text]
    try:
        return IndoorOutdoor(text)
    except ValueError:
        return IndoorOutdoor.MIXED


@dataclass(slots=True)
class PlaceRecord:
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
    rating: float = 0.0
    review_count: int = 0
    popularity: float = 0.5
    local_recommend_score: float = 0.0
    price_level: int = 0
    avg_cost: float = 0.0
    ticket_price: float = 0.0
    opening_hours: str = ""
    closed_days: list[str] = field(default_factory=list)
    duration_minutes: int = 90
    best_time: list[str] = field(default_factory=list)
    avoid_time: list[str] = field(default_factory=list)
    indoor_outdoor: IndoorOutdoor = IndoorOutdoor.MIXED
    weather_sensitivity: float = 0.5
    crowd_level: float = 0.5
    queue_risk: float = 0.5
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
    source: str = "unknown"
    source_confidence: float = 0.5
    updated_at: str = ""
    layer: DataLayer = DataLayer.ONLINE
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, item: dict[str, Any]) -> "PlaceRecord":
        return cls(
            poi_id=str(item.get("poi_id") or item.get("id") or "").strip(),
            name=str(item.get("name") or item.get("title") or "").strip(),
            city=str(item.get("city") or "").strip(),
            country=str(item.get("country") or "中国").strip(),
            address=str(item.get("address") or item.get("nearby_area") or "").strip(),
            lat=_as_float(item.get("lat") or item.get("latitude")),
            lng=_as_float(item.get("lng") or item.get("lon") or item.get("longitude")),
            category=_category(item.get("category")),
            sub_category=str(item.get("sub_category") or "").strip(),
            scene_type=str(item.get("scene_type") or "").strip(),
            alias=_as_list(item.get("alias")),
            tags=_as_list(item.get("tags")),
            rating=_as_float(item.get("rating")),
            review_count=_as_int(item.get("review_count")),
            popularity=_as_float(item.get("popularity"), 0.5),
            local_recommend_score=_as_float(item.get("local_recommend_score")),
            price_level=_as_int(item.get("price_level")),
            avg_cost=_as_float(item.get("avg_cost")),
            ticket_price=_as_float(item.get("ticket_price")),
            opening_hours=str(item.get("opening_hours") or item.get("open_hours") or "").strip(),
            closed_days=_as_list(item.get("closed_days")),
            duration_minutes=_as_int(item.get("duration_minutes"), 90),
            best_time=_as_list(item.get("best_time")),
            avoid_time=_as_list(item.get("avoid_time")),
            indoor_outdoor=_indoor_outdoor(item.get("indoor_outdoor")),
            weather_sensitivity=_as_float(item.get("weather_sensitivity"), 0.5),
            crowd_level=_as_float(item.get("crowd_level"), 0.5),
            queue_risk=_as_float(item.get("queue_risk"), 0.5),
            energy_cost=_as_float(item.get("energy_cost"), 0.5),
            family_friendly=_as_float(item.get("family_friendly"), 0.5),
            elderly_friendly=_as_float(item.get("elderly_friendly"), 0.5),
            photo_score=_as_float(item.get("photo_score"), 0.5),
            cluster_id=str(item.get("cluster_id") or "").strip(),
            nearby_poi_ids=_as_list(item.get("nearby_poi_ids")),
            nearest_transport=str(item.get("nearest_transport") or "").strip(),
            business_area=str(item.get("business_area") or "").strip(),
            nearby_area=str(item.get("nearby_area") or item.get("business_area") or "").strip(),
            recommended_for=_as_list(item.get("recommended_for")),
            avoid_for=_as_list(item.get("avoid_for")),
            alternative_group_id=str(item.get("alternative_group_id") or "").strip(),
            source=str(item.get("source") or "unknown").strip(),
            source_confidence=_as_float(item.get("source_confidence") or item.get("confidence"), 0.5),
            updated_at=str(item.get("updated_at") or "").strip(),
            layer=DataLayer(str(item.get("layer") or DataLayer.ONLINE.value)),
            raw=dict(item),
        )

    @classmethod
    def from_poi(cls, poi: POI) -> "PlaceRecord":
        return cls.from_mapping(asdict(poi))

    def to_poi(self) -> POI:
        return POI(
            poi_id=self.poi_id,
            name=self.name,
            city=self.city,
            country=self.country,
            address=self.address,
            lat=self.lat,
            lng=self.lng,
            category=self.category,
            sub_category=self.sub_category,
            scene_type=self.scene_type,
            alias=list(self.alias),
            tags=list(self.tags),
            review_count=self.review_count,
            avg_cost=self.avg_cost,
            ticket_price=self.ticket_price,
            price_level=self.price_level,
            duration_minutes=self.duration_minutes,
            opening_hours=self.opening_hours,
            closed_days=list(self.closed_days),
            best_time=list(self.best_time),
            avoid_time=list(self.avoid_time),
            popularity=self.popularity,
            rating=self.rating,
            local_recommend_score=self.local_recommend_score,
            crowd_level=self.crowd_level,
            queue_risk=self.queue_risk,
            indoor_outdoor=self.indoor_outdoor,
            weather_sensitivity=self.weather_sensitivity,
            energy_cost=self.energy_cost,
            family_friendly=self.family_friendly,
            elderly_friendly=self.elderly_friendly,
            photo_score=self.photo_score,
            cluster_id=self.cluster_id,
            nearby_poi_ids=list(self.nearby_poi_ids),
            nearest_transport=self.nearest_transport,
            business_area=self.business_area,
            nearby_area=self.nearby_area,
            recommended_for=list(self.recommended_for),
            avoid_for=list(self.avoid_for),
            alternative_group_id=self.alternative_group_id,
            source=self.source,
            source_confidence=self.source_confidence,
            confidence=self.source_confidence,
            updated_at=self.updated_at,
            metadata={"place_db_layer": self.layer.value, "raw": self.raw},
        )

    def dedupe_key(self) -> str:
        city = self.city.strip().lower()
        name = self.name.strip().lower()
        grid_lat = round(self.lat, 3) if self.lat else 0
        grid_lng = round(self.lng, 3) if self.lng else 0
        return f"{city}:{name}:{grid_lat}:{grid_lng}"
