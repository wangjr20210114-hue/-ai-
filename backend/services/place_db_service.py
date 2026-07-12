"""Place API service — query OSM database with Tencent Maps fallback."""
import asyncpg
from typing import Any

DB_HOST = "94.16.110.28"
DB_PORT = 5433
DB_NAME = "osm"
DB_USER = "postgres"
DB_PASSWORD = "osm123456"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=DB_HOST, port=DB_PORT, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
            min_size=1, max_size=4,
        )
    return _pool


async def search_places(
    query: str,
    *,
    limit: int = 10,
    country: str = "cn",
    min_importance: float = 0.01,
) -> list[dict[str, Any]]:
    """Search places by name (Chinese + English)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name, tags->>'name:zh' AS name_zh,
                   tags->>'name:en' AS name_en,
                   ST_Y(ST_Transform(way, 4326)) AS lat,
                   ST_X(ST_Transform(way, 4326)) AS lng,
                   tags->>'amenity' AS amenity,
                   tags->>'tourism' AS tourism,
                   tags->>'leisure' AS leisure,
                   tags->>'shop' AS shop,
                   tags->>'cuisine' AS cuisine,
                   tags->>'addr:city' AS city,
                   COALESCE(
                       (tags->>'wikipedia')::float,
                       (tags->>'population')::float / 1000000.0,
                       0.01
                   ) AS importance
            FROM planet_osm_point
            WHERE (name ILIKE $1 OR tags->>'name:zh' ILIKE $1 OR tags->>'name:en' ILIKE $1)
              AND (tags->>'amenity' IS NOT NULL OR tags->>'tourism' IS NOT NULL
                   OR tags->>'leisure' IS NOT NULL OR tags->>'historic' IS NOT NULL
                   OR tags->>'shop' IS NOT NULL)
            ORDER BY importance DESC
            LIMIT $2
            """,
            f"%{query}%", limit,
        )
    return [_row_to_dict(r) for r in rows]


async def nearby_places(
    lat: float,
    lng: float,
    *,
    radius_m: int = 3000,
    place_type: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find places near a location, optionally filtered by type."""
    pool = await get_pool()
    type_filter = ""
    params: list[Any] = [lat, lng, radius_m, limit]
    if place_type == "restaurant" or place_type == "food":
        type_filter = "AND (tags->>'amenity' IN ('restaurant','fast_food','cafe','bar','pub','food_court') OR tags->>'cuisine' IS NOT NULL)"
    elif place_type == "tourist" or place_type == "attraction":
        type_filter = "AND (tags->>'tourism' IS NOT NULL OR tags->>'historic' IS NOT NULL OR tags->>'leisure'='park')"
    elif place_type == "hotel":
        type_filter = "AND tags->>'tourism' IN ('hotel','hostel','motel','guest_house')"
    elif place_type == "shop":
        type_filter = "AND tags->>'shop' IS NOT NULL"
    elif place_type:
        type_filter = f"AND (tags->>'amenity' = '{place_type}' OR tags->>'tourism' = '{place_type}' OR tags->>'leisure' = '{place_type}')"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT name, tags->>'name:zh' AS name_zh,
                   tags->>'name:en' AS name_en,
                   ST_Y(ST_Transform(way, 4326)) AS lat,
                   ST_X(ST_Transform(way, 4326)) AS lng,
                   ST_Distance(
                       ST_Transform(way, 3857),
                       ST_Transform(ST_SetSRID(ST_MakePoint($2, $1), 4326), 3857)
                   ) AS distance_m,
                   tags->>'amenity' AS amenity,
                   tags->>'tourism' AS tourism,
                   tags->>'cuisine' AS cuisine,
                   tags->>'addr:city' AS city,
                   tags->>'addr:street' AS street,
                   tags->>'opening_hours' AS opening_hours,
                   tags->>'phone' AS phone
            FROM planet_osm_point
            WHERE ST_DWithin(
                ST_Transform(way, 3857),
                ST_Transform(ST_SetSRID(ST_MakePoint($2, $1), 4326), 3857),
                $3
            )
            {type_filter}
            ORDER BY distance_m
            LIMIT $4
            """,
            *params,
        )
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    d["type"] = d.pop("amenity") or d.pop("tourism") or d.pop("leisure") or "place"
    d["name"] = d.pop("name_zh") or d.pop("name") or d.pop("name_en") or "未知"
    for k in ("name_en", "distance_m", "cuisine", "city", "street", "opening_hours", "phone"):
        v = d.get(k)
        if v is None:
            d[k] = ""
        elif k == "distance_m":
            d[k] = round(float(v), 0)
    return d
