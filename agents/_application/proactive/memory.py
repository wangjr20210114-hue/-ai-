"""Application inference for the bounded proactive reminder window."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..intelligence.service import confirmed_memory_context, safe_non_sensitive_text
from ..i18n import language_instruction, normalize_language, text


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
    response_language: object = "zh-CN",
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
    language = normalize_language(response_language)
    existing = "\n".join(f"- {item[:180]}" for item in existing_reminders[:8]) or "[]"
    prompt = [
        SystemMessage(content=text(
            "model.proactive.memory_system", language,
            language_instruction=language_instruction(language),
        )),
        HumanMessage(content=text(
            "model.proactive.memory_context", language,
            now=now, memory_context=memory_context,
            location=json.dumps(location, ensure_ascii=False, default=str),
            existing=existing,
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
