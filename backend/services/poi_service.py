"""POI 查询服务：按城市+关键词查询 SQLite pois 表。

缓存命中时 0 次 API。
缓存未命中时调 1 次 place_search，结果写入数据库，以后永久不再搜索。
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from database.connection import get_db
from services.geo_cache import get_coords


async def match_poi(city: str, search_query: str) -> dict[str, Any] | None:
    """模糊匹配 POI。返回最佳匹配 + 坐标 + 备选 2-3 个。

    Returns:
        {"name", "address", "lat", "lng", "ticket", "cost_estimate",
         "stay_time", "place_type", "alternatives": [...]} 或 None
    """
    db = await get_db()

    # 1. 精确匹配
    cursor = await db.execute(
        "SELECT * FROM pois WHERE city = ? AND name = ?", (city, search_query)
    )
    row = await cursor.fetchone()
    if row:
        poi = _row_to_dict(row)
        coords = await get_coords(poi["address"])
        poi["lat"] = coords["lat"]
        poi["lng"] = coords["lng"]
        poi["alternatives"] = await _find_alternatives(city, poi)
        return poi

    # 2. 模糊匹配（name LIKE）
    cursor = await db.execute(
        "SELECT * FROM pois WHERE city = ? AND name LIKE ? LIMIT 5",
        (city, f"%{search_query}%"),
    )
    rows = await cursor.fetchall()
    if rows:
        poi = _row_to_dict(rows[0])
        coords = await get_coords(poi["address"])
        poi["lat"] = coords["lat"]
        poi["lng"] = coords["lng"]
        poi["alternatives"] = [
            {"id": _row_to_dict(r)["name"], "title": _row_to_dict(r)["name"],
             "address": _row_to_dict(r)["address"], "lat": 0, "lng": 0}
            for r in rows[1:4]
        ]
        # 获取备选坐标
        for alt in poi["alternatives"]:
            alt_coords = await get_coords(alt["address"])
            alt["lat"] = alt_coords["lat"]
            alt["lng"] = alt_coords["lng"]
        return poi

    # 3. POI 库未命中 → place_search 搜索一次，写入数据库
    from services.map_service import map_service, _CITY_COORDS
    import math

    center = _CITY_COORDS.get(city, {"lat": 0, "lng": 0})
    if not center["lat"]:
        center_coords = await get_coords(city)
        center = center_coords

    results = await map_service.place_search(search_query, city)
    if not results:
        return None

    # 按距市中心排序，取 80km 以内的
    valid = []
    for r in results:
        rloc = r.get("location", {})
        rlat, rlng = rloc.get("lat", 0), rloc.get("lng", 0)
        if not rlat or not center["lat"]:
            continue
        dlat = (rlat - center["lat"]) * 111
        dlng = (rlng - center["lng"]) * 111 * math.cos(math.radians(center["lat"]))
        d = math.sqrt(dlat * dlat + dlng * dlng)
        if d < 80:
            valid.append((d, r))

    if not valid:
        return None

    valid.sort(key=lambda x: x[0])
    top = valid[0][1]
    tloc = top.get("location", {})

    # 写入 pois 表（自动扩充）
    poi_id = f"auto-{uuid.uuid4().hex[:8]}"
    await db.execute(
        """INSERT OR REPLACE INTO pois (id, city, name, address, category, ticket, stay_time, cost_estimate, place_type, lat, lng, created_at)
           VALUES (?, ?, ?, ?, ?, 0, 60, 0, ?, ?, ?, ?)""",
        (poi_id, city, top.get("title", search_query), top.get("address", ""),
         top.get("category", "other"), "other",
         tloc.get("lat", 0), tloc.get("lng", 0), time.time()),
    )
    await db.commit()

    # 写入 geo_cache
    from services.geo_cache import cache_coords
    await cache_coords(top.get("address", search_query), tloc.get("lat", 0), tloc.get("lng", 0))

    alts = []
    for _, r in valid[:3]:
        rloc = r.get("location", {})
        alts.append({
            "id": r.get("id", ""), "title": r.get("title", ""),
            "address": r.get("address", ""), "tel": r.get("tel", ""),
            "lat": rloc.get("lat", 0), "lng": rloc.get("lng", 0),
        })

    return {
        "name": top.get("title", search_query),
        "address": top.get("address", ""),
        "lat": tloc.get("lat", 0),
        "lng": tloc.get("lng", 0),
        "ticket": 0,
        "cost_estimate": 0,
        "stay_time": 60,
        "place_type": "other",
        "alternatives": alts,
    }


async def _find_alternatives(city: str, poi: dict) -> list[dict]:
    """查找同类别备选 POI。"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM pois WHERE city = ? AND category = ? AND name != ? LIMIT 3",
        (city, poi.get("category", "other"), poi["name"]),
    )
    rows = await cursor.fetchall()
    alts = []
    for r in rows:
        d = _row_to_dict(r)
        coords = await get_coords(d["address"])
        alts.append({
            "id": d["name"], "title": d["name"],
            "address": d["address"], "tel": "",
            "lat": coords["lat"], "lng": coords["lng"],
        })
    return alts


def _row_to_dict(row) -> dict:
    """将 sqlite Row 转为 dict。"""
    return {
        "id": row[0],
        "city": row[1],
        "name": row[2],
        "address": row[3],
        "category": row[4],
        "ticket": row[5],
        "stay_time": row[6],
        "cost_estimate": row[7],
        "place_type": row[8],
        "lat": row[9],
        "lng": row[10],
    }
