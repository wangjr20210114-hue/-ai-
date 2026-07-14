from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import asyncpg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.result_rules import rank_and_deduplicate


class PlaceSearchRequest(BaseModel):
    city: str = Field(default="", max_length=120)
    query: str = Field(min_length=1, max_length=160)
    category: Literal["attraction", "restaurant", "hotel", "shopping", "transport", "other"] = "other"
    limit: int = Field(default=10, ge=1, le=20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    app.state.pool = await asyncpg.create_pool(database_url, min_size=1, max_size=12)
    yield
    await app.state.pool.close()


app = FastAPI(title="Yuanbao Place Service", version="1.0.0", lifespan=lifespan)

GENERIC_CATEGORY_QUERIES = {
    "景点", "旅游景点", "好玩", "游玩", "餐厅", "餐馆", "美食", "酒店", "住宿", "购物",
}

OVERTURE_CITY_ALIASES = {
    "东京": "Tokyo", "大阪": "Osaka", "京都": "Kyoto", "首尔": "Seoul",
    "新加坡": "Singapore", "曼谷": "Bangkok", "巴黎": "Paris", "伦敦": "London",
    "罗马": "Rome", "纽约": "New York", "洛杉矶": "Los Angeles",
    "旧金山": "San Francisco", "悉尼": "Sydney", "墨尔本": "Melbourne",
    "迪拜": "Dubai", "伊斯坦布尔": "Istanbul",
}

OVERTURE_CITY_COUNTRIES = {
    "东京": "JP", "大阪": "JP", "京都": "JP", "首尔": "KR", "新加坡": "SG",
    "曼谷": "TH", "巴黎": "FR", "伦敦": "GB", "罗马": "IT", "纽约": "US",
    "洛杉矶": "US", "旧金山": "US", "悉尼": "AU", "墨尔本": "AU",
    "迪拜": "AE", "伊斯坦布尔": "TR",
}


async def search_overture(request: PlaceSearchRequest) -> list[dict]:
    base_url = os.environ.get("OVERTURE_API_BASE_URL", "").rstrip("/")
    token = os.environ.get("PLACE_API_TOKEN", "")
    if not base_url:
        return []
    mapped_city = OVERTURE_CITY_ALIASES.get(request.city, request.city)
    inferred_country = OVERTURE_CITY_COUNTRIES.get(request.city, "")
    if not inferred_country and any("\u4e00" <= char <= "\u9fff" for char in request.city):
        inferred_country = "CN"
    params = {
        "q": request.query,
        "city": mapped_city,
        "country": inferred_country,
        "category": "" if request.category == "other" else request.category,
        "limit": min(request.limit * 3, 50),
    }

    def fetch() -> dict:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        http_request = Request(
            f"{base_url}/v1/places/search?{urlencode(params)}",
            headers=headers,
        )
        with urlopen(http_request, timeout=6) as response:
            return json.load(response)

    try:
        payload = await asyncio.wait_for(asyncio.to_thread(fetch), timeout=7)
    except Exception:
        return []

    places: list[dict] = []
    for item in payload.get("places", []):
        category = item.get("category_group") or "other"
        if category not in {"attraction", "restaurant", "hotel", "shopping", "transport", "other"}:
            category = "other"
        places.append({
            "id": f"overture:{item.get('id', '')}",
            "name": item.get("name") or "",
            "address": item.get("address") or "",
            "category": category,
            "lat": float(item.get("lat") or 0),
            "lng": float(item.get("lng") or 0),
            "tel": "",
            "rating": 0.0,
            "importance": float(item.get("confidence") or 0),
            "source": item.get("source") or "overture_places",
        })
    return places


def authorize(authorization: str | None) -> None:
    expected = os.environ.get("PLACE_API_TOKEN", "")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/healthz")
async def healthz():
    async with app.state.pool.acquire() as connection:
        count = await connection.fetchval("SELECT count(*) FROM places")
    return {"ok": True, "places": count}


@app.post("/v1/places/search")
async def search_places(request: PlaceSearchRequest, authorization: str | None = Header(default=None)):
    authorize(authorization)
    overture_task = asyncio.create_task(search_overture(request))
    category_filter = "" if request.category == "other" else request.category
    search_term = "" if request.query.strip().casefold() in GENERIC_CATEGORY_QUERIES else request.query.strip()
    pattern = f"%{search_term}%"
    async with app.state.pool.acquire() as connection:
        center = None
        if request.city:
            center = await connection.fetchrow(
                """
                SELECT ST_X(geom) AS lng, ST_Y(geom) AS lat
                FROM places
                WHERE category = 'other'
                  AND (name = $1 OR name_zh = $1 OR name_en = $1
                       OR name = $1 || '市' OR name_zh = $1 || '市')
                ORDER BY importance DESC
                LIMIT 1
                """,
                request.city,
            )
        if center:
            location_filter = """
                ST_DWithin(
                    p.geom,
                    ST_SetSRID(ST_MakePoint($6, $7), 4326),
                    0.8
                )
            """
            center_lng, center_lat = float(center["lng"]), float(center["lat"])
        elif request.city:
            location_filter = "(p.city ILIKE '%' || $1 || '%' OR p.address ILIKE '%' || $1 || '%')"
            center_lng, center_lat = 0.0, 0.0
        else:
            location_filter = "TRUE"
            center_lng, center_lat = 0.0, 0.0
        rows = await connection.fetch(
            f"""
            SELECT p.id, COALESCE(NULLIF(p.name_zh, ''), p.name, NULLIF(p.name_en, '')) AS name,
                   p.address, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng,
                   p.phone AS tel, p.rating, p.importance, p.source
            FROM places p
            WHERE {location_filter}
              AND $1::text IS NOT NULL
              AND $6::double precision IS NOT NULL AND $7::double precision IS NOT NULL
              AND ($2 = '' OR p.category = $2)
              AND ($4 = '' OR p.name ILIKE $3 OR p.name_zh ILIKE $3 OR p.name_en ILIKE $3
                   OR p.aliases ILIKE $3)
            ORDER BY
              CASE WHEN p.name = $4 OR p.name_zh = $4 OR p.name_en = $4 THEN 0 ELSE 1 END,
              similarity(COALESCE(NULLIF(p.name_zh, ''), p.name), $4) DESC,
              p.importance DESC,
              p.rating DESC
            LIMIT $5
            """,
            request.city,
            category_filter,
            pattern,
            search_term,
            min(request.limit * 3, 60),
            center_lng,
            center_lat,
        )
    overture_places = await overture_task
    return {
        "places": rank_and_deduplicate(
            [*[dict(row) for row in rows], *overture_places],
            search_term,
            request.limit,
        )
    }
