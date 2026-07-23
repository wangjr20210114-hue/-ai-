"""Generate optional follow-up chips without constraining the primary answer."""

from __future__ import annotations

import json
import re
from typing import Any


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def parse_followups(content: Any) -> list[str]:
    text = _text(content).strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for value in raw:
        question = re.sub(r"\s+", " ", str(value or "")).strip()[:60]
        if question and question not in result:
            result.append(question)
    return result[:3]


async def generate_followups(
    model, user_message: str, answer: str = "", *, plan_context: str = "",
) -> list[str]:
    """Return useful next questions and allow planning beside answer synthesis."""
    grounding = answer.strip() or plan_context.strip()
    if len(user_message.strip()) + len(grounding) < 20:
        return []
    response = await model.ainvoke([
        {
            "role": "system",
            "content": (
                "你只生成对话界面的‘猜你想问’，不续写或编排回答。结合用户原问题和回答，"
                "给出2到3个自然、有信息增量、用户可能真的会点的简短中文问题。"
                "不要重复原问题，不要写‘还有什么可以帮你’。如果不适合追问，返回[]。"
                "只返回JSON字符串数组。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"原问题：{user_message[:1200]}\n\n"
                + (f"回答：{answer[:6000]}" if answer.strip() else f"已识别的任务方向：{plan_context[:2400]}")
            ),
        },
    ])
    return parse_followups(getattr(response, "content", response))
