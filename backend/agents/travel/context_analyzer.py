"""Travel context analyzer — infer constraints from conversation, ask for missing info."""
from __future__ import annotations

import json as _json
from dataclasses import dataclass, field

import httpx

from config import settings


@dataclass
class TravelContext:
    destination: str = ""
    departure: str = ""
    days: int = 1
    budget: str = ""  # "budget" | "moderate" | "luxury"
    style: str = ""  # "文化深度" | "休闲度假" | "亲子家庭" | "美食探店" | "户外探险" | ""
    interests: list[str] = field(default_factory=list)
    participants: str = ""  # "独自" | "情侣" | "亲子" | "朋友" | "商务"
    start_date: str = ""
    is_complete: bool = False
    missing: list[str] = field(default_factory=list)  # what to ask the user


async def analyze(message: str, history: list[str] | None = None) -> TravelContext:
    """Infer travel intent and missing info from user message using DeepSeek."""
    history_text = "\n".join((history or [])[-6:])
    
    prompt = (
        "分析用户的旅行意图，提取已知信息并列出还缺什么。返回 JSON：\n"
        '{\n  "destination": "城市名",\n  "departure": "出发城市或空",'
        '\n  "days": 天数, "budget": "budget/moderate/luxury或空",\n'
        '  "style": "文化深度/休闲度假/亲子家庭/美食探店/户外探险或空",\n'
        '  "interests": ["偏好1","偏好2"], "participants": "独自/情侣/亲子/朋友/商务或空",\n'
        '  "start_date": "YYYY-MM-DD或空",\n'
        '  "is_complete": true/false,\n'
        '  "missing": ["需要追问的信息1", "需要追问的信息2"]\n}\n\n'
        "is_complete=true 当 destination+days+style 都有值时，否则 false。\n"
        "missing 列出用户还没说清楚的关键信息（用自然中文问题）。\n"
    )

    user_content = f"用户消息：{message}"
    if history_text:
        user_content += f"\n\n对话历史：{history_text}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 400,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            raw = raw.strip().strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            data = _json.loads(raw)

        return TravelContext(
            destination=data.get("destination", ""),
            departure=data.get("departure", ""),
            days=max(1, int(data.get("days", 1) or 1)),
            budget=data.get("budget", ""),
            style=data.get("style", ""),
            interests=list(data.get("interests", [])),
            participants=data.get("participants", ""),
            start_date=data.get("start_date", ""),
            is_complete=bool(data.get("is_complete", False)),
            missing=list(data.get("missing", [])),
        )
    except Exception:
        return TravelContext(missing=["请问你想去哪里旅行？大概玩几天？"])
