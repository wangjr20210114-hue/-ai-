"""Tencent Location Service provider adapter; not an Agent route."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API_ROOT = "https://apis.map.qq.com/ws"
_OSM_SEARCH_SEMAPHORE = asyncio.Semaphore(1)
_osm_last_request_at = 0.0


def _fetch_json(url: str, params: dict[str, Any], timeout: int = 8) -> dict[str, Any]:
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


def _fetch_public_json(url: str, params: dict[str, Any], timeout: int = 8) -> Any:
    query = urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        f"{url}?{query}" if query else url,
        headers={"Accept": "application/json", "User-Agent": "yuanbao-edgeone/1.0 (travel assistant)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(5 * 1024 * 1024).decode("utf-8"))


async def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(2):
        try:
            return await asyncio.to_thread(_fetch_json, url, params)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt:
                raise
            await asyncio.sleep(0.2)
    raise RuntimeError("腾讯位置服务请求失败")


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


async def search_place_suggestions(
    key: str, query: str, *, city: str = "全国", limit: int = 10,
) -> list[dict[str, Any]]:
    """Use Tencent's keyword-suggestion service as evidence for typo recovery."""
    if not key:
        return []
    query = str(query or "").strip()
    if not query:
        return []
    data = await _get(
        f"{API_ROOT}/place/v1/suggestion",
        {
            "key": key,
            "keyword": query[:120],
            "region": str(city or "全国").strip(),
            "region_fix": 0,
            "page_size": max(1, min(20, int(limit))),
        },
    )
    places = [_place(item) for item in data.get("data", []) if isinstance(item, dict)]
    return [item for item in places if item is not None]


async def reverse_geocode(key: str, location: dict[str, Any]) -> dict[str, Any]:
    """Resolve a request-scoped browser fix into user-readable Tencent address data."""
    if not key:
        raise RuntimeError("未配置 TENCENT_MAP_KEY")
    try:
        latitude = float(location.get("latitude"))
        longitude = float(location.get("longitude"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("当前位置坐标无效") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("当前位置坐标超出有效范围")
    coordinate_type = str(location.get("coordinate_type") or "").lower()
    data = await _get(
        f"{API_ROOT}/geocoder/v1",
        {
            "key": key,
            "location": f"{latitude:.7f},{longitude:.7f}",
            "coord_type": 1 if coordinate_type == "wgs84" else 5,
            "get_poi": 1,
        },
    )
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    components = (
        result.get("address_component")
        if isinstance(result.get("address_component"), dict)
        else {}
    )
    formatted = (
        result.get("formatted_addresses")
        if isinstance(result.get("formatted_addresses"), dict)
        else {}
    )
    address = str(
        formatted.get("recommend")
        or result.get("address")
        or formatted.get("rough")
        or ""
    ).strip()[:240]
    nearby_landmark = ""
    for raw_poi in result.get("pois") or []:
        if not isinstance(raw_poi, dict):
            continue
        title = str(raw_poi.get("title") or "").strip()
        poi_address = str(raw_poi.get("address") or "").strip()
        if title:
            nearby_landmark = (
                f"{title}（{poi_address}）" if poi_address else title
            )[:240]
            break
    if not address and not any(str(value or "").strip() for value in components.values()):
        raise RuntimeError("腾讯位置服务未返回可读地址")
    return {
        "provider": "tencent",
        "address": address,
        "province": str(components.get("province") or "").strip()[:80],
        "city": str(components.get("city") or "").strip()[:80],
        "district": str(components.get("district") or "").strip()[:80],
        "street": str(components.get("street") or "").strip()[:120],
        "street_number": str(components.get("street_number") or "").strip()[:80],
        "nearby_landmark": nearby_landmark,
    }


async def search_osm_places(query: str, *, city: str = "", limit: int = 10) -> list[dict[str, Any]]:
    global _osm_last_request_at
    terms = " ".join(part for part in (str(query or "").strip(), str(city or "").strip()) if part and part != "全国")
    async with _OSM_SEARCH_SEMAPHORE:
        loop = asyncio.get_running_loop()
        delay = 1.0 - (loop.time() - _osm_last_request_at)
        if delay > 0:
            await asyncio.sleep(delay)
        _osm_last_request_at = loop.time()
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
            "coordinate_type": "wgs84",
            "city": str(address.get("city") or address.get("town") or address.get("county") or "")[:80],
            "category": str(item.get("type") or item.get("category") or "")[:120],
        })
    return places


def _normalized_lookup_text(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _provider_place_candidates(
    candidates: list[dict[str, Any]],
    query: str,
    *,
    limit: int,
    evidence: str,
    annotate_corrections: bool = False,
) -> list[dict[str, Any]]:
    """Preserve provider ranking and provider-native correction evidence.

    The adapter deliberately does not infer typo similarity, strip category
    suffixes, or collapse aliases. A normal Tencent place-search result with a
    different name may simply be another branch, so only Tencent's suggestion
    endpoint is allowed to annotate it as a correction. Downstream semantic
    adjudication sees the complete ordered candidate set.
    """
    normalized_query = _normalized_lookup_text(query)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        place_id = str(item.get("place_id") or "")
        if not place_id or place_id in seen:
            continue
        seen.add(place_id)
        current = dict(item)
        if (
            annotate_corrections
            and _normalized_lookup_text(item.get("name")) != normalized_query
        ):
            current["query_correction"] = {
                "original_query": str(query or "").strip()[:120],
                "corrected_name": str(item.get("name") or "")[:120],
                "evidence": evidence,
            }
        output.append(current)
        if len(output) >= max(1, min(20, int(limit))):
            break
    return output


def _merge_place_candidates(
    *candidate_groups: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Merge provider-ranked groups without changing order or inferring aliases."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    bounded_limit = max(1, min(20, int(limit)))
    for group in candidate_groups:
        for item in group:
            place_id = str(item.get("place_id") or "")
            if not place_id or place_id in seen:
                continue
            seen.add(place_id)
            merged.append(item)
            if len(merged) >= bounded_limit:
                return merged
    return merged


def place_distance_meters(origin: dict[str, Any], destination: dict[str, Any]) -> float:
    """Return a bounded straight-line distance for nearby-result validation."""
    lat1 = math.radians(float(origin["latitude"]))
    lat2 = math.radians(float(destination["latitude"]))
    delta_lat = lat2 - lat1
    delta_lng = math.radians(float(destination["longitude"]) - float(origin["longitude"]))
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


async def search_verified_places(key: str, query: str, *, city: str = "全国", limit: int = 10) -> list[dict[str, Any]]:
    return await search_verified_places_bounded(
        key, query, city=city, limit=limit, timeout_seconds=20,
    )


async def search_verified_places_bounded(
    key: str,
    query: str,
    *,
    city: str = "全国",
    limit: int = 10,
    timeout_seconds: float = 20,
) -> list[dict[str, Any]]:
    """Search Tencent first and use OSM only as a bounded POI-search fallback.

    OSM coordinates may be passed to Tencent Directions later, but OSM is
    never used for road matching or route calculation.
    """
    timeout = max(3.0, min(55.0, float(timeout_seconds)))
    deadline = asyncio.get_running_loop().time() + timeout
    normalized_query = _normalized_lookup_text(query)
    unresolved_primary: list[dict[str, Any]] = []
    exact_primary: list[dict[str, Any]] = []
    if key:
        try:
            primary = await asyncio.wait_for(
                search_places(key, query, city=city, limit=limit),
                # search_places owns one bounded retry after a transient
                # network failure. Its two 8 s attempts can legitimately
                # take a little over 16 s, so an 8 s outer timeout cancelled
                # the retry before it could ever succeed.
                timeout=min(17.0, timeout),
            )
            exact_primary = [
                item for item in primary
                if _normalized_lookup_text(item.get("name")) == normalized_query
            ]
            if exact_primary and len(primary) > 1:
                # Do not discard alternate Tencent records merely because one
                # item has the exact bare name. That shortcut silently selected
                # one branch for queries such as a chain mall or hotel. The
                # route layer now receives the complete provider-ranked set and
                # asks only when semantic intent is not near-certain.
                return _provider_place_candidates(
                    primary, query, limit=limit,
                    evidence="tencent_place_search",
                )
            unresolved_primary = primary
        except Exception:
            pass
    remaining = deadline - asyncio.get_running_loop().time()
    if key and remaining > 0.5:
        try:
            suggestions = await asyncio.wait_for(
                search_place_suggestions(
                    key, query, city=city, limit=max(limit, 6),
                ),
                # Keep this stage inside the shared deadline while allowing
                # the adapter's bounded retry when enough budget remains.
                timeout=min(17.0, remaining),
            )
            if suggestions:
                suggestion_candidates = _provider_place_candidates(
                    suggestions, query, limit=limit,
                    evidence="tencent_place_suggestion",
                    # When the main Tencent endpoint already supplied an exact
                    # record, other suggestions are alternative POIs, not typo
                    # corrections. Without an exact main result, the suggestion
                    # endpoint is Tencent-native correction evidence.
                    annotate_corrections=not bool(exact_primary),
                )
                if exact_primary:
                    primary_candidates = _provider_place_candidates(
                        unresolved_primary,
                        query,
                        limit=limit,
                        evidence="tencent_place_search",
                    )
                    return _merge_place_candidates(
                        primary_candidates,
                        suggestion_candidates,
                        limit=limit,
                    )
                return suggestion_candidates
        except Exception:
            pass
    if exact_primary:
        return _provider_place_candidates(
            unresolved_primary,
            query,
            limit=limit,
            evidence="tencent_place_search",
        )
    if len(unresolved_primary) > 1:
        return _provider_place_candidates(
            unresolved_primary,
            query,
            limit=limit,
            evidence="tencent_place_search",
        )
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError(f"地点搜索超过 {round(timeout)} 秒，请减少候选数量或使用快速档")
    try:
        fallback = await asyncio.wait_for(
            search_osm_places(query, city=city, limit=limit),
            timeout=max(0.1, remaining),
        )
        remaining = deadline - asyncio.get_running_loop().time()
        if (
            not fallback
            and str(city or "全国").strip() == "全国"
            and remaining > 0.5
        ):
            fallback = await asyncio.wait_for(
                search_osm_places(f"{query} 中国", limit=limit),
                timeout=max(0.1, remaining),
            )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"地点搜索超过 {round(timeout)} 秒，请减少候选数量或使用快速档"
        ) from exc
    requested_city = _normalized_lookup_text(city)
    if requested_city and requested_city != _normalized_lookup_text("全国"):
        fallback = [
            item for item in fallback
            if requested_city in _normalized_lookup_text(
                f"{item.get('city', '')}{item.get('address', '')}"
            )
        ]
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


async def search_verified_places_nearby(
    key: str,
    query: str,
    anchor: dict[str, Any],
    *,
    radius_meters: int = 5_000,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Resolve POIs only when they are physically near a verified anchor.

    Tencent's nearby boundary and ordered results are the evidence source.
    The adapter does not infer categories or aliases from local word lists.
    """
    query = str(query or "").strip()
    if not query:
        raise ValueError("周边地点搜索词不能为空")
    try:
        latitude = float(anchor["latitude"])
        longitude = float(anchor["longitude"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("周边搜索锚点缺少已验证坐标") from None
    radius = max(200, min(50_000, int(radius_meters or 5_000)))
    bounded_limit = max(1, min(20, int(limit)))
    search_keyword = query
    if key:
        try:
            data = await _get(
                f"{API_ROOT}/place/v1/search",
                {
                    "key": key,
                    "keyword": search_keyword[:120],
                    "boundary": f"nearby({latitude},{longitude},{radius},1)",
                    "orderby": "_distance",
                    "page_size": bounded_limit,
                    "page_index": 1,
                },
            )
            candidates = [
                place for place in (_place(item) for item in data.get("data", []) if isinstance(item, dict))
                if place is not None
            ]
            provider_candidates = _provider_place_candidates(
                candidates,
                query,
                limit=bounded_limit,
                evidence="tencent_nearby_search",
            )
            ranked = sorted(
                (
                    (place_distance_meters(anchor, item), index, item)
                    for index, item in enumerate(provider_candidates)
                ),
                key=lambda candidate: (candidate[0], candidate[1]),
            )
            nearby = [
                {**item, "distance_to_anchor_meters": round(distance, 1)}
                for distance, _index, item in ranked
                if distance <= radius
            ]
            if nearby:
                return nearby[:bounded_limit]
        except Exception:
            pass

    fallback = await search_osm_places(
        search_keyword,
        city=str(anchor.get("city") or ""),
        limit=max(bounded_limit, 10),
    )
    nearby = []
    for item in fallback:
        distance = place_distance_meters(anchor, item)
        if distance <= radius:
            nearby.append({**item, "distance_to_anchor_meters": round(distance, 1)})
    return sorted(nearby, key=lambda item: float(item["distance_to_anchor_meters"]))[:bounded_limit]


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


def _fare(
    distance_m: float,
    duration_s: float,
    toll_yuan: float,
    taxi_estimate_yuan: float = 0,
) -> dict[str, Any]:
    km = max(0.0, distance_m / 1000)
    hours = max(0.0, duration_s / 3600)
    fuel = round(km * 0.075 * 8.0 + max(0.0, toll_yuan), 2)
    if taxi_estimate_yuan > 0:
        taxi_low = taxi_estimate_yuan * 0.9
        taxi_high = taxi_estimate_yuan * 1.15
        basis = "腾讯真实道路距离与出租车费用估算；区间用于覆盖动态加价和等候差异，不包含停车费"
    else:
        taxi_low = 14.0 + max(0.0, km - 3.0) * 2.3 + max(0.0, hours - 0.15) * 18.0
        taxi_high = taxi_low * 1.25
        basis = "真实道路距离；出租车为通用城市参数区间，未包含动态加价和停车费"
    return {
        "currency": "CNY",
        "basis": basis,
        "self_driving": {"estimate": fuel, "toll": round(max(0.0, toll_yuan), 2)},
        "taxi": {
            "low": round(taxi_low, 2),
            "high": round(taxi_high, 2),
            **({"provider_estimate": round(taxi_estimate_yuan, 2)} if taxi_estimate_yuan > 0 else {}),
        },
    }


def _decoded_route_path(route: dict[str, Any]) -> list[dict[str, float]]:
    direct = route.get("polyline")
    if isinstance(direct, list) and direct:
        try:
            return decode_polyline(direct)
        except (TypeError, ValueError):
            pass
    path: list[dict[str, float]] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "polyline" and isinstance(child, list) and child:
                    try:
                        segment = decode_polyline(child)
                    except (TypeError, ValueError):
                        continue
                    if path and segment and path[-1] == segment[0]:
                        segment = segment[1:]
                    path.extend(segment)
                elif key in {"steps", "lines", "walking", "segments"}:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(route.get("steps") or [])
    return path


def _decoded_polyline(value: Any) -> list[dict[str, float]]:
    """Decode one Tencent geometry without walking unrelated sibling nodes."""
    if not isinstance(value, dict):
        return []
    polyline = value.get("polyline")
    if not isinstance(polyline, list) or not polyline:
        return []
    try:
        return decode_polyline(polyline)
    except (TypeError, ValueError):
        return []


def _route_section_mode(value: str, fallback: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "WALKING":
        return "walking"
    if normalized in {"BICYCLING", "BICYCLE", "BIKE"}:
        return "bicycling"
    if normalized in {"RAIL", "SUBWAY", "METRO", "TRAIN"}:
        return "rail"
    if normalized in {"BUS", "COACH"}:
        return "bus"
    if normalized in {"DRIVING", "CAR", "TAXI"}:
        return "driving"
    if normalized in {"TRANSIT", "PUBLIC_TRANSPORT"}:
        return "transit"
    return fallback


def _route_sections(route: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    """Preserve Tencent's selected walking/vehicle geometry for map layers."""
    sections: list[dict[str, Any]] = []
    for step in route.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_mode = str(step.get("mode") or "")
        if step_mode.upper() == "WALKING":
            path = _decoded_polyline(step)
            if path:
                sections.append({
                    "mode": "walking",
                    "path": path,
                    "distance_meters": round(float(step.get("distance") or 0)),
                    "duration_seconds": round(float(step.get("duration") or 0) * 60),
                    "instruction": str(step.get("instruction") or "")[:240],
                })
            continue
        selected_lines = [
            line for line in (step.get("lines") or [])
            if isinstance(line, dict)
        ]
        selected = selected_lines[0] if selected_lines else step
        path = _decoded_polyline(selected) or _decoded_polyline(step)
        if not path:
            continue
        vehicle = str(selected.get("vehicle") or step_mode)
        geton = selected.get("geton") if isinstance(selected.get("geton"), dict) else {}
        getoff = selected.get("getoff") if isinstance(selected.get("getoff"), dict) else {}
        sections.append({
            "mode": _route_section_mode(vehicle, mode),
            "path": path,
            "distance_meters": round(float(selected.get("distance") or step.get("distance") or 0)),
            "duration_seconds": round(float(selected.get("duration") or step.get("duration") or 0) * 60),
            "line": str(selected.get("title") or selected.get("name") or "")[:120],
            "vehicle": vehicle.upper(),
            "geton": str(geton.get("title") or "")[:120],
            "getoff": str(getoff.get("title") or "")[:120],
            "station_count": max(0, int(selected.get("station_count") or 0)),
            "instruction": str(step.get("instruction") or "")[:240],
        })
    if sections:
        return sections
    path = _decoded_route_path(route)
    return ([{
        "mode": mode,
        "path": path,
        "distance_meters": round(float(route.get("distance") or 0)),
        "duration_seconds": round(float(route.get("duration") or 0) * 60),
    }] if path else [])


def _path_distance(path: list[dict[str, float]]) -> float:
    distance = 0.0
    for left, right in zip(path, path[1:]):
        lat = math.radians((float(left["latitude"]) + float(right["latitude"])) / 2)
        dy = (float(right["latitude"]) - float(left["latitude"])) * 111_320
        dx = (
            (float(right["longitude"]) - float(left["longitude"]))
            * 111_320
            * math.cos(lat)
        )
        distance += math.hypot(dx, dy)
    return distance


def _split_route_path(
    path: list[dict[str, float]], places: list[dict[str, Any]],
) -> list[list[dict[str, float]]]:
    """Split a single waypoint route at the nearest ordered stop coordinates."""
    if len(places) < 2:
        return []
    if len(path) < 2:
        return [[] for _ in range(len(places) - 1)]
    boundaries = [0]
    cursor = 0
    for place in places[1:-1]:
        target_lat = float(place.get("latitude") or 0)
        target_lng = float(place.get("longitude") or 0)
        remaining = range(cursor, len(path) - 1)
        nearest = min(
            remaining,
            key=lambda index: (
                (float(path[index]["latitude"]) - target_lat) ** 2
                + (float(path[index]["longitude"]) - target_lng) ** 2
            ),
            default=cursor,
        )
        cursor = max(cursor, nearest)
        boundaries.append(cursor)
    boundaries.append(len(path) - 1)
    return [path[start:end + 1] for start, end in zip(boundaries, boundaries[1:])]


async def normalize_route_places(
    key: str, places: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert browser WGS84 fixes to Tencent coordinates before road matching."""
    normalized = [copy.deepcopy(place) for place in places]
    browser_indexes = [
        index for index, place in enumerate(normalized)
        if str(place.get("provider") or "") == "browser-wgs84"
        or str(place.get("coordinate_type") or "") == "wgs84"
    ]
    if not browser_indexes:
        return normalized
    locations = ";".join(
        f"{float(normalized[index]['latitude'])},{float(normalized[index]['longitude'])}"
        for index in browser_indexes
    )
    data = await _get(
        f"{API_ROOT}/coord/v1/translate",
        {"key": key, "locations": locations, "type": 1},
    )
    translated = data.get("locations")
    if not isinstance(translated, list):
        translated = (data.get("result") or {}).get("locations")
    if not isinstance(translated, list) or len(translated) != len(browser_indexes):
        raise RuntimeError("腾讯坐标转换没有返回完整的当前位置结果")
    for index, location in zip(browser_indexes, translated):
        if not isinstance(location, dict):
            raise RuntimeError("腾讯坐标转换返回格式无效")
        lat, lng = location.get("lat"), location.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            raise RuntimeError("腾讯坐标转换缺少有效经纬度")
        original_provider = str(normalized[index].get("provider") or "")
        normalized[index].update({
            "provider": (
                "browser-tencent"
                if original_provider.startswith("browser")
                else original_provider or "tencent"
            ),
            "coordinate_type": "gcj02",
            "coordinate_transformed_by": "tencent",
            "latitude": float(lat),
            "longitude": float(lng),
        })
    return normalized


def _non_driving_fare(mode: str, route: dict[str, Any]) -> dict[str, Any]:
    if mode == "transit":
        estimate = route.get("fare_yuan")
        fare_known = bool(route.get("fare_known"))
        return {
            "currency": "CNY",
            "basis": "票价来自腾讯公交路线结果；实际票价受线路、优惠和支付方式影响",
            "transit": {
                "estimate": round(max(0.0, float(estimate or 0)), 2),
                "provider_estimate": fare_known,
            },
        }
    return {
        "currency": "CNY",
        "basis": "步行或骑行路线不估算交通票价",
    }


def _transit_summary(route: dict[str, Any]) -> dict[str, Any]:
    walking_distance = 0.0
    fare_yuan = 0.0
    fare_known = False
    lines: list[str] = []
    segments: list[dict[str, Any]] = []
    for step in route.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("mode") or "").upper() == "WALKING":
            walking_distance += float(step.get("distance") or 0)
            continue
        available_lines = [line for line in (step.get("lines") or []) if isinstance(line, dict)]
        if not available_lines:
            continue
        # Tencent documents later items as alternate lines over the same stops;
        # the first line carries the complete selected-leg details.
        line = available_lines[0]
        name = str(line.get("title") or line.get("name") or "").strip()
        if name and name not in lines:
            lines.append(name[:120])
        price = line.get("price")
        vehicle = str(line.get("vehicle") or "").upper()
        if isinstance(price, (int, float)) and price >= 0:
            fare_yuan += float(price) if vehicle == "RAIL" else float(price) / 100
            fare_known = True
        geton = line.get("geton") if isinstance(line.get("geton"), dict) else {}
        getoff = line.get("getoff") if isinstance(line.get("getoff"), dict) else {}
        segments.append({
            "line": name[:120],
            "vehicle": vehicle,
            "geton": str(geton.get("title") or "")[:120],
            "getoff": str(getoff.get("title") or "")[:120],
            "station_count": max(0, int(line.get("station_count") or 0)),
        })
    return {
        "walking_distance_meters": round(float(walking_distance or 0)),
        "lines": lines[:12],
        "transfer_count": max(0, len(segments) - 1),
        "segments": segments[:12],
        "fare_yuan": round(fare_yuan, 2),
        "fare_known": fare_known,
    }


async def _plan_route_leg(
    key: str,
    origin: dict[str, Any],
    destination: dict[str, Any],
    *,
    mode: str,
    waypoints: list[dict[str, Any]] | None = None,
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
) -> dict[str, Any]:
    coords = [origin, *(waypoints or []), destination]
    params: dict[str, Any] = {
        "key": key,
        "from": f"{float(origin['latitude'])},{float(origin['longitude'])}",
        "to": f"{float(destination['latitude'])},{float(destination['longitude'])}",
    }
    if mode == "driving":
        params.update({
            "policy": (
                "LEAST_TIME,LEAST_FEE"
                if strategy == "least_cost"
                else "LEAST_TIME"
            ),
            "get_mp": 1,
        })
        if waypoints:
            params["waypoints"] = ";".join(
                f"{float(place['latitude'])},{float(place['longitude'])}"
                for place in waypoints
            )
    elif mode == "transit":
        params["policy"] = "LEAST_TIME"
    data = await _get(f"{API_ROOT}/direction/v1/{mode}/", params)
    routes = (data.get("result") or {}).get("routes") or []
    candidates = [item for item in routes if isinstance(item, dict)]
    if not candidates:
        raise RuntimeError(f"腾讯位置服务没有返回可用的{mode}路线")
    fastest = min(
        candidates,
        key=lambda item: (
            float(item.get("duration") or math.inf),
            float(item.get("distance") or math.inf),
        ),
    )
    fastest_duration = float(fastest.get("duration") or math.inf)

    def candidate_cost(item: dict[str, Any]) -> float:
        if mode == "driving":
            distance = float(item.get("distance") or 0)
            toll = float(item.get("toll") or 0)
            return float(
                (_fare(distance, float(item.get("duration") or 0) * 60, toll)
                 .get("self_driving") or {}).get("estimate") or math.inf
            )
        if mode == "transit":
            summary = _transit_summary(item)
            if summary.get("fare_known"):
                return float(summary.get("fare_yuan") or 0)
        if mode in {"walking", "bicycling"}:
            return 0.0
        return math.inf

    tolerance = max(0, min(30, int(near_time_tolerance_minutes or 0)))
    if strategy == "least_cost":
        priced = [item for item in candidates if math.isfinite(candidate_cost(item))]
        route = min(
            priced or candidates,
            key=lambda item: (
                candidate_cost(item),
                float(item.get("duration") or math.inf),
                float(item.get("distance") or math.inf),
            ),
        )
    elif strategy == "time_then_cost":
        near_fastest = [
            item for item in candidates
            if float(item.get("duration") or math.inf) <= fastest_duration + tolerance
        ]
        priced = [item for item in near_fastest if math.isfinite(candidate_cost(item))]
        route = min(
            priced or near_fastest or [fastest],
            key=lambda item: (
                candidate_cost(item),
                float(item.get("duration") or math.inf),
                float(item.get("distance") or math.inf),
            ),
        )
    else:
        route = fastest
    distance = float(route.get("distance") or 0)
    # Tencent Direction WebService reports duration in minutes.
    duration = float(route.get("duration") or 0) * 60
    transit = _transit_summary(route) if mode == "transit" else {}
    if mode == "driving":
        toll = float(route.get("toll") or 0)
        taxi_estimate = (
            float(route.get("taxi_fare", {}).get("fare") or 0)
            if isinstance(route.get("taxi_fare"), dict)
            else 0
        )
        fare = _fare(distance, duration, toll, taxi_estimate)
    else:
        fare = _non_driving_fare(mode, transit)
    return {
        "places": coords,
        "path": _decoded_route_path(route),
        "sections": _route_sections(route, mode),
        "distance_meters": distance,
        "duration_seconds": duration,
        "fare": fare,
        "selection": {
            "strategy": strategy,
            "near_time_tolerance_minutes": tolerance,
            "provider_policy": str(params.get("policy") or ""),
            "candidate_count": len(candidates),
            "fastest_duration_seconds": (
                round(fastest_duration * 60)
                if math.isfinite(fastest_duration)
                else 0
            ),
            "selected_cost_yuan": (
                round(candidate_cost(route), 2)
                if math.isfinite(candidate_cost(route))
                else None
            ),
            "cost_source": (
                "estimated_self_driving"
                if mode == "driving"
                else "tencent_transit_fare"
                if mode == "transit" and math.isfinite(candidate_cost(route))
                else "zero_cost_mode"
                if mode in {"walking", "bicycling"}
                else "unavailable"
            ),
        },
        **({"transit": transit} if mode == "transit" else {}),
    }


async def plan_route(
    key: str,
    places: list[dict[str, Any]],
    *,
    optimize: bool = False,
    mode: str = "driving",
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
) -> dict[str, Any]:
    if not key:
        raise RuntimeError("未配置 TENCENT_MAP_KEY")
    if len(places) < 2:
        raise ValueError("至少需要两个有效地点才能规划路线")
    if len(places) > 12:
        raise ValueError("单条路线最多支持 12 个地点")
    mode = str(mode or "driving").strip().lower()
    if mode not in {"driving", "transit", "walking", "bicycling"}:
        raise ValueError("路线方式必须是 driving、transit、walking 或 bicycling")
    strategy = str(strategy or "time_then_cost").strip().lower()
    if strategy not in {"time_then_cost", "least_time", "least_cost"}:
        raise ValueError("路线策略必须是 time_then_cost、least_time 或 least_cost")
    places = await normalize_route_places(key, places)
    if optimize and mode == "driving":
        places = await optimize_place_order(key, places)
    if mode == "driving":
        combined = await _plan_route_leg(
            key,
            places[0],
            places[-1],
            mode=mode,
            waypoints=places[1:-1],
            strategy=strategy,
            near_time_tolerance_minutes=near_time_tolerance_minutes,
        )
        leg_paths = _split_route_path(
            list(combined.get("path") or []), places,
        )
        measured_total = sum(_path_distance(path) for path in leg_paths)
        combined["legs"] = []
        for index, leg_path in enumerate(leg_paths):
            share = (
                _path_distance(leg_path) / measured_total
                if measured_total > 0 else 1 / max(1, len(leg_paths))
            )
            leg_distance = round(float(combined.get("distance_meters") or 0) * share)
            leg_duration = round(float(combined.get("duration_seconds") or 0) * share)
            combined["legs"].append({
                "from": places[index],
                "to": places[index + 1],
                "mode": mode,
                "path": leg_path,
                "sections": [{
                    "mode": mode,
                    "path": leg_path,
                    "distance_meters": leg_distance,
                    "duration_seconds": leg_duration,
                }],
                "distance_meters": leg_distance,
                "duration_seconds": leg_duration,
            })
    else:
        semaphore = asyncio.Semaphore(3)

        async def plan_index(index: int) -> dict[str, Any]:
            async with semaphore:
                return await _plan_route_leg(
                    key,
                    places[index],
                    places[index + 1],
                    mode=mode,
                    strategy=strategy,
                    near_time_tolerance_minutes=near_time_tolerance_minutes,
                )

        legs = await asyncio.gather(*(plan_index(index) for index in range(len(places) - 1)))
        path: list[dict[str, float]] = []
        for leg in legs:
            segment = list(leg.get("path") or [])
            if path and segment and path[-1] == segment[0]:
                segment = segment[1:]
            path.extend(segment)
        combined = {
            "path": path,
            "legs": [
                {
                    "from": places[index],
                    "to": places[index + 1],
                    "mode": mode,
                    "path": list(leg.get("path") or []),
                    "sections": list(leg.get("sections") or []),
                    "distance_meters": round(float(leg.get("distance_meters") or 0)),
                    "duration_seconds": round(float(leg.get("duration_seconds") or 0)),
                    **({"fare": leg.get("fare") or {}} if leg.get("fare") else {}),
                    **({"transit": leg.get("transit") or {}} if mode == "transit" else {}),
                }
                for index, leg in enumerate(legs)
            ],
            "distance_meters": sum(float(leg.get("distance_meters") or 0) for leg in legs),
            "duration_seconds": sum(float(leg.get("duration_seconds") or 0) for leg in legs),
            "fare": (
                {
                    "currency": "CNY",
                    "basis": "票价为各段腾讯公交路线票价之和；实际票价受线路、优惠和支付方式影响",
                    "transit": {
                        "estimate": round(sum(
                            float(((leg.get("fare") or {}).get("transit") or {}).get("estimate") or 0)
                            for leg in legs
                        ), 2),
                        "provider_estimate": all(
                            bool(((leg.get("fare") or {}).get("transit") or {}).get("provider_estimate"))
                            for leg in legs
                        ),
                    },
                }
                if mode == "transit"
                else _non_driving_fare(mode, {})
            ),
            **(
                {"transit": {
                    "walking_distance_meters": round(sum(
                        float((leg.get("transit") or {}).get("walking_distance_meters") or 0)
                        for leg in legs
                    )),
                    "lines": [
                        line
                        for leg in legs
                        for line in (leg.get("transit") or {}).get("lines") or []
                    ][:24],
                    "legs": [leg.get("transit") or {} for leg in legs],
                }}
                if mode == "transit"
                else {}
            ),
            "selection": {
                "strategy": strategy,
                "near_time_tolerance_minutes": max(
                    0, min(30, int(near_time_tolerance_minutes or 0)),
                ),
                "provider_policy": "LEAST_TIME" if mode == "transit" else "",
                "candidate_count": sum(
                    int((leg.get("selection") or {}).get("candidate_count") or 0)
                    for leg in legs
                ),
                "leg_selections": [leg.get("selection") or {} for leg in legs],
            },
        }
    return {
        "schema_version": 4,
        "provider": "tencent",
        "mode": mode,
        "places": places,
        **combined,
    }


async def plan_driving_route(
    key: str,
    places: list[dict[str, Any]],
    *,
    optimize: bool = False,
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
) -> dict[str, Any]:
    """Backward-compatible driving entrypoint."""
    return await plan_route(
        key,
        places,
        optimize=optimize,
        mode="driving",
        strategy=strategy,
        near_time_tolerance_minutes=near_time_tolerance_minutes,
    )


async def plan_verified_route(
    key: str,
    places: list[dict[str, Any]],
    *,
    optimize: bool = False,
    mode: str = "driving",
    strategy: str = "time_then_cost",
    near_time_tolerance_minutes: int = 10,
    timeout_seconds: float = 18,
) -> dict[str, Any]:
    """Plan roads exclusively with Tencent Location Service.

    Public OSM is deliberately limited to POI search fallback. A Tencent
    failure is surfaced instead of silently changing the road-matching
    provider and semantics.
    """
    if not key:
        raise RuntimeError("未配置腾讯地图服务密钥，无法计算道路路线")
    timeout = max(5.0, min(25.0, float(timeout_seconds)))
    try:
        return await asyncio.wait_for(
            (
                plan_driving_route(
                    key,
                    places,
                    optimize=optimize,
                    strategy=strategy,
                    near_time_tolerance_minutes=near_time_tolerance_minutes,
                )
                if str(mode or "driving") == "driving"
                else plan_route(
                    key,
                    places,
                    optimize=optimize,
                    mode=mode,
                    strategy=strategy,
                    near_time_tolerance_minutes=near_time_tolerance_minutes,
                )
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"腾讯地图路线服务超过 {round(timeout)} 秒未响应") from exc


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
