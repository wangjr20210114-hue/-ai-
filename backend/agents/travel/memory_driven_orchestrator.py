"""Memory-driven travel orchestrator — preferences from memory, not prompts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TripRequest:
    destination: str = ""
    departure: str = ""
    days: int = 1
    start_date: str = ""  # YYYY-MM-DD
    style: str = ""  # inferred from memory
    budget_level: str = ""
    interests: list[str] = field(default_factory=list)
    participants: str = ""


async def infer_from_memories() -> dict[str, Any]:
    """Read user memories to infer travel preferences."""
    try:
        from database.repositories.memory_repo import list_memories, cluster_and_merge

        # Cluster and merge similar memories first
        await cluster_and_merge()

        memories = await list_memories()
        if not memories:
            return {}

        prefs: dict[str, Any] = {}
        key_map = {
            "旅行偏好": "style",
            "饮食偏好": "food_preference",
            "户外偏好": "outdoor_preference",
            "住宿偏好": "accommodation",
            "出行方式": "transport",
        }

        for m in memories:
            k = str(m.get("memory_key", ""))
            v = m.get("value_json")
            if k in key_map and v:
                prefs[key_map[k]] = str(v)

        # Infer style from compound preferences
        if prefs.get("style"):
            pass  # already clustered
        elif prefs.get("outdoor_preference"):
            prefs["style"] = "户外自然"
        elif "美食" in str(prefs.get("food_preference", "")):
            prefs["style"] = "美食探店"

        # Infer budget from accommodation
        acc = str(prefs.get("accommodation", "")).lower()
        if "经济" in acc or "便宜" in acc or "省钱" in acc:
            prefs["budget_level"] = "budget"
        elif "奢侈" in acc or "高端" in acc or "五星" in acc:
            prefs["budget_level"] = "luxury"
        else:
            prefs["budget_level"] = "moderate"

        return prefs
    except Exception:
        return {}


async def handle_travel(message: str, history: list[str] | None = None) -> dict[str, Any]:
    """Handle travel request: memories → extract essentials → ask only if needed."""
    prefs = await infer_from_memories()

    # Extract MUST-HAVE info from message via minimal rules
    must_ask: list[str] = []

    # Destination detection (simple keyword)
    destination = ""
    for city in ["北京", "上海", "杭州", "成都", "广州", "深圳", "南京", "西安", "重庆",
                 "武汉", "长沙", "厦门", "青岛", "大连", "三亚", "昆明", "丽江", "桂林"]:
        if city in message:
            destination = city
            break

    # Days detection
    import re
    days_match = re.search(r'(\d+)\s*天', message)
    days = int(days_match.group(1)) if days_match else 1

    # Date detection
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', message)
    start_date = date_match.group(1) if date_match else ""

    if not destination:
        must_ask.append("你想去哪里旅行？")
    if not start_date:
        must_ask.append("什么时候出发？我需要写到日程里")
    if days < 1:
        must_ask.append("大概玩几天？")

    # If missing essentials, ask
    if must_ask:
        msg = "好的，我来帮你规划旅行！"
        if prefs.get("style"):
            msg += f" 根据之前的了解，你偏好{prefs['style']}风格。"
        msg += "\n\n" + "\n".join(f"• {q}" for q in must_ask)
        return {
            "action": "ask",
            "reply": msg,
            "preferences": prefs,
        }

    # All essentials known → plan trip
    req = TripRequest(
        destination=destination,
        start_date=start_date,
        days=days,
        style=prefs.get("style", ""),
        budget_level=prefs.get("budget_level", "moderate"),
        interests=prefs.get("style", "").split("；") if prefs.get("style") else [],
    )

    # Use existing TravelAgent to plan
    try:
        from agents.travel.place_repository import PlaceRepository
        from agents.travel.agent import TravelAgent

        agent = TravelAgent(PlaceRepository())
        plan = await agent.plan_trip_dict({
            "destination": req.destination,
            "departure": req.departure,
            "days": req.days,
            "start_date": req.start_date,
            "travel_style": req.style,
            "budget": req.budget_level,
        })
        plan["action"] = "plan"
        plan["preferences"] = prefs
        return plan
    except Exception as e:
        return {
            "action": "error",
            "reply": f"规划行程时出错了：{e}",
            "preferences": prefs,
        }
