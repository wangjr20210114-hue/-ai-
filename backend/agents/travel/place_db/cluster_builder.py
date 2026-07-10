"""Cluster places before day-route planning."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from agents.travel.models import POICategory
from agents.travel.place_db.schema import PlaceRecord
from agents.travel.place_db.spatial_index import haversine_km


@dataclass(slots=True)
class PlaceCluster:
    cluster_id: str
    city: str
    records: list[PlaceRecord]
    center_lat: float
    center_lng: float
    score: float


def build_clusters(records: list[PlaceRecord], radius_km: float = 1.8) -> tuple[list[PlaceRecord], list[PlaceCluster]]:
    by_city: dict[str, list[PlaceRecord]] = defaultdict(list)
    for record in records:
        by_city[record.city].append(record)

    clustered_records: list[PlaceRecord] = []
    clusters: list[PlaceCluster] = []
    for city, city_records in by_city.items():
        pending = [record for record in city_records if record.lat and record.lng]
        no_geo = [record for record in city_records if not record.lat or not record.lng]
        assigned: set[str] = set()
        for seed in sorted(pending, key=_cluster_seed_score, reverse=True):
            if seed.poi_id in assigned:
                continue
            members = [
                item
                for item in pending
                if item.poi_id not in assigned and haversine_km(seed.lat, seed.lng, item.lat, item.lng) <= radius_km
            ]
            if not members:
                continue
            if len(members) == 1:
                assigned.add(seed.poi_id)
                clustered_records.append(seed)
                continue
            cluster_id = f"{city}_{len(clusters) + 1:04d}"
            for member in members:
                assigned.add(member.poi_id)
            center_lat = sum(member.lat for member in members) / len(members)
            center_lng = sum(member.lng for member in members) / len(members)
            score = _cluster_score(members)
            clusters.append(PlaceCluster(cluster_id, city, members, center_lat, center_lng, score))
            for member in members:
                nearby_ids = [other.poi_id for other in members if other.poi_id != member.poi_id][:12]
                clustered_records.append(replace(member, cluster_id=cluster_id, nearby_poi_ids=nearby_ids))
        clustered_records.extend(no_geo)
    return clustered_records, clusters


def _cluster_seed_score(record: PlaceRecord) -> float:
    return record.local_recommend_score + record.popularity + record.rating / 5


def _cluster_score(records: list[PlaceRecord]) -> float:
    if not records:
        return 0.0
    category_bonus = len({record.category for record in records}) / 8
    food_bonus = 0.15 if any(record.category == POICategory.RESTAURANT for record in records) else 0.0
    anchor_quality = sum(record.local_recommend_score for record in records) / len(records)
    density = min(1.0, len(records) / 12)
    return round(anchor_quality * 0.5 + density * 0.35 + category_bonus * 0.15 + food_bonus, 4)
