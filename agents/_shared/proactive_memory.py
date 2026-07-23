"""Memory-first reminder inference for the bounded proactive window."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .intelligence import confirmed_memory_context, safe_non_sensitive_text


def _message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        ).strip()
    return ""


def _json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except Exception:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}


async def infer_memory_reminder(
    model: Any,
    intelligence_state: dict[str, Any],
    *,
    location_context: dict[str, Any] | None,
    existing_reminders: list[str],
    now: int,
    timeout_seconds: float = 6,
) -> dict[str, Any] | None:
    """Return at most one safe reminder, or None when memory is insufficient."""
    memory_context = confirmed_memory_context(intelligence_state, limit=12)
    if not memory_context:
        return None
    location = {
        key: value
        for key, value in (location_context or {}).items()
        if key in {
            "city", "district", "weather", "temperature", "wind_direction",
            "wind_power", "humidity", "precipitation", "observed_at",
        }
        and value not in (None, "")
    }
    existing = "\n".join(f"- {item[:180]}" for item in existing_reminders[:8]) or "（当前为空）"
    prompt = [
        SystemMessage(content=(
            "你是 Floris 的主动关怀判断器。仅依据给出的非敏感用户记忆，并可结合粗粒度城市天气，"
            "判断现在是否有一条真正有帮助、自然且不过度打扰的提醒。记忆必须是主要依据；"
            "不得猜测未提供的事实，不得提及“记忆、数据库、模型、后台、画像”，不得输出敏感信息。"
            "若依据不足、只是泛泛问候、或与当前窗口重复，should_remind 必须为 false。"
            "只输出严格 JSON："
            "{\"should_remind\":true或false,\"title\":\"不超过18字\","
            "\"detail\":\"一条自然短句，不超过70字\",\"action\":\"用户可直接继续询问的建议，不超过80字\","
            "\"priority\":\"normal或low\"}。"
        )),
        HumanMessage(content=(
            f"当前 Unix 时间：{now}\n"
            f"用户的安全记忆：\n{memory_context}\n"
            f"粗粒度位置与天气：{json.dumps(location, ensure_ascii=False, default=str)}\n"
            f"当前窗口已有提醒：\n{existing}"
        )),
    ]
    try:
        response = await asyncio.wait_for(
            model.ainvoke(prompt),
            timeout=max(1.0, min(10.0, float(timeout_seconds))),
        )
    except Exception:
        return None
    payload = _json_object(_message_text(response))
    if payload.get("should_remind") is not True:
        return None
    title = str(payload.get("title") or "").strip()[:18]
    detail = str(payload.get("detail") or "").strip()[:70]
    action = str(payload.get("action") or "").strip()[:80]
    if not all(
        safe_non_sensitive_text(value, max_chars=limit)
        for value, limit in ((title, 18), (detail, 70), (action, 80))
    ):
        return None
    identity = hashlib.sha256(f"{title}\n{detail}".encode("utf-8")).hexdigest()[:16]
    return {
        "type": "memory_context_reminder",
        "source": "memory_window",
        "window_policy": "memory_refresh",
        "dedup_key": f"memory_context:{now // 600}:{identity}",
        "priority": str(payload.get("priority") or "normal") if payload.get("priority") in {"normal", "low"} else "normal",
        "subject_ids": [],
        "title": title,
        "detail": detail,
        "action": action,
        "evidence": {
            "basis": "safe_memory",
            "location_used": bool(location),
        },
        "occurred_at": now,
        "expires_at": now + 2 * 3600,
    }
