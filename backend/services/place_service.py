"""Unified place service: local OSM DB primary, Tencent Maps fallback."""
from __future__ import annotations

from typing import Any


async def search_places(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Search places by name. Tries local DB first, falls back to Tencent Maps."""
    # Try local OSM DB
    try:
        from services.place_db_service import search_places as db_search
        results = await db_search(query, limit=limit)
        if results:
            return results
    except Exception:
        pass

    # Fallback to Tencent Maps
    try:
        from services.map_service import search_places as tmap_search
        results = await tmap_search(query, limit=limit)
        if results:
            return _normalize_tmap(results)
    except Exception:
        pass

    return []


async def nearby_places(
    lat: float, lng: float,
    *, radius_m: int = 3000, place_type: str = "", limit: int = 20,
) -> list[dict[str, Any]]:
    """Search nearby places by coordinates."""
    try:
        from services.place_db_service import nearby_places as db_nearby
        results = await db_nearby(lat, lng, radius_m=radius_m, place_type=place_type, limit=limit)
        if results:
            return results
    except Exception:
        pass

    try:
        from services.map_service import search_nearby as tmap_nearby
        results = await tmap_nearby(lat, lng, radius_m=radius_m, category=place_type, limit=limit)
        if results:
            return _normalize_tmap(results)
    except Exception:
        pass

    return []


def _normalize_tmap(results: list[dict]) -> list[dict]:
    """Normalize Tencent Map results to standard format."""
    out = []
    for r in results:
        out.append({
            "name": r.get("title") or r.get("name", ""),
            "lat": r.get("location", {}).get("lat", 0),
            "lng": r.get("location", {}).get("lng", 0),
            "type": r.get("category", "place"),
            "address": r.get("address", ""),
            "phone": r.get("tel", ""),
            "distance_m": r.get("_distance", 0),
        })
    return out
