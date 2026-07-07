"""坐标缓存服务：地址→坐标永久缓存到 SQLite。

首次 geocode 后永久缓存，后续查询 0 次 API。
内存级 dict 缓存 + SQLite 持久化双保险。
"""
from __future__ import annotations

import time
from typing import Any

from database.connection import get_db

# 内存缓存（进程级）
_mem_cache: dict[str, dict[str, float | str]] = {}


async def get_coords(address: str) -> dict[str, float]:
    """获取地址坐标。优先内存→SQLite缓存，未命中调 geocode API。"""
    # 1. 内存缓存
    if address in _mem_cache:
        c = _mem_cache[address]
        return {"lat": c["lat"], "lng": c["lng"]}

    # 2. SQLite 缓存
    db = await get_db()
    cursor = await db.execute(
        "SELECT lat, lng FROM geo_cache WHERE address = ?", (address,)
    )
    row = await cursor.fetchone()
    if row:
        result = {"lat": row[0], "lng": row[1]}
        _mem_cache[address] = result
        return result

    # 3. 缓存未命中 → 调 geocode API
    from services.map_service import map_service
    coords = await map_service.geocode(address)
    if coords["lat"] and coords["lng"]:
        await cache_coords(address, coords["lat"], coords["lng"])
        _mem_cache[address] = coords
    return coords


async def cache_coords(address: str, lat: float, lng: float, adcode: str = "") -> None:
    """写入坐标缓存。"""
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO geo_cache (address, lat, lng, adcode, created_at) VALUES (?, ?, ?, ?, ?)",
        (address, lat, lng, adcode, time.time()),
    )
    await db.commit()
    _mem_cache[address] = {"lat": lat, "lng": lng}


async def get_adcode(city: str) -> str:
    """获取城市的 adcode（用于天气查询）。优先缓存。"""
    # 1. 内存缓存
    if f"adcode:{city}" in _mem_cache:
        return str(_mem_cache[f"adcode:{city}"].get("adcode", ""))

    # 2. SQLite 缓存
    db = await get_db()
    cursor = await db.execute(
        "SELECT adcode FROM geo_cache WHERE address = ?", (city,)
    )
    row = await cursor.fetchone()
    if row and row[0]:
        _mem_cache[f"adcode:{city}"] = {"adcode": row[0]}
        return row[0]

    # 3. 缓存未命中 → geocode 获取坐标 + 逆 geocode 获取 adcode
    from services.map_service import map_service, _CITY_COORDS
    loc = _CITY_COORDS.get(city, {"lat": 0, "lng": 0})
    if not loc["lat"]:
        loc = await map_service.geocode(city)

    if not loc["lat"]:
        return ""

    # 逆 geocode 获取 adcode
    adcode = await map_service.get_adcode(loc["lat"], loc["lng"])
    if adcode:
        await cache_coords(city, loc["lat"], loc["lng"], adcode)
        _mem_cache[f"adcode:{city}"] = {"adcode": adcode}
    return adcode


def clear_mem_cache() -> None:
    """清空内存缓存（测试用）。"""
    _mem_cache.clear()
