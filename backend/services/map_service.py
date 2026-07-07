"""腾讯位置服务：路线规划、距离计算、地点搜索、天气。

优化策略：
- direction_with_waypoints: 一次 API 规划含途经点的完整路线（替代逐段调用）
- batch_distance_matrix: 一次 API 获取 N×N 距离矩阵
- get_weather: 使用 geo_cache 缓存 adcode，不重复 geocode
- get_adcode: 逆 geocode 获取 adcode
"""
from __future__ import annotations

from typing import Any

import httpx

from config import settings

# 主要城市经纬度（geocode 超限时的兜底）
_CITY_COORDS: dict[str, dict[str, float]] = {
    "北京": {"lat": 39.905, "lng": 116.724},
    "上海": {"lat": 31.230, "lng": 121.473},
    "广州": {"lat": 23.129, "lng": 113.264},
    "深圳": {"lat": 22.543, "lng": 114.057},
    "杭州": {"lat": 30.274, "lng": 120.155},
    "成都": {"lat": 30.572, "lng": 104.066},
    "西安": {"lat": 34.341, "lng": 108.940},
    "厦门": {"lat": 24.479, "lng": 118.089},
    "三亚": {"lat": 18.252, "lng": 109.580},
    "丽江": {"lat": 26.872, "lng": 100.226},
    "南京": {"lat": 32.060, "lng": 118.796},
    "武汉": {"lat": 30.592, "lng": 114.305},
    "重庆": {"lat": 29.563, "lng": 106.551},
    "长沙": {"lat": 28.228, "lng": 112.938},
    "天津": {"lat": 39.085, "lng": 117.199},
    "青岛": {"lat": 36.067, "lng": 120.382},
    "昆明": {"lat": 25.039, "lng": 102.718},
    "大连": {"lat": 38.914, "lng": 121.614},
    "海口": {"lat": 20.045, "lng": 110.201},
    "大理": {"lat": 25.693, "lng": 100.162},
    "桂林": {"lat": 25.274, "lng": 110.290},
    "拉萨": {"lat": 29.650, "lng": 91.140},
    "苏州": {"lat": 31.299, "lng": 120.585},
}


class MapService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._base = "https://apis.map.qq.com"

    async def close(self) -> None:
        await self._client.aclose()

    async def geocode(self, address: str) -> dict[str, float]:
        """地址 → 经纬度。"""
        try:
            resp = await self._client.get(
                f"{self._base}/ws/geocoder/v1/",
                params={"address": address, "key": settings.tencent_map_key},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == 0:
                loc = data.get("result", {}).get("location", {})
                return {"lat": loc.get("lat", 0), "lng": loc.get("lng", 0)}
        except Exception:
            pass
        return {"lat": 0, "lng": 0}

    async def get_adcode(self, lat: float, lng: float) -> str:
        """逆 geocode 获取 adcode（用于天气查询）。"""
        try:
            resp = await self._client.get(
                f"{self._base}/ws/geocoder/v1/",
                params={"location": f"{lat},{lng}", "key": settings.tencent_map_key},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == 0:
                return data.get("result", {}).get("ad_info", {}).get("adcode", "")
        except Exception:
            pass
        return ""

    async def direction_driving(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> dict[str, Any]:
        """驾车路线规划（两点间）。"""
        from_str = f"{from_lat},{from_lng}"
        to_str = f"{to_lat},{to_lng}"
        resp = await self._client.get(
            f"{self._base}/ws/direction/v1/driving/",
            params={"from": from_str, "to": to_str, "key": settings.tencent_map_key},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 0:
            routes = data.get("result", {}).get("routes", [])
            if routes:
                r = routes[0]
                return {
                    "distance": r.get("distance", 0),
                    "duration": r.get("duration", 0),
                    "polyline": r.get("polyline", []),
                    "toll": r.get("toll", 0),
                }
        elif data.get("status") == 121:
            raise RuntimeError("腾讯地图 API 每日调用量已达到上限，请明天重试")
        return {"distance": 0, "duration": 0, "polyline": []}

    async def direction_with_waypoints(
        self, points: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """驾车路线规划（含途经点，一次 API）。

        Args:
            points: [{lat, lng, name}, ...] 按顺序的地点列表

        Returns:
            {distance, duration, polyline, toll, segments}
        """
        if len(points) < 2:
            return {"distance": 0, "duration": 0, "polyline": [], "toll": 0, "segments": []}

        from_str = f"{points[0]['lat']},{points[0]['lng']}"
        to_str = f"{points[-1]['lat']},{points[-1]['lng']}"

        params: dict[str, Any] = {
            "from": from_str,
            "to": to_str,
            "key": settings.tencent_map_key,
        }

        # 途经点（中间点，用 ; 分隔）
        if len(points) > 2:
            waypoints = ";".join(
                f"{p['lat']},{p['lng']}" for p in points[1:-1]
            )
            params["waypoints"] = waypoints

        resp = await self._client.get(
            f"{self._base}/ws/direction/v1/driving/", params=params
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == 0:
            routes = data.get("result", {}).get("routes", [])
            if routes:
                r = routes[0]
                return {
                    "distance": r.get("distance", 0),
                    "duration": r.get("duration", 0),
                    "polyline": r.get("polyline", []),
                    "toll": r.get("toll", 0),
                }
        elif data.get("status") == 121:
            raise RuntimeError("腾讯地图 API 每日调用量已达到上限")

        return {"distance": 0, "duration": 0, "polyline": [], "toll": 0}

    async def batch_distance_matrix(
        self, points: list[dict[str, Any]], mode: str = "driving"
    ) -> list[list[dict[str, int]]]:
        """批量距离矩阵：一次 API 获取 N×N 距离矩阵。

        Args:
            points: [{lat, lng, name}, ...]

        Returns:
            N×N 矩阵，matrix[i][j] = {distance, duration}
        """
        if not points:
            return []

        # 腾讯地图 distance API 支持 from 和 to 传多个坐标（; 分隔）
        coords = [f"{p['lat']},{p['lng']}" for p in points]
        from_str = ";".join(coords)
        to_str = ";".join(coords)

        resp = await self._client.get(
            f"{self._base}/ws/distance/v1/",
            params={
                "from": from_str,
                "to": to_str,
                "mode": mode,
                "key": settings.tencent_map_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        n = len(points)
        matrix = [[{"distance": 0, "duration": 0} for _ in range(n)] for _ in range(n)]

        if data.get("status") == 0:
            elements = data.get("result", {}).get("elements", [])
            for e in elements:
                fi = e.get("from", 0)
                ti = e.get("to", 0)
                if 0 <= fi < n and 0 <= ti < n:
                    matrix[fi][ti] = {
                        "distance": e.get("distance", 0),
                        "duration": e.get("duration", 0),
                    }

        return matrix

    async def place_search(self, keyword: str, city: str = "") -> list[dict]:
        """地点搜索。"""
        params = {
            "keyword": keyword,
            "key": settings.tencent_map_key,
            "page_size": 10,
        }
        if city:
            params["boundary"] = f"region({city},0)"
        resp = await self._client.get(
            f"{self._base}/ws/place/v1/search", params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 0:
            return data.get("data", [])
        return []

    async def get_weather(self, city: str) -> dict[str, Any]:
        """查询城市天气。使用 geo_cache 缓存 adcode，避免重复 geocode。"""
        from services.geo_cache import get_adcode
        from database.connection import get_db
        import time as _time
        import json as _json

        # 1. 查天气缓存（30 分钟 TTL）
        db = await get_db()
        cursor = await db.execute(
            "SELECT weather_json, updated_at FROM weather_cache WHERE city = ?", (city,)
        )
        row = await cursor.fetchone()
        if row and (_time.time() - row[1] < 1800):
            return _json.loads(row[0])

        # 2. 获取 adcode（从缓存或 geocode）
        adcode = await get_adcode(city)
        if not adcode:
            return {"error": f"无法获取{city}的天气"}

        # 3. 查天气 API
        try:
            wresp = await self._client.get(
                f"{self._base}/ws/weather/v1/",
                params={"adcode": adcode, "key": settings.tencent_map_key},
            )
            wdata = wresp.json()
            if wdata.get("status") == 0:
                realtime = wdata.get("result", {}).get("realtime", [])
                if realtime:
                    info = realtime[0].get("infos", {})
                    result = {
                        "city": city,
                        "weather": info.get("weather", ""),
                        "temperature": info.get("temperature", 0),
                        "wind_direction": info.get("wind_direction", ""),
                        "wind_power": info.get("wind_power", ""),
                        "humidity": info.get("humidity", ""),
                        "precipitation": info.get("precipitation", ""),
                        "pressure": info.get("pressure", ""),
                        "tips": _weather_tips(info.get("weather", "")),
                    }
                    # 写入缓存
                    await db.execute(
                        "INSERT OR REPLACE INTO weather_cache (city, weather_json, adcode, updated_at) VALUES (?, ?, ?, ?)",
                        (city, _json.dumps(result, ensure_ascii=False), adcode, _time.time()),
                    )
                    await db.commit()
                    return result
        except Exception:
            pass
        return {"error": f"无法获取{city}的天气"}

    async def plan_travel_route(
        self, origin: str, destination: str, waypoints: list[str] | None = None
    ) -> dict[str, Any]:
        """规划城市间路线（使用 waypoints 一次 API）。"""
        from services.geo_cache import get_coords

        # 获取所有地点坐标（优先缓存）
        origin_loc = await get_coords(origin)
        if not origin_loc["lat"]:
            origin_loc = _CITY_COORDS.get(origin, {"lat": 0, "lng": 0})
            if not origin_loc["lat"]:
                return {"error": f"无法找到出发地：{origin}"}

        dest_loc = await get_coords(destination)
        if not dest_loc["lat"]:
            dest_loc = _CITY_COORDS.get(destination, {"lat": 0, "lng": 0})
            if not dest_loc["lat"]:
                return {"error": f"无法找到目的地：{destination}"}

        waypoint_locs = []
        if waypoints:
            for wp in waypoints:
                loc = await get_coords(wp)
                if not loc["lat"]:
                    loc = _CITY_COORDS.get(wp, {"lat": 0, "lng": 0})
                if loc["lat"]:
                    waypoint_locs.append({"name": wp, "lat": loc["lat"], "lng": loc["lng"]})

        # 构建路线点列表
        all_points = [
            {"name": origin, "lat": origin_loc["lat"], "lng": origin_loc["lng"]},
        ] + waypoint_locs + [
            {"name": destination, "lat": dest_loc["lat"], "lng": dest_loc["lng"]},
        ]

        # 一次 API 获取完整路线
        route = await self.direction_with_waypoints(all_points)

        distance_km = route["distance"] / 1000
        cost_estimate = {
            "self_driving": round(distance_km * 0.7 + route["toll"]),
            "taxi": round(distance_km * 3),
            "toll": route["toll"],
        }

        weather = await self.get_weather(destination)

        return {
            "origin": origin,
            "origin_location": origin_loc,
            "destination": destination,
            "destination_location": dest_loc,
            "waypoints": [w["name"] for w in waypoint_locs],
            "waypoint_locations": [{"lat": w["lat"], "lng": w["lng"]} for w in waypoint_locs],
            "distance": route["distance"],
            "duration": route["duration"],
            "toll": route["toll"],
            "polyline": route["polyline"],
            "total_distance": route["distance"],
            "total_duration": route["duration"],
            "total_distance_km": round(distance_km, 1),
            "total_duration_hours": round(route["duration"] / 3600, 1),
            "total_toll": route["toll"],
            "cost_estimate": cost_estimate,
            "weather": weather,
        }


map_service = MapService()


def _weather_tips(weather: str) -> str:
    """根据天气生成旅游建议。"""
    w = weather.lower() if weather else ""
    if any(k in w for k in ["雨", "雷", "暴"]):
        return "雨天建议安排室内活动：博物馆、美术馆、购物中心、美食探店"
    if any(k in w for k in ["雪", "冰", "霜"]):
        return "雪天注意保暖，推荐温泉、室内景点，谨慎驾车"
    if any(k in w for k in ["晴", "多云"]):
        return "天气不错，适合户外景点和 Citywalk"
    if any(k in w for k in ["雾", "霾"]):
        return "能见度较低，建议减少户外活动，佩戴口罩"
    if any(k in w for k in ["风", "大风"]):
        return "大风天气，注意安全，避免高空项目"
    return "出行前关注天气变化"
