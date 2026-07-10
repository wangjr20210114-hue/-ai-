"""Runtime repository for cleaned online POI records."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from agents.travel.models import POI, POICategory, ScoredPOI, TravelConstraints
from agents.travel.place_db.cluster_builder import PlaceCluster, build_clusters
from agents.travel.place_db.features import score_record
from agents.travel.place_db.schema import PlaceRecord
from agents.travel.place_db.spatial_index import GridSpatialIndex
from agents.travel.place_db.tagger import clean_record


class PlaceDatabase:
    def __init__(self, records: Iterable[PlaceRecord | POI] = ()) -> None:
        self._records: dict[str, PlaceRecord] = {}
        self._by_city: dict[str, list[PlaceRecord]] = defaultdict(list)
        self._by_category: dict[tuple[str, POICategory], list[PlaceRecord]] = defaultdict(list)
        self._clusters: dict[str, PlaceCluster] = {}
        self._spatial = GridSpatialIndex()
        self.load(records)

    def load(self, records: Iterable[PlaceRecord | POI]) -> None:
        clean: list[PlaceRecord] = []
        for item in records:
            record = item if isinstance(item, PlaceRecord) else PlaceRecord.from_poi(item)
            normalized = clean_record(record)
            if normalized:
                clean.append(normalized)
        clustered, clusters = build_clusters(_dedupe_records(clean))
        self._records = {record.poi_id: record for record in clustered}
        self._clusters = {cluster.cluster_id: cluster for cluster in clusters}
        self._rebuild_indexes()

    def upsert(self, item: PlaceRecord | POI) -> PlaceRecord:
        record = item if isinstance(item, PlaceRecord) else PlaceRecord.from_poi(item)
        normalized = clean_record(record)
        if not normalized:
            raise ValueError("Cannot upsert invalid place record")
        existing = self._records.get(normalized.poi_id)
        if existing and existing.cluster_id and not normalized.cluster_id:
            normalized = replace(normalized, cluster_id=existing.cluster_id, nearby_poi_ids=existing.nearby_poi_ids)
        self._records[normalized.poi_id] = normalized
        self._rebuild_indexes()
        return normalized

    def get(self, poi_id: str) -> PlaceRecord | None:
        return self._records.get(poi_id)

    def list_by_city(self, city: str) -> list[PlaceRecord]:
        return list(self._by_city.get(city, [])) if city else list(self._records.values())

    def search(
        self,
        city: str,
        keyword: str = "",
        categories: list[POICategory] | None = None,
        limit: int = 100,
    ) -> list[PlaceRecord]:
        if categories:
            pool: list[PlaceRecord] = []
            for category in categories:
                pool.extend(self._by_category.get((city, category), []))
        else:
            pool = self.list_by_city(city)
        if keyword:
            lowered = keyword.lower()
            pool = [
                record
                for record in pool
                if lowered in record.name.lower()
                or any(lowered in alias.lower() for alias in record.alias)
                or lowered in " ".join(record.tags).lower()
                or lowered in record.nearby_area.lower()
                or lowered in record.business_area.lower()
            ]
        pool.sort(key=lambda record: (record.local_recommend_score, record.rating, record.popularity), reverse=True)
        return pool[:limit]

    def nearby(self, city: str, lat: float, lng: float, radius_km: float = 2.0, limit: int = 20) -> list[PlaceRecord]:
        return [record for record, _dist in self._spatial.nearby(city, lat, lng, radius_km, limit)]

    def recommend(self, constraints: TravelConstraints, categories: list[POICategory] | None = None, limit: int = 80) -> list[ScoredPOI]:
        scores = [score_record(record, constraints) for record in self.search(constraints.destination, categories=categories, limit=limit * 3)]
        scores.sort(key=lambda item: item.score, reverse=True)
        return [ScoredPOI(item.record.to_poi(), item.score, item.reasons) for item in scores[:limit]]

    def cluster_summary(self, city: str) -> list[dict]:
        clusters = [cluster for cluster in self._clusters.values() if not city or cluster.city == city]
        clusters.sort(key=lambda cluster: cluster.score, reverse=True)
        return [
            {
                "cluster_id": cluster.cluster_id,
                "city": cluster.city,
                "center_lat": cluster.center_lat,
                "center_lng": cluster.center_lng,
                "score": cluster.score,
                "poi_count": len(cluster.records),
                "top_pois": [record.name for record in cluster.records[:5]],
            }
            for cluster in clusters
        ]

    def _rebuild_indexes(self) -> None:
        self._by_city = defaultdict(list)
        self._by_category = defaultdict(list)
        records = list(self._records.values())
        for record in records:
            self._by_city[record.city].append(record)
            self._by_category[(record.city, record.category)].append(record)
        for values in self._by_city.values():
            values.sort(key=lambda record: (record.local_recommend_score, record.rating, record.popularity), reverse=True)
        self._spatial.build(records)


def _dedupe_records(records: list[PlaceRecord]) -> list[PlaceRecord]:
    selected: dict[str, PlaceRecord] = {}
    for record in records:
        key = record.dedupe_key()
        current = selected.get(key)
        if not current or _quality(record) > _quality(current):
            selected[key] = record
    return list(selected.values())


def _quality(record: PlaceRecord) -> float:
    return record.source_confidence + record.local_recommend_score + record.rating / 5 + min(1.0, record.review_count / 5000)
