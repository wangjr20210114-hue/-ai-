"""Tencent Location Service adapters; not an Agent route."""

from __future__ import annotations

import asyncio
import json
import math
import re
import urllib.parse
import urllib.request
from typing import Any


API_ROOT = "https://apis.map.qq.com/ws"


def _fetch_json(url: str, params: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    query = urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"Accept": "application/json", "User-Agent": "yuanbao-edgeone/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(3 * 1024 * 1024)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("位置服务返回格式无效")
    if int(data.get("status") or 0) != 0:
        raise RuntimeError(str(data.get("message") or "位置服务请求失败"))
    return data


def _fetch_public_json(url: str, params: dict[str, Any], timeout: int = 20) -> Any:
    query = urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        f"{url}?{query}" if query else url,
        headers={"Accept": "application/json", "User-Agent": "yuanbao-edgeone/1.0 (travel assistant)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(5 * 1024 * 1024).decode("utf-8"))


async def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_json, url, params)


async def _get_public(url: str, params: dict[str, Any]) -> Any:
    return await asyncio.to_thread(_fetch_public_json, url, params)


def _place(item: dict[str, Any]) -> dict[str, Any] | None:
    location = item.get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    place_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    if not place_id or not title:
        return None
    ad_info = item.get("ad_info") or {}
    return {
        "schema_version": 1,
        "place_id": place_id,
        "provider": "tencent",
        "name": title[:120],
        "address": str(item.get("address") or "").strip()[:240],
        "latitude": float(lat),
        "longitude": float(lng),
        "city": str(ad_info.get("city") or "")[:80],
        "category": str(item.get("category") or "")[:120],
    }


async def search_places(key: str, query: str, *, city: str = "全国", limit: int = 10) -> list[dict[str, Any]]:
    if not key:
        raise RuntimeError("未配置 TENCENT_MAP_KEY")
    query = str(query or "").strip()
    if not query:
        raise ValueError("地点搜索词不能为空")
    boundary = f"region({str(city or '全国').strip()},0)"
    data = await _get(
        f"{API_ROOT}/place/v1/search",
        {"key": key, "keyword": query[:120], "boundary": boundary, "page_size": max(1, min(20, int(limit))), "page_index": 1},
    )
    places = [_place(item) for item in data.get("data", []) if isinstance(item, dict)]
    return [item for item in places if item is not None]


async def search_osm_places(query: str, *, city: str = "", limit: int = 10) -> list[dict[str, Any]]:
    terms = " ".join(part for part in (str(query or "").strip(), str(city or "").strip()) if part and part != "全国")
    data = await _get_public(
        "https://nominatim.openstreetmap.org/search",
        {"q": terms or query, "format": "jsonv2", "addressdetails": 1, "limit": max(1, min(20, int(limit))), "accept-language": "zh-CN,zh,en"},
    )
    places = []
    for item in data if isinstance(data, list) else []:
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        address = item.get("address") or {}
        name = str(item.get("name") or str(item.get("display_name") or "").split(",")[0]).strip()
        osm_type = str(item.get("osm_type") or "place")
        osm_id = str(item.get("osm_id") or item.get("place_id") or "")
        if not name or not osm_id:
            continue
        places.append({
            "schema_version": 1,
            "place_id": f"osm:{osm_type}:{osm_id}",
            "provider": "openstreetmap",
            "name": name[:120],
            "address": str(item.get("display_name") or "")[:240],
            "latitude": lat,
            "longitude": lng,
            "city": str(address.get("city") or address.get("town") or address.get("county") or "")[:80],
            "category": str(item.get("type") or item.get("category") or "")[:120],
        })
    return places


def _normalized_lookup_text(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _primary_place_match_score(item: dict[str, Any], normalized_query: str) -> float:
    normalized_name = _normalized_lookup_text(item.get("name"))
    normalized_record = _normalized_lookup_text(f"{item.get('name', '')}{item.get('address', '')}")
    if not normalized_query or not normalized_name:
        return 0.0
    if normalized_query in normalized_record:
        return 3.0 + min(1.0, len(normalized_query) / max(1, len(normalized_record)))
    if len(normalized_name) >= 3 and normalized_name in normalized_query:
        coverage = len(normalized_name) / max(1, len(normalized_query))
        if coverage > 0.25:
            return 2.0 + coverage
    return 0.0


async def search_verified_places(key: str, query: str, *, city: str = "全国", limit: int = 10) -> list[dict[str, Any]]:
    normalized_query = _normalized_lookup_text(query)
    primary: list[dict[str, Any]] = []
    if key:
        try:
            primary = await search_places(key, query, city=city, limit=limit)
            ranked_primary = sorted(
                (
                    (_primary_place_match_score(item, normalized_query), index, item)
                    for index, item in enumerate(primary)
                ),
                key=lambda candidate: (-candidate[0], candidate[1]),
            )
            matched_primary = [item for score, _index, item in ranked_primary if score > 0]
            if matched_primary:
                return matched_primary
        except Exception:
            pass
    fallback = await search_osm_places(query, city=city, limit=limit)
    if not fallback and str(city or "全国").strip() == "全国":
        fallback = await search_osm_places(f"{query} 中国", limit=limit)
    output, seen = [], set()
    # Unmatched Tencent candidates are real POIs but not verified answers to
    # this query (for example, the generic "三里屯" area returned for a missing
    # restaurant brand). Never reintroduce them merely because the public
    # fallback is empty.
    for item in fallback:
        place_id = str(item.get("place_id") or "")
        if place_id and place_id not in seen:
            seen.add(place_id)
            output.append(item)
        if len(output) >= max(1, min(20, int(limit))):
            break
    return output


async def optimize_place_order(key: str, places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find the shortest open path using Tencent driving matrix distances."""
    if len(places) < 3:
        return places
    if len(places) > 10:
        # Keep provider calls and DP bounded; deterministic nearest-neighbour is
        # used only for unusually large recommendation sets.
        remaining = list(range(1, len(places)))
        order = [0]
        while remaining:
            current = places[order[-1]]
            next_index = min(
                remaining,
                key=lambda index: (current["latitude"] - places[index]["latitude"]) ** 2
                + (current["longitude"] - places[index]["longitude"]) ** 2,
            )
            order.append(next_index)
            remaining.remove(next_index)
        return [places[index] for index in order]
    coords = ";".join(f"{float(place['latitude'])},{float(place['longitude'])}" for place in places)
    data = await _get(
        f"{API_ROOT}/distance/v1/matrix",
        {"key": key, "mode": "driving", "from": coords, "to": coords},
    )
    rows = (data.get("result") or {}).get("rows") or []
    matrix: list[list[float]] = []
    for row in rows:
        elements = row.get("elements") or [] if isinstance(row, dict) else []
        matrix.append([float(item.get("distance") or math.inf) for item in elements if isinstance(item, dict)])
    count = len(places)
    if len(matrix) != count or any(len(row) != count for row in matrix):
        return places
    # Held-Karp for an open Hamiltonian path. Every point may be the start/end.
    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {
        (1 << index, index): (0.0, (index,)) for index in range(count)
    }
    for mask in range(1, 1 << count):
        for last in range(count):
            current = dp.get((mask, last))
            if current is None:
                continue
            distance, path = current
            for nxt in range(count):
                if mask & (1 << nxt):
                    continue
                candidate = (distance + matrix[last][nxt], path + (nxt,))
                key_state = (mask | (1 << nxt), nxt)
                previous = dp.get(key_state)
                if previous is None or candidate < previous:
                    dp[key_state] = candidate
    full = (1 << count) - 1
    best = min(dp[(full, last)] for last in range(count) if (full, last) in dp)
    return [places[index] for index in best[1]]


def decode_polyline(values: list[Any]) -> list[dict[str, float]]:
    numbers = [float(value) for value in values]
    for index in range(2, len(numbers)):
        numbers[index] = numbers[index - 2] + numbers[index] / 1_000_000
    return [
        {"latitude": numbers[index], "longitude": numbers[index + 1]}
        for index in range(0, len(numbers) - 1, 2)
    ]


def _fare(distance_m: float, duration_s: float, toll_yuan: float) -> dict[str, Any]:
    km = max(0.0, distance_m / 1000)
    hours = max(0.0, duration_s / 3600)
    fuel = round(km * 0.075 * 8.0 + max(0.0, toll_yuan), 2)
    taxi_low = 14.0 + max(0.0, km - 3.0) * 2.3 + max(0.0, hours - 0.15) * 18.0
    taxi_high = taxi_low * 1.25
    return {
        "currency": "CNY",
        "basis": "腾讯真实道路距离；出租车为通用城市参数区间，未包含动态加价和停车费",
        "self_driving": {"estimate": fuel, "toll": round(max(0.0, toll_yuan), 2)},
        "taxi": {"low": round(taxi_low, 2), "high": round(taxi_high, 2)},
    }


async def plan_driving_route(key: str, places: list[dict[str, Any]], *, optimize: bool = False) -> dict[str, Any]:
    if not key:
        raise RuntimeError("未配置 TENCENT_MAP_KEY")
    if len(places) < 2:
        raise ValueError("至少需要两个有效地点才能规划路线")
    if len(places) > 12:
        raise ValueError("单条路线最多支持 12 个地点")
    if optimize:
        places = await optimize_place_order(key, places)
    coords = [
        (float(place["latitude"]), float(place["longitude"]))
        for place in places
    ]
    params: dict[str, Any] = {
        "key": key,
        "from": f"{coords[0][0]},{coords[0][1]}",
        "to": f"{coords[-1][0]},{coords[-1][1]}",
        "policy": "LEAST_DISTANCE",
        "get_mp": 1,
    }
    if len(coords) > 2:
        params["waypoints"] = ";".join(f"{lat},{lng}" for lat, lng in coords[1:-1])
    data = await _get(f"{API_ROOT}/direction/v1/driving/", params)
    routes = (data.get("result") or {}).get("routes") or []
    if not routes:
        raise RuntimeError("位置服务没有返回可用道路路线")
    route = min(
        (item for item in routes if isinstance(item, dict)),
        key=lambda item: (float(item.get("distance") or math.inf), float(item.get("duration") or math.inf)),
    )
    distance = float(route.get("distance") or 0)
    # Tencent Direction WebService reports route duration in minutes.  The
    # public Yuanbao contract and the OSRM fallback both use seconds.
    duration = float(route.get("duration") or 0) * 60
    toll = float(route.get("taxi_fare", {}).get("fare") or route.get("toll") or 0) if isinstance(route.get("taxi_fare"), dict) else float(route.get("toll") or 0)
    return {
        "schema_version": 2,
        "provider": "tencent",
        "mode": "driving",
        "places": places,
        "path": decode_polyline(route.get("polyline") or []),
        "distance_meters": distance,
        "duration_seconds": duration,
        "fare": _fare(distance, duration, toll),
    }


def _best_open_path(matrix: list[list[float]]) -> tuple[int, ...]:
    count = len(matrix)
    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {
        (1 << index, index): (0.0, (index,)) for index in range(count)
    }
    for mask in range(1, 1 << count):
        for last in range(count):
            current = dp.get((mask, last))
            if current is None:
                continue
            distance, path = current
            for nxt in range(count):
                if mask & (1 << nxt):
                    continue
                candidate = (distance + matrix[last][nxt], path + (nxt,))
                state_key = (mask | (1 << nxt), nxt)
                if state_key not in dp or candidate < dp[state_key]:
                    dp[state_key] = candidate
    full = (1 << count) - 1
    return min(dp[(full, last)] for last in range(count))[1]


async def plan_osrm_route(places: list[dict[str, Any]], *, optimize: bool = False) -> dict[str, Any]:
    if not 2 <= len(places) <= 12:
        raise ValueError("道路路线地点数量必须在 2 到 12 个之间")
    ordered = list(places)
    if optimize and len(places) <= 10:
        coordinates = ";".join(f"{float(place['longitude'])},{float(place['latitude'])}" for place in places)
        table = await _get_public(
            f"https://router.project-osrm.org/table/v1/driving/{coordinates}",
            {"annotations": "distance"},
        )
        matrix = table.get("distances") if isinstance(table, dict) else None
        if isinstance(matrix, list) and len(matrix) == len(places) and all(isinstance(row, list) and len(row) == len(places) for row in matrix):
            numeric = [[float(value) if value is not None else math.inf for value in row] for row in matrix]
            ordered = [places[index] for index in _best_open_path(numeric)]
    coordinates = ";".join(f"{float(place['longitude'])},{float(place['latitude'])}" for place in ordered)
    data = await _get_public(
        f"https://router.project-osrm.org/route/v1/driving/{coordinates}",
        {"overview": "full", "geometries": "geojson", "steps": "false"},
    )
    routes = data.get("routes") if isinstance(data, dict) else None
    if not routes:
        raise RuntimeError("备用道路服务没有返回可用路线")
    route = routes[0]
    coordinates_out = ((route.get("geometry") or {}).get("coordinates") or [])
    path = [{"latitude": float(item[1]), "longitude": float(item[0])} for item in coordinates_out if isinstance(item, list) and len(item) >= 2]
    distance = float(route.get("distance") or 0)
    duration = float(route.get("duration") or 0)
    return {
        "schema_version": 1,
        "provider": "openstreetmap-osrm",
        "mode": "driving",
        "places": ordered,
        "path": path,
        "distance_meters": distance,
        "duration_seconds": duration,
        "fare": _fare(distance, duration, 0),
    }


async def plan_verified_route(key: str, places: list[dict[str, Any]], *, optimize: bool = False) -> dict[str, Any]:
    if key:
        try:
            return await plan_driving_route(key, places, optimize=optimize)
        except Exception:
            pass
    return await plan_osrm_route(places, optimize=optimize)


async def get_current_weather(key: str, place: dict[str, Any]) -> dict[str, Any]:
    """Resolve a verified place to an adcode and return Tencent realtime weather."""
    if not key:
        raise RuntimeError("未配置 TENCENT_MAP_KEY，跳过天气 Collector")
    lat = place.get("latitude")
    lng = place.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        raise ValueError("天气地点缺少已验证坐标")
    geocode = await _get(
        f"{API_ROOT}/geocoder/v1/",
        {"key": key, "location": f"{float(lat)},{float(lng)}", "get_poi": 0},
    )
    ad_info = (geocode.get("result") or {}).get("ad_info") or {}
    adcode = str(ad_info.get("adcode") or "")
    if not adcode:
        raise RuntimeError("位置服务没有返回天气行政区划")
    weather = await _get(f"{API_ROOT}/weather/v1/", {"key": key, "adcode": adcode})
    realtime = (weather.get("result") or {}).get("realtime") or []
    if not realtime:
        raise RuntimeError("位置服务没有返回实时天气")
    infos = (realtime[0] or {}).get("infos") or {}
    return {
        "provider": "tencent",
        "adcode": adcode,
        "city": str(ad_info.get("city") or place.get("city") or ""),
        "district": str(ad_info.get("district") or ""),
        "weather": str(infos.get("weather") or ""),
        "temperature": infos.get("temperature"),
        "wind_direction": str(infos.get("wind_direction") or ""),
        "wind_power": str(infos.get("wind_power") or ""),
        "humidity": infos.get("humidity"),
        "precipitation": infos.get("precipitation"),
        "observed_at": infos.get("update_time") or infos.get("time") or "",
    }
