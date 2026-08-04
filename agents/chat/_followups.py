"""Generate optional follow-up chips without constraining the primary answer."""

from __future__ import annotations

import json
import re
from typing import Any

from .._application.i18n import normalize_language, text


_FOLLOWUP_RESULT_CAPABILITIES = (
    "needs_web_search",
    "needs_images",
    "needs_places",
    "needs_current_location",
    "needs_nearby_places",
    "needs_route",
    "needs_map_action",
    "needs_calendar_context",
    "needs_image_generation",
    "needs_papers",
)


def should_generate_followups(
    capability_plan: dict[str, Any],
    *,
    blocked_skill: str = "",
) -> bool:
    """Select useful result turns from semantic state, never message keywords.

    The planner's explicit judgment remains authoritative for ordinary chat.
    Result-producing Skills get a safe fallback because their natural next
    steps are part of the product experience and older/partial planner outputs
    may omit the optional flag. Clarification and blocked turns never receive
    competing suggestions.
    """
    if blocked_skill or capability_plan.get("needs_clarification"):
        return False
    return bool(
        capability_plan.get("needs_followups")
        or any(capability_plan.get(key) for key in _FOLLOWUP_RESULT_CAPABILITIES)
    )


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
    model,
    user_message: str,
    answer: str = "",
    *,
    response_language: str = "zh-CN",
) -> list[str]:
    """Return useful next questions grounded in the completed public answer."""
    grounding = answer.strip()
    if not grounding or len(user_message.strip()) + len(grounding) < 20:
        return []
    language = normalize_language(response_language)
    language_copy = text("model.followups.language", language)
    response = await model.ainvoke([
        {
            "role": "system",
            "content": text(
                "model.followups.system",
                language,
                language_instruction=language_copy,
            ),
        },
        {
            "role": "user",
            "content": text(
                "model.followups.user_with_answer",
                language,
                question=user_message[:1200],
                answer=answer[:6000],
            ),
        },
    ])
    return parse_followups(getattr(response, "content", response))
