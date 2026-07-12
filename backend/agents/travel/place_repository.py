"""Place repository — OSM DB primary, Tencent Maps fallback. Zero seed data."""
from __future__ import annotations

from agents.travel.models import Alternative, POI, POICategory, ScoredPOI, TravelConstraints
from agents.travel.place_db.repository import PlaceDatabase


class PlaceRepository:
    def __init__(self) -> None:
        self._db = PlaceDatabase([])  # empty, no seed data
        self._alternatives: list[Alternative] = []

    def list_by_city(self, city: str) -> list[POI]:
        return [r.to_poi() for r in self._db.list_by_city(city)]

    def get(self, poi_id: str) -> POI | None:
        r = self._db.get(poi_id)
        return r.to_poi() if r else None

    def upsert(self, poi: POI) -> POI:
        return self._db.upsert(poi).to_poi()

    def search_local(self, city: str, keyword: str = "", categories: list[POICategory] | None = None) -> list[POI]:
        return [r.to_poi() for r in self._db.search(city, keyword, categories)]

    def recommend(self, constraints: TravelConstraints, categories: list[POICategory] | None = None, limit: int = 80) -> list[ScoredPOI]:
        return self._db.recommend(constraints, categories, limit)

    def cluster_summary(self, city: str) -> list[dict]:
        return self._db.cluster_summary(city)

    async def search_with_fallback(self, city: str, keyword: str, *, category: str = "") -> list[POI]:
        """OSM DB → Tencent Maps. No hardcoded data."""
        # 1. Try local in-memory cache (from previous DB queries)
        local = self.search_local(city, keyword)
        if local:
            return local

        # 2. Try remote OSM DB
        try:
            from services.place_db_service import search_places as db_search
            results = await db_search(keyword + " " + city, limit=15)
            if results:
                return self._import_db_results(results, city, category)
        except Exception:
            pass

        # 3. Fallback to Tencent Maps
        try:
            from services.map_service import map_service
            raw = await map_service.place_search(keyword, city)
        except Exception:
            raw = []
        return self._import_tmap_results(raw, city, keyword, category)

    def _import_db_results(self, results: list[dict], city: str, category: str) -> list[POI]:
        imported: list[POI] = []
        for idx, r in enumerate(results[:15]):
            cat = POICategory.OTHER
            t = r.get("type", "")
            if t in ("restaurant", "fast_food", "cafe", "bar"):
                cat = POICategory.RESTAURANT
            elif t in ("hotel", "hostel", "motel"):
                cat = POICategory.HOTEL
            elif t in ("museum", "gallery"):
                cat = POICategory.MUSEUM
            elif t in ("mall", "department_store"):
                cat = POICategory.SHOPPING
            elif t in ("viewpoint", "attraction", "park"):
                cat = POICategory.SCENIC

            poi = POI(
                poi_id=f"osm_{city}_{idx}",
                name=r.get("name", keyword),
                city=city,
                address=r.get("street", "") or r.get("city", ""),
                lat=float(r.get("lat", 0) or 0),
                lng=float(r.get("lng", 0) or 0),
                category=cat,
                tags=[t] if t else [],
                nearby_area=r.get("city", ""),
                source="osm_db",
                source_confidence=0.8,
                confidence=0.8,
                opening_hours=r.get("opening_hours", ""),
                metadata={"raw": r},
            )
            imported.append(self.upsert(poi))
        return imported

    def _import_tmap_results(self, raw: list[dict], city: str, keyword: str, category: str) -> list[POI]:
        imported: list[POI] = []
        for idx, item in enumerate(raw[:10]):
            loc = item.get("location", {})
            poi = POI(
                poi_id=f"tmap_{city}_{keyword}_{idx}",
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
            imported.append(self.upsert(poi))
        return imported

    def alternatives_for(self, poi: POI, *, reason: str = "") -> list[POI]:
        """Dynamic alternatives based on same city + category, no hardcoding."""
        same_city = [p for p in self.list_by_city(poi.city) if p.poi_id != poi.poi_id and p.category == poi.category]
        same_city.sort(key=lambda p: (abs(p.total_cost - poi.total_cost), -p.rating, p.crowd_level, p.queue_risk))
        return same_city[:3]
