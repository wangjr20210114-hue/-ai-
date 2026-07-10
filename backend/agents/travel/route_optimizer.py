"""Route optimization helpers."""
from __future__ import annotations

import math

from agents.travel.models import POI, ScoredPOI


def haversine_km(a: POI, b: POI) -> float:
    if not a.lat or not a.lng or not b.lat or not b.lng:
        return 8.0
    r = 6371.0
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class RouteOptimizer:
    def order(self, candidates: list[ScoredPOI]) -> list[ScoredPOI]:
        if len(candidates) <= 2:
            return candidates
        remaining = candidates[:]
        current = remaining.pop(0)
        ordered = [current]
        while remaining:
            remaining.sort(key=lambda item: (haversine_km(current.poi, item.poi), -item.score))
            current = remaining.pop(0)
            ordered.append(current)
        return ordered