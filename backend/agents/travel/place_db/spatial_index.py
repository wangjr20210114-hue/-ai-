"""Small in-memory spatial index for city-scoped POI lookup."""
from __future__ import annotations

from collections import defaultdict
from math import asin, cos, radians, sin, sqrt

from agents.travel.place_db.schema import PlaceRecord


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0088
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * radius * asin(sqrt(a))


class GridSpatialIndex:
    def __init__(self, cell_size: float = 0.02) -> None:
        self.cell_size = cell_size
        self._grid: dict[tuple[str, int, int], list[PlaceRecord]] = defaultdict(list)

    def build(self, records: list[PlaceRecord]) -> None:
        self._grid.clear()
        for record in records:
            if record.lat and record.lng:
                self._grid[self._cell(record.city, record.lat, record.lng)].append(record)

    def nearby(self, city: str, lat: float, lng: float, radius_km: float = 2.0, limit: int = 20) -> list[tuple[PlaceRecord, float]]:
        if not lat or not lng:
            return []
        center = self._cell(city, lat, lng)
        rings = max(1, int(radius_km / 1.5) + 1)
        candidates: list[tuple[PlaceRecord, float]] = []
        for gx in range(center[1] - rings, center[1] + rings + 1):
            for gy in range(center[2] - rings, center[2] + rings + 1):
                for record in self._grid.get((city, gx, gy), []):
                    dist = haversine_km(lat, lng, record.lat, record.lng)
                    if dist <= radius_km:
                        candidates.append((record, dist))
        candidates.sort(key=lambda item: item[1])
        return candidates[:limit]

    def _cell(self, city: str, lat: float, lng: float) -> tuple[str, int, int]:
        return (city, int(lat / self.cell_size), int(lng / self.cell_size))
