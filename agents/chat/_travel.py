"""Travel intent, memory, place search, and itinerary helpers for Makers."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from langchain_core.messages import HumanMessage, SystemMessage


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_PLACE_API_BASE_URL = "https://94-16-110-28.sslip.io"
PROFILE_FIELDS = {
    "home_city",
    "pace",
    "budget",
    "interests",
    "food_preferences",
    "transport",
    "party",
    "accessibility",
}
TRAVEL_HINTS = (
    "旅游", "旅行", "行程", "攻略", "景点", "好玩", "去哪", "餐馆", "餐厅",
    "美食", "住宿", "酒店", "路线", "打卡", "citywalk", "周末游",
)
ITINERARY_HINTS = ("好玩", "攻略", "行程", "怎么玩")
DATED_VISIT_HINTS = ("去", "游", "逛", "参观", "玩")
NO_ITINERARY_HINTS = (
    "只推荐", "只要推荐", "不要排行程", "不用排行程", "不需要行程", "别安排行程",
)
KNOWN_CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "西安", "南京", "武汉",
    "长沙", "苏州", "厦门", "青岛", "天津", "昆明", "大理", "丽江", "三亚", "桂林",
    "哈尔滨", "沈阳", "大连", "郑州", "济南", "福州", "泉州", "香港", "澳门", "台北",
    "东京", "大阪", "京都", "首尔", "新加坡", "曼谷", "巴黎", "伦敦", "罗马", "纽约",
    "洛杉矶", "旧金山", "悉尼", "墨尔本", "迪拜", "伊斯坦布尔",
)
LANDMARK_CITIES = {
    "故宫": "北京",
    "天安门": "北京",
    "长城": "北京",
    "西湖": "杭州",
    "外滩": "上海",
    "兵马俑": "西安",
    "鼓浪屿": "厦门",
}
LANDMARK_AREA_PLACES = {
    "天安门": [
        {
            "id": "landmark-tiananmen-square",
            "name": "天安门广场",
            "address": "北京市东城区东长安街",
            "category": "attraction",
            "lat": 39.9037,
            "lng": 116.3976,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_landmark_area",
        },
        {
            "id": "landmark-national-museum",
            "name": "中国国家博物馆",
            "address": "北京市东城区东长安街16号",
            "category": "attraction",
            "lat": 39.9039,
            "lng": 116.4013,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_landmark_area",
        },
        {
            "id": "landmark-mausoleum",
            "name": "毛主席纪念堂",
            "address": "北京市东城区前门东大街11号",
            "category": "attraction",
            "lat": 39.9011,
            "lng": 116.3975,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_landmark_area",
        },
        {
            "id": "landmark-qianmen-street",
            "name": "前门大街",
            "address": "北京市东城区前门大街",
            "category": "attraction",
            "lat": 39.8974,
            "lng": 116.3975,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_landmark_area",
        },
    ],
}
CITY_FALLBACK_PLACES = {
    "杭州": [
        {
            "id": "city-hangzhou-west-lake",
            "name": "西湖风景名胜区",
            "address": "杭州市西湖区龙井路1号",
            "category": "attraction",
            "lat": 30.2495,
            "lng": 120.1437,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_city_fallback",
        },
        {
            "id": "city-hangzhou-lingyin-temple",
            "name": "灵隐寺",
            "address": "杭州市西湖区法云弄1号",
            "category": "attraction",
            "lat": 30.2408,
            "lng": 120.1022,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_city_fallback",
        },
        {
            "id": "city-hangzhou-xixi-wetland",
            "name": "西溪国家湿地公园",
            "address": "杭州市西湖区天目山路518号",
            "category": "attraction",
            "lat": 30.2709,
            "lng": 120.0626,
            "rating": 0,
            "tel": "",
            "distance": 0,
            "source": "curated_city_fallback",
        },
    ],
}


def _env_value(env: Any, key: str, default: str = "") -> str:
    if isinstance(env, dict):
        value = env.get(key, default)
    else:
        value = getattr(env, key, default)
    return str(value or default).strip()


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


def _item_value(item: Any) -> Any:
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get("value", item)
    return getattr(item, "value", item)


def _safe_user_id(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:-]", "-", str(value or "anonymous"))[:128]
    return cleaned or "anonymous"


def _namespace(user_id: str, kind: str) -> tuple[str, ...]:
    return ("users", _safe_user_id(user_id), kind)


async def _store_get(store, namespace: tuple[str, ...], key: str) -> Any:
    method = getattr(store, "aget", None) or getattr(store, "get", None)
    if method is None:
        return None
    return _item_value(await _maybe_await(method(namespace, key)))


async def _store_put(store, namespace: tuple[str, ...], key: str, value: dict) -> None:
    method = getattr(store, "aput", None) or getattr(store, "put", None)
    if method is None:
        raise RuntimeError("Makers langgraph_store does not provide put/aput")
    await _maybe_await(method(namespace, key, value))


async def _store_delete(store, namespace: tuple[str, ...], key: str) -> None:
    method = getattr(store, "adelete", None) or getattr(store, "delete", None)
    if method is None:
        raise RuntimeError("Makers langgraph_store does not provide delete/adelete")
    await _maybe_await(method(namespace, key))


async def _store_search(store, namespace: tuple[str, ...], *, limit: int = 100) -> list:
    method = getattr(store, "asearch", None) or getattr(store, "search", None)
    if method is None:
        return []
    result = await _maybe_await(method(namespace, limit=limit))
    return list(result or [])


async def load_recent_conversation(checkpointer, conversation_id: str, *, limit: int = 12) -> str:
    """Read recent LangGraph messages for pre-graph travel analysis.

    Makers exposes the native BaseCheckpointSaver adapter.  The adapter shape
    can vary slightly between LangGraph versions, so this helper deliberately
    accepts both sync/async methods and object/dict checkpoint tuples.
    """

    if not checkpointer or not conversation_id:
        return ""
    method = getattr(checkpointer, "aget_tuple", None) or getattr(checkpointer, "get_tuple", None)
    if method is None:
        return ""
    try:
        item = await _maybe_await(method({"configurable": {"thread_id": conversation_id}}))
        checkpoint = (
            item.get("checkpoint") if isinstance(item, dict)
            else getattr(item, "checkpoint", None)
        )
        if not isinstance(checkpoint, dict):
            return ""
        channel_values = checkpoint.get("channel_values")
        messages = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
        lines: list[str] = []
        for message in list(messages)[-limit:]:
            role = str(getattr(message, "type", "") or "")
            if role not in {"human", "user", "ai", "assistant"}:
                continue
            content = getattr(message, "content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            label = "用户" if role in {"human", "user"} else "助手"
            lines.append(f"{label}：{content[:1000]}")
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


async def load_profile(store, user_id: str) -> dict[str, Any]:
    value = await _store_get(store, _namespace(user_id, "memory"), "travel-profile")
    return value if isinstance(value, dict) else {}


async def merge_profile(
    store,
    user_id: str,
    updates: dict[str, Any],
    *,
    source_conversation_id: str,
) -> dict[str, Any]:
    """Persist only non-sensitive travel preferences inferred from user text."""

    current = await load_profile(store, user_id)
    fields = dict(current.get("fields") or {})
    now = datetime.now(SHANGHAI_TZ).isoformat()
    for key, raw in updates.items():
        if key not in PROFILE_FIELDS:
            continue
        value = raw.get("value") if isinstance(raw, dict) else raw
        confidence = raw.get("confidence", 0.65) if isinstance(raw, dict) else 0.65
        if value in (None, "", []):
            continue
        fields[key] = {
            "value": value,
            "confidence": max(0.1, min(float(confidence or 0.65), 0.95)),
            "updated_at": now,
            "source_conversation_id": source_conversation_id,
        }
    profile = {"schema_version": 1, "fields": fields, "updated_at": now}
    await _store_put(store, _namespace(user_id, "memory"), "travel-profile", profile)
    return profile


def profile_prompt(profile: dict[str, Any]) -> str:
    fields = profile.get("fields") if isinstance(profile, dict) else {}
    if not isinstance(fields, dict) or not fields:
        return "尚无可靠的长期旅行偏好；不要凭空假设用户年龄、收入或家庭情况。"
    readable = {
        key: item.get("value") if isinstance(item, dict) else item
        for key, item in fields.items()
        if key in PROFILE_FIELDS
    }
    return "已确认或由上下文推断的旅行偏好：" + json.dumps(readable, ensure_ascii=False)


def _profile_value(profile: dict[str, Any], key: str, default: Any = "") -> Any:
    fields = profile.get("fields") if isinstance(profile, dict) else {}
    item = fields.get(key) if isinstance(fields, dict) else None
    return item.get("value", default) if isinstance(item, dict) else (item or default)


def _preference_tokens(profile: dict[str, Any], *keys: str) -> list[str]:
    tokens: list[str] = []
    for key in keys:
        value = _profile_value(profile, key)
        values = value if isinstance(value, list) else re.split(r"[,，、/\s]+", str(value or ""))
        for item in values:
            token = str(item).strip().casefold()
            if len(token) >= 2 and token not in tokens:
                tokens.append(token)
    return tokens


def looks_like_travel(message: str) -> bool:
    lowered = message.lower()
    if any(hint in lowered for hint in TRAVEL_HINTS):
        return True
    has_named_destination = (
        any(landmark in message for landmark in LANDMARK_CITIES)
        or any(city.casefold() in lowered for city in KNOWN_CITIES)
    )
    return has_named_destination and any(hint in message for hint in DATED_VISIT_HINTS)


def _now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _start_date_from_message(message: str) -> str:
    """Resolve explicit and common relative dates without trusting the model clock."""

    date_match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", message)
    if date_match:
        return f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    relative_dates = (
        ("大后天", 3),
        ("后天", 2),
        ("明天", 1),
        ("明日", 1),
        ("今天", 0),
        ("今日", 0),
    )
    today = _now_shanghai().date()
    for phrase, offset in relative_dates:
        if phrase in message:
            return (today + timedelta(days=offset)).isoformat()
    return ""


def _fallback_analysis(message: str) -> dict[str, Any]:
    landmark = next((item for item in LANDMARK_CITIES if item in message), "")
    city = next(
        (item for item in KNOWN_CITIES if item.lower() in message.lower()),
        LANDMARK_CITIES.get(landmark, ""),
    )
    count_match = re.search(r"(?:推荐|找|给我)?\s*(\d{1,2})\s*(?:家|个|处)", message)
    days_match = re.search(r"(\d{1,2})\s*天", message)
    category = "restaurant" if any(k in message for k in ("餐馆", "餐厅", "美食", "吃")) else "attraction"
    start_date = _start_date_from_message(message)
    wants_itinerary = (
        category != "restaurant"
        and (
            any(k in message for k in ITINERARY_HINTS)
            or (bool(start_date) and any(k in message for k in DATED_VISIT_HINTS))
        )
        and not any(k in message for k in NO_ITINERARY_HINTS)
    )
    return {
        "travel_related": True,
        "city": city,
        "query": "餐厅" if category == "restaurant" else (landmark or "景点"),
        "category": category,
        "count": max(1, min(int(count_match.group(1)) if count_match else 6, 12)),
        "wants_itinerary": wants_itinerary,
        "days": max(1, min(int(days_match.group(1)) if days_match else 1, 7)),
        "start_date": start_date,
        "memory_updates": {},
    }


async def analyze_travel_request(
    model,
    message: str,
    profile: dict[str, Any],
    *,
    recent_context: str = "",
) -> dict[str, Any]:
    """Use the main model for robust place/trip parsing, with a deterministic fallback."""

    fallback = _fallback_analysis(message)
    prompt = f"""分析这条旅行或地点请求，只返回一个 JSON 对象，不要 Markdown。
字段：
- travel_related: boolean
- city: 城市或地区名称，缺失则空字符串
- query: 适合地点搜索的短关键词
- category: attraction|restaurant|hotel|shopping|transport|other
- count: 1-12
- wants_itinerary: 用户是否期待游玩安排；普通餐馆列表为 false
- days: 1-7
- start_date: YYYY-MM-DD，未提日期为空字符串
- memory_updates: 仅从用户明确表达或强上下文中提取，可用键只有 {sorted(PROFILE_FIELDS)}；每项格式 {{"value":...,"confidence":0-1}}。不得推断敏感身份、精确住址、健康、财务或联系方式。

已有偏好：{profile_prompt(profile)}
最近对话（只用于理解省略信息与延续需求，不得覆盖用户当前表达）：
{recent_context[-6000:] or "无"}
用户消息：{message[:2000]}"""
    try:
        response = await asyncio.wait_for(
            model.ainvoke([
                SystemMessage(content="你是旅行请求结构化分析器，只输出严格 JSON。"),
                HumanMessage(content=prompt),
            ], config={"tags": ["internal_travel_analysis"]}),
            timeout=30,
        )
        raw = str(getattr(response, "content", ""))
        match = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(match.group(0)) if match else {}
        if not isinstance(parsed, dict):
            return fallback
        merged = {**fallback, **parsed}
        merged["count"] = max(1, min(int(merged.get("count") or fallback["count"]), 12))
        merged["days"] = max(1, min(int(merged.get("days") or 1), 7))
        # Explicit planning language is a deterministic lower bound.  The
        # classifier may add an itinerary, but must not suppress the product's
        # proactive-plan contract for prompts such as “杭州有啥好玩的”.
        merged["wants_itinerary"] = bool(merged.get("wants_itinerary")) or bool(
            fallback["wants_itinerary"]
        )
        # An explicit landmark in the current message is stronger than a
        # model-generated city-wide query such as “北京景点”. Keep map, prose,
        # and persisted schedules anchored to the place the user named.
        landmark = next((item for item in LANDMARK_CITIES if item in message), "")
        if landmark:
            merged["city"] = LANDMARK_CITIES[landmark]
            merged["query"] = landmark
            merged["category"] = "attraction"
        else:
            # A city explicitly named in the current turn is stronger than
            # profile memory and recent conversation. This prevents an older
            # Beijing trip from hijacking a new “杭州一日游” request.
            explicit_city = next(
                (item for item in KNOWN_CITIES if item.casefold() in message.casefold()),
                "",
            )
            if explicit_city:
                merged["city"] = explicit_city
        # Relative dates must use the server's Shanghai clock.  Models can have
        # a different or stale notion of "today", so a deterministic date from
        # the current user message always wins over model output and history.
        if fallback.get("start_date"):
            merged["start_date"] = fallback["start_date"]
        if merged.get("category") not in {"attraction", "restaurant", "hotel", "shopping", "transport", "other"}:
            merged["category"] = fallback["category"]
        if not isinstance(merged.get("memory_updates"), dict):
            merged["memory_updates"] = {}
        return merged
    except Exception:
        return fallback


def _normalize_place(item: dict[str, Any], source: str) -> dict[str, Any]:
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    lat = item.get("lat", location.get("lat", 0))
    lng = item.get("lng", location.get("lng", 0))
    return {
        "id": str(item.get("id") or item.get("osm_id") or f"{source}-{uuid4().hex[:12]}"),
        "name": str(item.get("name") or item.get("title") or "未知地点"),
        "address": str(item.get("address") or item.get("street") or ""),
        "category": str(item.get("category") or item.get("type") or "other"),
        "lat": float(lat or 0),
        "lng": float(lng or 0),
        "rating": float(item.get("rating") or 0),
        "tel": str(item.get("tel") or item.get("phone") or ""),
        "distance": float(item.get("distance") or item.get("distance_m") or 0),
        "source": source,
    }


def _place_identity(place: dict[str, Any]) -> tuple[Any, ...]:
    name = re.sub(r"\s+", "", str(place.get("name") or "")).casefold()
    address = re.sub(r"\s+", "", str(place.get("address") or "")).casefold()
    if name and address:
        return ("text", name, address)
    try:
        return ("geo", name, round(float(place.get("lat") or 0), 4), round(float(place.get("lng") or 0), 4))
    except (TypeError, ValueError):
        return ("name", name)


def _merge_places(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for group in groups:
        for place in group:
            identity = _place_identity(place)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(place)
            if len(merged) >= limit:
                return merged
    return merged


CATEGORY_FALLBACK_QUERIES = {
    "attraction": "景点",
    "restaurant": "餐厅",
    "hotel": "酒店",
    "shopping": "购物",
    "transport": "交通枢纽",
}


def _place_query_variants(city: str, query: str, category: str) -> list[str]:
    """Return progressively broader queries without losing the original intent.

    The model may produce a useful ranking phrase such as ``杭州 历史文化 景点``.
    Both the private exact-name index and Tencent's keyword API can legitimately
    return zero for that phrase even though the city has plenty of attractions.
    Keep the phrase first, then remove the city (already supplied as a boundary),
    add an interest-shaped POI class, and finally use the category-wide query.
    """

    normalized = re.sub(r"[，,、/|]+", " ", str(query or "")).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    variants: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" -")
        if value and value.casefold() not in {item.casefold() for item in variants}:
            variants.append(value)

    add(normalized)
    if city:
        add(re.sub(re.escape(city), " ", normalized, flags=re.IGNORECASE))

    lowered = normalized.casefold()
    if category == "attraction":
        if any(token in lowered for token in ("历史", "文化", "人文", "博物", "古迹", "古镇")):
            add("博物馆")
        elif any(token in lowered for token in ("自然", "风景", "户外", "亲子", "公园")):
            add("公园")

    add(CATEGORY_FALLBACK_QUERIES.get(category, ""))
    return variants or ["地点"]


async def _search_private_places(
    env: Any, *, city: str, query: str, category: str, limit: int,
) -> list[dict[str, Any]]:
    """Query the compact OSM/GeoNames service without leaking its token."""

    # The public origin is safe to keep as a default; the Bearer token remains
    # server-side and mandatory.  This also keeps production functional when a
    # Makers project has reached its environment-variable key limit.
    base_url = _env_value(env, "PLACE_API_BASE_URL", DEFAULT_PLACE_API_BASE_URL)
    token = _env_value(env, "PLACE_API_TOKEN")
    if not base_url:
        return []
    try:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/v1/places/search",
                headers=headers,
                json={"city": city, "query": query, "category": category, "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
        raw = payload.get("places", payload) if isinstance(payload, dict) else payload
        return [_normalize_place(item, "private_place_db") for item in raw if isinstance(item, dict)][:limit]
    except Exception:
        return []


async def _search_tencent_places(
    env: Any, *, city: str, query: str, limit: int,
) -> list[dict[str, Any]]:
    key = _env_value(env, "TENCENT_MAP_SERVER_KEY")
    if not key:
        return []
    params = {"keyword": query, "key": key, "page_size": limit}
    if city:
        params["boundary"] = f"region({city},0)"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                "https://apis.map.qq.com/ws/place/v1/search?" + urlencode(params),
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("status") != 0:
            return []
        return [_normalize_place(item, "tencent_map") for item in payload.get("data", [])[:limit]]
    except Exception:
        return []


async def search_places(env: Any, *, city: str, query: str, category: str, limit: int) -> list[dict[str, Any]]:
    """Use fresh Tencent commercial POIs and the compact private stable-place index."""

    limit = max(1, min(int(limit), 20))
    landmark = next((item for item in LANDMARK_AREA_PLACES if item in str(query or "")), "")
    if landmark and (not city or city == LANDMARK_CITIES.get(landmark)):
        # Famous landmark geometry is stable. A compact curated neighborhood
        # prevents broad category fallback from mixing remote city-wide POIs
        # into a single-day route.
        return [dict(place) for place in LANDMARK_AREA_PLACES[landmark][:limit]]
    dynamic_categories = {"restaurant", "hotel", "shopping"}
    merged: list[dict[str, Any]] = []
    for variant in _place_query_variants(city, query, category):
        remaining = limit - len(merged)
        if remaining <= 0:
            break
        if category in dynamic_categories:
            tencent = await _search_tencent_places(
                env, city=city, query=variant, limit=remaining,
            )
            # Commercial POIs change quickly and are intentionally excluded
            # from the stable private index. Never fill a Tencent miss with
            # stale Overture restaurant/hotel/shop rows.
            merged = _merge_places(merged, tencent, limit=limit)
        else:
            private = await _search_private_places(
                env, city=city, query=variant, category=category, limit=remaining,
            )
            tencent = [] if len(private) >= remaining else await _search_tencent_places(
                env, city=city, query=variant, limit=remaining,
            )
            merged = _merge_places(merged, private, tencent, limit=limit)
    if not merged and category in {"attraction", "other"} and city in CITY_FALLBACK_PLACES:
        # Stable landmark geometry keeps itinerary creation available when the
        # private index has no broad-category hit and the live map quota is
        # temporarily unavailable. Never use this for changing commercial POIs.
        return [dict(place) for place in CITY_FALLBACK_PLACES[city][:limit]]
    return merged[:limit]


async def enrich_itinerary_places(
    env: Any,
    analysis: dict[str, Any],
    profile: dict[str, Any],
    primary_places: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add meal POIs to an attraction request so a day can form a useful route."""

    if not analysis.get("wants_itinerary"):
        return primary_places
    city = str(analysis.get("city") or "")
    if not city:
        return primary_places
    days = max(1, min(int(analysis.get("days") or 1), 7))
    food_tokens = _preference_tokens(profile, "food_preferences")
    dining_query = f"{food_tokens[0]}餐厅" if food_tokens else "餐厅"
    dining = await search_places(
        env,
        city=city,
        query=dining_query,
        category="restaurant",
        limit=min(days * 2, 6),
    )
    landmark = next(
        (item for item in LANDMARK_AREA_PLACES if item in str(analysis.get("query") or "")),
        "",
    )
    if landmark and primary_places:
        anchor = primary_places[0]
        dining = [
            place for place in dining
            if place.get("lat") and place.get("lng") and _haversine(anchor, place) <= 3000
        ]
    # Keep room for meals under the runtime's compact 20-POI context budget.
    primary_limit = min(len(primary_places), max(days * 2, 4), 14)
    return _merge_places(primary_places[:primary_limit], dining, limit=20)


def places_prompt(analysis: dict[str, Any], places: list[dict[str, Any]]) -> str:
    if not places:
        return "地点专库和腾讯地图均未返回可验证地点；明确告诉用户暂时无法给出可靠 POI，不要编造店名、评分或地址。"
    return (
        "地点检索结果（按返回顺序优先，禁止编造列表外的地址、评分和坐标）：\n"
        + json.dumps({"request": analysis, "places": places}, ensure_ascii=False)
    )


def itinerary_prompt(itinerary: dict[str, Any] | None) -> str:
    """Give the writer the exact calendar facts without prescribing its prose."""

    if not itinerary or not itinerary.get("schedules"):
        return ""
    schedules = []
    for item in itinerary.get("schedules", []):
        if not isinstance(item, dict):
            continue
        try:
            when = datetime.fromtimestamp(
                float(item.get("start_time") or 0),
                SHANGHAI_TZ,
            ).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OSError):
            when = "待定"
        schedules.append({
            "time": when,
            "title": str(item.get("title") or "未命名安排"),
            "location": str(item.get("location") or item.get("title") or ""),
        })
    return (
        "\n\n已成功写入日历的权威行程（必须在回答中自然、完整地包含这些日期、时间和地点；"
        "表达方式、游玩理由、节奏建议、交通、美食和提醒均可自由发挥。可以提出额外备选，"
        "但要明确它们尚未写入日历，不能把备选混入下列正式行程）：\n"
        + json.dumps({
            "city": itinerary.get("city"),
            "start_date": itinerary.get("start_date"),
            "days": itinerary.get("days"),
            "schedules": schedules,
        }, ensure_ascii=False)
    )


def contains_internal_tool_protocol(content: str) -> bool:
    """Detect provider tool-call markup that must never reach the browser."""

    return "<tool_call" in str(content or "").casefold()


def deterministic_places_answer(
    analysis: dict[str, Any],
    places: list[dict[str, Any]],
    itinerary: dict[str, Any] | None = None,
) -> str:
    """Render recommendations from the same structured data used by the UI."""

    city = str(analysis.get("city") or "目的地")
    category = str(analysis.get("category") or "other")
    if itinerary and itinerary.get("schedules"):
        schedules = [
            item for item in itinerary.get("schedules", [])
            if isinstance(item, dict)
        ]
        start_date = str(itinerary.get("start_date") or "").strip()
        days = max(1, int(itinerary.get("days") or 1))
        heading = f"## {city}{days}日行程"
        if start_date:
            heading += f"（{start_date}）"
        lines = [
            heading,
            "",
            "以下安排已写入右侧日历，地图会按所选日期实时显示同一组地点：",
            "",
            "| 时间 | 安排 | 地点 |",
            "|---|---|---|",
        ]
        for schedule in schedules:
            try:
                when = datetime.fromtimestamp(
                    float(schedule.get("start_time") or 0),
                    SHANGHAI_TZ,
                )
                time_text = when.strftime("%H:%M") if days == 1 else when.strftime("%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                time_text = "待定"
            title = str(schedule.get("title") or "未命名安排").replace("|", "｜")
            location = str(schedule.get("location") or title).replace("|", "｜")
            lines.append(f"| {time_text} | **{title}** | {location} |")
        lines.extend([
            "",
            f"共 {len(schedules)} 项；切换日历日期时，路线地图会立即改为当天日程。",
        ])
        return "\n".join(lines)

    requested_count = max(1, min(int(analysis.get("count") or 6), 12))
    if category == "restaurant":
        candidates = [item for item in places if item.get("category") == "restaurant"]
    elif category == "attraction":
        candidates = [item for item in places if item.get("category") != "restaurant"]
    else:
        candidates = list(places)
    selected = candidates[:requested_count] or list(places[:requested_count])
    if not selected:
        return f"暂时没有检索到可验证的{city}地点，因此这次不编造推荐。"

    noun = "餐馆" if category == "restaurant" else "地点"
    lines = [f"## {city}{noun}推荐", "", "以下结果来自地点专库或腾讯地图：", ""]
    for index, place in enumerate(selected, start=1):
        details = []
        address = str(place.get("address") or "").strip()
        telephone = str(place.get("tel") or place.get("phone") or "").strip()
        rating = float(place.get("rating") or 0)
        if address:
            details.append(address)
        if rating:
            details.append(f"评分 {rating:g}")
        if telephone:
            details.append(f"电话 {telephone}")
        suffix = f" — {'；'.join(details)}" if details else ""
        lines.append(f"{index}. **{str(place.get('name') or '未命名地点')}**{suffix}")

    return "\n".join(lines)


def ensure_itinerary_in_answer(
    content: str,
    analysis: dict[str, Any],
    places: list[dict[str, Any]],
    itinerary: dict[str, Any] | None,
) -> str:
    """Preserve model-written prose and append facts only when it missed them."""

    answer = str(content or "").strip()
    if not itinerary or not itinerary.get("schedules"):
        return answer
    if not answer or contains_internal_tool_protocol(answer):
        return deterministic_places_answer(analysis, places, itinerary)

    grounded = ground_itinerary_answer_date(answer, itinerary)
    schedules = [
        item for item in itinerary.get("schedules", [])
        if isinstance(item, dict)
    ]
    required_tokens = [str(itinerary.get("start_date") or "").strip()]
    for schedule in schedules:
        required_tokens.append(str(schedule.get("title") or "").strip())
        try:
            required_tokens.append(datetime.fromtimestamp(
                float(schedule.get("start_time") or 0),
                SHANGHAI_TZ,
            ).strftime("%H:%M"))
        except (TypeError, ValueError, OSError):
            pass
    has_calendar_confirmation = "日历" in grounded and any(
        word in grounded for word in ("写入", "同步", "更新", "安排")
    )
    if has_calendar_confirmation and all(
        not token or token in grounded for token in required_tokens
    ):
        return grounded

    # The model remains the primary author. This compact block is only a data
    # integrity guard when it omitted one of the persisted calendar facts.
    city = str(itinerary.get("city") or analysis.get("city") or "目的地")
    start_date = str(itinerary.get("start_date") or "").strip()
    lines = [
        grounded,
        "",
        f"### 已同步到日历的{city}行程{f'（{start_date}）' if start_date else ''}",
        "",
        "| 时间 | 安排 | 地点 |",
        "|---|---|---|",
    ]
    for schedule in schedules:
        try:
            time_text = datetime.fromtimestamp(
                float(schedule.get("start_time") or 0),
                SHANGHAI_TZ,
            ).strftime("%H:%M")
        except (TypeError, ValueError, OSError):
            time_text = "待定"
        title = str(schedule.get("title") or "未命名安排").replace("|", "｜")
        location = str(schedule.get("location") or title).replace("|", "｜")
        lines.append(f"| {time_text} | **{title}** | {location} |")
    lines.extend(["", "这组安排已经写入右侧日历；地图会跟随所选日期显示。"])
    return "\n".join(lines)


def ground_itinerary_answer_date(content: str, itinerary: dict[str, Any] | None) -> str:
    """Keep prose dates consistent with the itinerary already persisted to the UI."""

    if not itinerary:
        return content
    start_date = str(itinerary.get("start_date") or "").strip()
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", start_date):
        return content

    date_pattern = re.compile(r"20\d{2}-\d{2}-\d{2}")
    days = max(1, int(itinerary.get("days") or 1))
    if days == 1:
        # A one-day plan has exactly one valid calendar date.  Replacing all
        # ISO dates prevents the model from contradicting the travel_plan event
        # in its intro, heading, and closing confirmation.
        return date_pattern.sub(start_date, content)
    if start_date in content:
        return content
    return date_pattern.sub(start_date, content, count=1)


def _date_from_analysis(analysis: dict[str, Any]) -> datetime:
    raw = str(analysis.get("start_date") or "")
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
        return parsed
    except ValueError:
        tomorrow = _now_shanghai() + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)


def _personalized_place_order(
    places: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    interest_tokens = _preference_tokens(profile, "interests", "food_preferences")

    def score(place: dict[str, Any]) -> tuple[float, float]:
        text = f"{place.get('name', '')} {place.get('address', '')} {place.get('category', '')}".casefold()
        preference_score = sum(2.0 for token in interest_tokens if token in text)
        return preference_score + float(place.get("rating") or 0) / 5, float(place.get("rating") or 0)

    return sorted(places, key=score, reverse=True)


def _nearest_to(anchor: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [item for item in candidates if item.get("lat") and item.get("lng")]
    if not valid or not anchor.get("lat") or not anchor.get("lng"):
        return candidates[0] if candidates else None
    return min(valid, key=lambda item: _haversine(anchor, item))


def build_itinerary(
    user_id: str,
    analysis: dict[str, Any],
    places: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Build an editable, deterministic itinerary from verified POIs."""

    city = str(analysis.get("city") or "目的地")
    days = max(1, min(int(analysis.get("days") or 1), 7))
    start = _date_from_analysis(analysis)
    schedules: list[dict[str, Any]] = []
    ordered = _personalized_place_order(places, profile)
    dining = [item for item in ordered if item.get("category") == "restaurant"]
    attractions = [item for item in ordered if item.get("category") != "restaurant"]
    pace = str(_profile_value(profile, "pace", "适中"))
    attractions_per_day = 2 if any(word in pace for word in ("慢", "休闲", "轻松")) else 3
    start_hour = 10 if any(word in pace for word in ("慢", "休闲", "轻松")) else 9
    attraction_index = 0
    dining_pool = list(dining)

    for day_index in range(days):
        day_attractions = attractions[attraction_index: attraction_index + attractions_per_day]
        attraction_index += len(day_attractions)
        if not day_attractions and not dining_pool:
            break

        day_items: list[tuple[dict[str, Any], tuple[int, int]]] = []
        if day_attractions:
            day_items.append((day_attractions[0], (start_hour, 0)))
        if dining_pool:
            anchor = day_attractions[0] if day_attractions else dining_pool[0]
            lunch = _nearest_to(anchor, dining_pool)
            if lunch:
                dining_pool.remove(lunch)
                day_items.append((lunch, (12, 30)))
        if len(day_attractions) >= 2:
            day_items.append((day_attractions[1], (14, 30)))
        if len(day_attractions) >= 3:
            day_items.append((day_attractions[2], (16, 30)))
        if dining_pool:
            anchor = day_attractions[-1] if day_attractions else day_items[-1][0]
            dinner = _nearest_to(anchor, dining_pool)
            if dinner:
                dining_pool.remove(dinner)
                day_items.append((dinner, (18, 30)))

        for place, slot in day_items:
            when = (start + timedelta(days=day_index)).replace(hour=slot[0], minute=slot[1])
            schedule_id = f"travel-{uuid4().hex[:16]}"
            is_dining = place.get("category") == "restaurant"
            schedules.append({
                "id": schedule_id,
                "session_id": _safe_user_id(user_id),
                "title": place["name"],
                "category": "dining" if is_dining else "travel",
                "start_time": int(when.timestamp()),
                "duration_minutes": 90 if is_dining else 120,
                "duration_days": 0,
                "location": place["address"] or place["name"],
                "description": f"{city}个性化行程 · 数据来源：{place['source']}",
                "markdown_content": "",
                "extra": {
                    "city": city,
                    "search_query": place["name"],
                    "place_id": place["id"],
                    "place_source": place["source"],
                    "place_type": "restaurant" if is_dining else "scenic",
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "tentative_date": not bool(analysis.get("start_date")),
                },
                "done": False,
                "created_at": datetime.now(SHANGHAI_TZ).timestamp(),
                "updated_at": datetime.now(SHANGHAI_TZ).timestamp(),
            })
    return {
        "schema_version": 1,
        "id": f"plan-{uuid4().hex[:16]}",
        "city": city,
        "start_date": start.date().isoformat(),
        "days": days,
        "tentative_date": not bool(analysis.get("start_date")),
        "profile": profile,
        "schedules": schedules,
    }


def _schedule_signature(schedule: dict[str, Any]) -> tuple[str, str, str]:
    extra = schedule.get("extra") if isinstance(schedule.get("extra"), dict) else {}
    city = str(extra.get("city") or "").strip().casefold()
    place = str(extra.get("place_id") or schedule.get("title") or "").strip().casefold()
    try:
        day = datetime.fromtimestamp(float(schedule.get("start_time") or 0), SHANGHAI_TZ).date().isoformat()
    except (TypeError, ValueError, OSError):
        day = ""
    return city, place, day


async def save_itinerary(
    store,
    user_id: str,
    itinerary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Persist an itinerary and return the schedules confirmed by a read-back.

    The returned list is the only payload that callers may announce as written.
    Existing schedules with the same place/day signature are reused so retries
    stay idempotent and the UI receives the same records that the store holds.
    """

    existing = await list_schedules(store, user_id)
    by_id = {str(item.get("id")): item for item in existing}
    by_signature = {_schedule_signature(item): item for item in existing}
    requested_signatures: list[tuple[str, str, str]] = []
    for schedule in itinerary.get("schedules", []):
        if not isinstance(schedule, dict):
            continue
        signature = _schedule_signature(schedule)
        requested_signatures.append(signature)
        if signature in by_signature:
            continue
        by_id[str(schedule["id"])] = schedule
        by_signature[signature] = schedule
    await _store_put(
        store,
        _namespace(user_id, "schedules"),
        "schedule-index",
        {"schema_version": 1, "items": list(by_id.values())},
    )
    await _store_put(store, _namespace(user_id, "plans"), str(itinerary["id"]), itinerary)

    persisted = await list_schedules(store, user_id)
    persisted_by_signature = {_schedule_signature(item): item for item in persisted}
    confirmed = [
        persisted_by_signature[signature]
        for signature in requested_signatures
        if signature in persisted_by_signature
    ]
    if requested_signatures and len(confirmed) != len(requested_signatures):
        raise RuntimeError("行程写入未完成，请稍后重试")
    return confirmed


async def list_schedules(store, user_id: str) -> list[dict[str, Any]]:
    index = await _store_get(store, _namespace(user_id, "schedules"), "schedule-index")
    items = index.get("items", []) if isinstance(index, dict) else []
    result = [item for item in items if isinstance(item, dict)]
    return sorted(result, key=lambda item: (float(item.get("start_time") or 0), str(item.get("id") or "")))


async def upsert_schedule(store, user_id: str, schedule: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(SHANGHAI_TZ).timestamp()
    schedule_id = str(schedule.get("id") or f"schedule-{uuid4().hex[:16]}")
    schedules = await list_schedules(store, user_id)
    existing = next((item for item in schedules if str(item.get("id")) == schedule_id), None)
    normalized = {
        "id": schedule_id,
        "session_id": _safe_user_id(user_id),
        "title": str(schedule.get("title") or "未命名日程")[:120],
        "category": str(schedule.get("category") or "other"),
        "start_time": float(schedule.get("start_time") or 0),
        "duration_minutes": max(0, int(schedule.get("duration_minutes") or 0)),
        "duration_days": max(0, int(schedule.get("duration_days") or 0)),
        "location": str(schedule.get("location") or "")[:300],
        "description": str(schedule.get("description") or "")[:2000],
        "markdown_content": str(schedule.get("markdown_content") or "")[:10000],
        "extra": schedule.get("extra") if isinstance(schedule.get("extra"), dict) else {},
        "done": bool(schedule.get("done", False)),
        "created_at": float((existing or {}).get("created_at") or schedule.get("created_at") or now),
        "updated_at": now,
    }
    by_id = {str(item.get("id")): item for item in schedules}
    by_id[schedule_id] = normalized
    await _store_put(
        store,
        _namespace(user_id, "schedules"),
        "schedule-index",
        {"schema_version": 1, "items": list(by_id.values())},
    )
    return normalized


async def delete_schedule(store, user_id: str, schedule_id: str) -> None:
    schedules = await list_schedules(store, user_id)
    remaining = [item for item in schedules if str(item.get("id")) != schedule_id]
    await _store_put(
        store,
        _namespace(user_id, "schedules"),
        "schedule-index",
        {"schema_version": 1, "items": remaining},
    )


def _haversine(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _route_alternative(place: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(place.get("id") or ""),
        "title": str(place.get("title") or place.get("name") or "地点"),
        "address": str(place.get("address") or ""),
        "tel": str(place.get("tel") or place.get("phone") or ""),
        "lat": float(place.get("lat") or 0),
        "lng": float(place.get("lng") or 0),
    }


def decode_tencent_polyline(values: Any) -> list[float]:
    """Decode Tencent's forward-difference route polyline into lat/lng pairs."""

    if not isinstance(values, list) or len(values) < 2:
        return []
    try:
        raw = [float(value) for value in values]
    except (TypeError, ValueError):
        return []
    first_lat = raw[0] / 1_000_000 if abs(raw[0]) > 90 else raw[0]
    first_lng = raw[1] / 1_000_000 if abs(raw[1]) > 180 else raw[1]
    decoded = [first_lat, first_lng]
    previous_lat, previous_lng = first_lat, first_lng
    for index in range(2, len(raw) - 1, 2):
        previous_lat += raw[index] / 1_000_000
        previous_lng += raw[index + 1] / 1_000_000
        if -90 <= previous_lat <= 90 and -180 <= previous_lng <= 180:
            decoded.extend((previous_lat, previous_lng))
    return decoded


async def plan_daily_route(env: Any, city: str, locations: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve schedule locations and return a road route or a clear geometric fallback."""

    resolved: list[dict[str, Any]] = []
    for item in locations[:12]:
        lat, lng = float(item.get("lat") or 0), float(item.get("lng") or 0)
        raw_alternatives = item.get("alternatives") if isinstance(item.get("alternatives"), list) else []
        alternatives = [_route_alternative(place) for place in raw_alternatives if isinstance(place, dict)]
        if not lat or not lng:
            matches = await search_places(
                env,
                city=city,
                query=str(item.get("keyword") or item.get("name") or ""),
                category="other",
                limit=3,
            )
            if matches:
                first = matches[0]
                alternatives = [_route_alternative(place) for place in matches]
                lat, lng = first["lat"], first["lng"]
                item = {**item, "name": first["name"], "address": first["address"]}
        if lat and lng:
            resolved.append({
                "id": str(item.get("id") or uuid4().hex),
                "keyword": str(item.get("keyword") or item.get("name") or ""),
                "name": str(item.get("name") or item.get("keyword") or "地点"),
                "address": str(item.get("address") or ""),
                "lat": lat,
                "lng": lng,
                "alternatives": alternatives,
            })
    if len(resolved) < 2:
        return {"error": "有效地点不足，无法连接成路线", "city": city, "locations": resolved}

    key = _env_value(env, "TENCENT_MAP_SERVER_KEY")
    route: dict[str, Any] = {}
    if key:
        params = {
            "from": f"{resolved[0]['lat']},{resolved[0]['lng']}",
            "to": f"{resolved[-1]['lat']},{resolved[-1]['lng']}",
            "key": key,
        }
        if len(resolved) > 2:
            params["waypoints"] = ";".join(f"{item['lat']},{item['lng']}" for item in resolved[1:-1])
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://apis.map.qq.com/ws/direction/v1/driving/?" + urlencode(params),
                )
                response.raise_for_status()
                payload = response.json()
            routes = payload.get("result", {}).get("routes", []) if payload.get("status") == 0 else []
            route = routes[0] if routes else {}
        except Exception:
            route = {}

    distances = [_haversine(resolved[i], resolved[i + 1]) for i in range(len(resolved) - 1)]
    total_distance = float(route.get("distance") or sum(distances))
    total_duration = float(route.get("duration") or total_distance / 8.33)
    polyline = (
        decode_tencent_polyline(route.get("polyline"))
        if route.get("polyline")
        else [coord for item in resolved for coord in (item["lat"], item["lng"])]
    )
    if len(polyline) < 4:
        polyline = [coord for item in resolved for coord in (item["lat"], item["lng"])]
    segments = [
        {
            "from": resolved[i]["name"],
            "to": resolved[i + 1]["name"],
            "distance": distances[i],
            "duration": distances[i] / 8.33,
            "toll": 0,
        }
        for i in range(len(resolved) - 1)
    ]
    return {
        "city": city,
        "locations": resolved,
        "segments": segments,
        "polyline": polyline,
        "total_distance": total_distance,
        "total_duration": total_duration,
        "total_distance_km": round(total_distance / 1000, 1),
        "total_duration_hours": round(total_duration / 3600, 1),
        "total_toll": float(route.get("toll") or 0),
        "cost_estimate": {
            "self_driving": round(total_distance / 1000 * 0.7 + float(route.get("toll") or 0)),
            "taxi": round(total_distance / 1000 * 3),
            "toll": float(route.get("toll") or 0),
        },
        "weather": {},
        "route_source": "tencent_map" if route else "geometric_fallback",
    }
