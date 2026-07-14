"""Indexed read-only API for the existing Overture DuckDB."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import duckdb
from fastapi import Depends, FastAPI, Header, HTTPException, Query


DB_PATH = os.getenv("PLACE_DB_PATH", "/data/places-next.duckdb")
API_TOKEN = os.getenv("PLACE_API_TOKEN", "")
app = FastAPI(title="Yuanbao Overture Place Service", version="2.0.0")


def authorize(authorization: str = Header(default="")) -> None:
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid place service token")


@contextmanager
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="place database is missing")
    db = duckdb.connect(DB_PATH, read_only=True)
    try:
        db.execute("SET threads=1")
        db.execute("SET memory_limit='400MB'")
        yield db
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    with connection() as db:
        count = db.execute("SELECT count(*) FROM places").fetchone()[0]
    return {"ok": True, "places": count}


@app.get("/v1/places/search", dependencies=[Depends(authorize)])
def search_places(
    q: str = "", city: str = "", country: str = "", category: str = "",
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    if q.casefold() in {
        "景点", "好玩", "博物馆", "attraction", "scenic", "museum",
        "餐厅", "美食", "吃", "restaurant", "food", "咖啡", "cafe", "coffee",
        "酒店", "住宿", "hotel", "lodging", "购物", "商场", "shopping", "mall",
    }:
        q = ""
    clauses: list[str] = []
    params: list[object] = []
    if country:
        clauses.append("country = ?")
        params.append(country.upper())
    if category:
        clauses.append("category_group = ?")
        params.append(category)

    with connection() as db:
        if q:
            # Domestic names frequently collide across provinces/countries.  Keep
            # the city constraint for China even on indexed name searches.  For
            # overseas destinations we retain country-only matching because the
            # Overture city field is often a borough/ward (for example 台東区).
            if city and country.upper() == "CN":
                clauses.append("(city IN (?, ?) OR region IN (?, ?))")
                params.extend([city, f"{city}市", city, f"{city}市"])
            exact_clauses = [*clauses, "name = ?"]
            exact_params = [*params, q]
            rows = _query(db, exact_clauses, exact_params, limit)
            if len(rows) < limit:
                prefix_clauses = [*clauses, "name LIKE ?"]
                prefix_rows = _query(db, prefix_clauses, [*params, f"{q}%"], limit)
                seen = {row[0] for row in rows}
                rows.extend(row for row in prefix_rows if row[0] not in seen)
        else:
            if city:
                clauses.append("(city IN (?, ?) OR region IN (?, ?))")
                params.extend([city, f"{city}市", city, f"{city}市"])
            rows = _query(db, clauses, params, limit)
        columns = [item[0] for item in db.description]
    places = [dict(zip(columns, row)) for row in rows[:limit]]
    return {"places": places, "count": len(places), "source": "overture"}


def _query(db, clauses: list[str], params: list[object], limit: int) -> list[tuple]:
    where = " AND ".join(clauses) if clauses else "TRUE"
    return db.execute(
        f"""SELECT id, name, aliases, category, category_group, confidence,
                   country, region, city, address, lat, lng, source
            FROM places WHERE {where}
            ORDER BY confidence DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()
