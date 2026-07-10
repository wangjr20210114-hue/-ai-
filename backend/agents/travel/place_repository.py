"""Place repository with seed data, cache hooks, and Tencent Map fallback."""
from __future__ import annotations

from typing import Iterable

from agents.travel.models import Alternative, POI, POICategory, ScoredPOI, TravelConstraints
from agents.travel.place_db.repository import PlaceDatabase
from agents.travel.seed_data import SEED_POIS


class PlaceRepository:
    def __init__(self, seed_pois: Iterable[POI] | None = None) -> None:
        self._db = PlaceDatabase(seed_pois or SEED_POIS)
        self._alternatives: list[Alternative] = []
        self._build_default_alternatives()

    def list_by_city(self, city: str) -> list[POI]:
        return [record.to_poi() for record in self._db.list_by_city(city)]

    def get(self, poi_id: str) -> POI | None:
        record = self._db.get(poi_id)
        return record.to_poi() if record else None

    def upsert(self, poi: POI) -> POI:
        return self._db.upsert(poi).to_poi()

    def search_local(self, city: str, keyword: str = "", categories: list[POICategory] | None = None) -> list[POI]:
        return [record.to_poi() for record in self._db.search(city, keyword, categories)]

    def recommend(self, constraints: TravelConstraints, categories: list[POICategory] | None = None, limit: int = 80) -> list[ScoredPOI]:
        return self._db.recommend(constraints, categories, limit)

    def cluster_summary(self, city: str) -> list[dict]:
        return self._db.cluster_summary(city)

    async def search_with_fallback(self, city: str, keyword: str, *, category: str = "") -> list[POI]:
        local = self.search_local(city, keyword)
        if local:
            return local
        try:
            from services.map_service import map_service
            raw_results = await map_service.place_search(keyword, city)
        except Exception:
            raw_results = []
        normalized: list[POI] = []
        for idx, item in enumerate(raw_results[:5]):
            loc = item.get("location", {})
            poi = POI(
                poi_id=f"map_{city}_{keyword}_{idx}",
                name=item.get("title", keyword),
                city=city,
                address=item.get("address", ""),
                lat=float(loc.get("lat", 0) or 0),
                lng=float(loc.get("lng", 0) or 0),
                category=POICategory.OTHER,
                tags=[category] if category else [],
                nearby_area=item.get("address", ""),
                source="tencent_map",
                source_confidence=0.55,
                confidence=0.55,
                metadata={"raw": item},
            )
            normalized.append(self.upsert(poi))
        return normalized

    def alternatives_for(self, poi: POI, *, reason: str = "") -> list[POI]:
        linked_ids = [a.to_poi_id for a in self._alternatives if a.from_poi_id == poi.poi_id and (not reason or reason in a.reason)]
        linked = [self.get(i) for i in linked_ids]
        linked = [item for item in linked if item]
        if linked:
            return linked
        same_city = [p for p in self.list_by_city(poi.city) if p.poi_id != poi.poi_id and p.category == poi.category]
        same_city.sort(key=lambda p: (abs(p.total_cost - poi.total_cost), -p.rating, p.crowd_level, p.queue_risk))
        return same_city[:3]

    def _build_default_alternatives(self) -> None:
        self._alternatives.extend([
            Alternative("hz_west_lake", "hz_zhejiang_museum", "雨天室内平替", 0.55, 0.7, 0.9, ["雨天", "人文"]),
            Alternative("hz_west_lake", "hz_tea_museum", "雨天/小众平替", 0.5, 0.55, 0.9, ["雨天", "茶文化"]),
            Alternative("hz_longjing", "hz_tea_museum", "下雨或体力不足平替", 0.8, 0.85, 1.0, ["茶文化", "室内"]),
            Alternative("hz_zhiweiguan", "hz_xinbailu", "湖滨午餐平替", 0.8, 0.95, 0.9, ["餐厅", "性价比"]),
            Alternative("bj_forbidden_city", "bj_national_museum", "雨天/票约不上平替", 0.7, 0.85, 1.0, ["博物馆", "人文"]),
            Alternative("sh_bund", "sh_museum", "雨天室内平替", 0.45, 0.7, 1.0, ["雨天", "人文"]),
        ])
