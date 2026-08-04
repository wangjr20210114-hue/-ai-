"""Application-level post-turn opportunity detection for the proactive Agent.

The detector does not answer the user and never performs a side effect.  It
selects at most one useful next service that can be delivered through the
existing persistent proactive inbox or the next empty conversation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from ..intelligence.service import safe_non_sensitive_text
from ..i18n import language_instruction, normalize_language, text


OPPORTUNITY_TYPES = {
    "search_update",
    "writing_improvement",
    "translation_review",
    "image_iteration",
    "document_next_step",
    "task_next_step",
}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def parse_opportunity(content: Any) -> dict[str, Any] | None:
    """Validate the model result and discard low-value or unsafe proposals."""
    text = _text(content).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not bool(raw.get("should_notify")):
        return None
    opportunity_type = str(raw.get("type") or "").strip()
    if opportunity_type not in OPPORTUNITY_TYPES:
        return None
    title = str(raw.get("title") or "").strip()[:80]
    body = str(raw.get("body") or "").strip()[:240]
    action_prompt = str(raw.get("action_prompt") or "").strip()[:500]
    if not title or not body or not action_prompt:
        return None
    if not safe_non_sensitive_text("\n".join((title, body, action_prompt, str(raw.get("reason") or "")))):
        return None
    try:
        confidence = float(raw.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if confidence < 0.72:
        return None
    try:
        expires_in_hours = max(1, min(168, int(raw.get("expires_in_hours") or 24)))
    except (TypeError, ValueError):
        expires_in_hours = 24
    return {
        "type": opportunity_type,
        "title": title,
        "body": body,
        "action_prompt": action_prompt,
        "priority": "normal" if str(raw.get("priority") or "") != "low" else "low",
        "confidence": round(min(1.0, confidence), 3),
        "expires_in_hours": expires_in_hours,
        "reason": str(raw.get("reason") or "").strip()[:240],
    }


async def detect_opportunity(
    model: Any,
    *,
    user_message: str,
    answer: str,
    capability_plan: dict[str, Any] | None = None,
    memory_context: str = "",
    recent_questions: list[str] | None = None,
    has_pending_action: bool = False,
    timeout_seconds: float = 6.0,
    response_language: object = "zh-CN",
) -> dict[str, Any] | None:
    """Use semantic judgment to identify one proactive service opportunity."""
    if not str(user_message or "").strip() or not str(answer or "").strip() or has_pending_action:
        return None
    language = normalize_language(response_language)
    system = text(
        "model.proactive.opportunity",
        language,
        language_instruction=language_instruction(language),
    )
    payload = {
        "user_message": str(user_message)[:3000],
        "answer": str(answer)[:6000],
        "capability_plan": capability_plan or {},
        "safe_memory_context": str(memory_context or "")[:1800],
        "recent_questions": [
            str(item).strip()[:240]
            for item in (recent_questions or [])[:6]
            if str(item).strip()
        ],
    }
    try:
        response = await asyncio.wait_for(
            model.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]),
            timeout=max(1.0, min(12.0, float(timeout_seconds))),
        )
    except Exception:
        return None
    return parse_opportunity(getattr(response, "content", response))


async def detect_generated_image_opportunity(
    model: Any,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 6.0,
    response_language: object = "zh-CN",
) -> dict[str, Any] | None:
    """Judge a completed image action without delaying the image response.

    The Workspace result is a trusted completion signal, but whether another
    version would help is still semantic.  Only the prompt and non-sensitive
    layout metadata are passed to the detector; image URLs and Blob keys stay
    out of the model context.
    """
    prompt = str(payload.get("prompt") or "").strip()[:2000]
    if not prompt:
        return None
    context = {
        "generated": True,
        "has_reference_image": bool(payload.get("has_reference_image")),
        "group_has_previous_version": bool(payload.get("has_previous_version")),
    }
    opportunity = await detect_opportunity(
        model,
        user_message=text("model.proactive.generated_image_request", response_language, prompt=prompt),
        answer=text("model.proactive.generated_image_answer", response_language),
        capability_plan={"intent": "image", "image_result": context},
        timeout_seconds=timeout_seconds,
        response_language=response_language,
    )
    if not opportunity or opportunity.get("type") != "image_iteration":
        return None
    return opportunity


async def detect_uploaded_file_opportunity(
    model: Any,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 6.0,
    response_language: object | None = None,
) -> dict[str, Any] | None:
    """Semantically choose the most useful unsolicited next step for a document.

    The bounded preview is transient model context. It is never copied into the
    proactive event; the durable notification keeps only the Blob reference.
    """
    preview = str(payload.get("preview") or "").strip()[:3000]
    language = normalize_language(response_language or payload.get("ui_language"))
    default_name = text("proactive.document.default_name", language)
    filename = str(payload.get("filename") or default_name).strip()[:120] or default_name
    if not preview:
        return None
    preferred_language = str(payload.get("ui_language") or "zh-CN").strip()[:24]
    return await detect_opportunity(
        model,
        user_message=text("model.proactive.upload_request", language, filename=filename),
        answer=text(
            "model.proactive.upload_context", language,
            preferred_language=preferred_language, preview=preview,
        ),
        capability_plan={
            "event": "file_uploaded",
            "is_paper": bool(payload.get("is_paper")),
            "preferred_response_language": preferred_language,
            "selection_rule": text("model.proactive.upload_selection", language),
        },
        timeout_seconds=timeout_seconds,
        response_language=language,
    )


def opportunity_signal(
    opportunity: dict[str, Any], *, source_id: str, now: int,
) -> dict[str, Any]:
    """Convert a validated semantic proposal into the shared signal shape."""
    identity = "|".join((
        str(opportunity.get("type") or ""),
        " ".join(str(opportunity.get("action_prompt") or "").casefold().split()),
    ))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    expires_at = now + int(opportunity.get("expires_in_hours") or 24) * 3600
    return {
        "type": f"opportunity_{opportunity['type']}",
        "source": "semantic_opportunity",
        "dedup_key": f"semantic_opportunity:{digest}",
        "priority": str(opportunity.get("priority") or "low"),
        "subject_ids": [str(source_id or "")],
        "title": str(opportunity.get("title") or text("proactive.default_title", "zh-CN")),
        "detail": str(opportunity.get("body") or ""),
        "action": str(opportunity.get("action_prompt") or ""),
        "evidence": {
            "opportunity_type": str(opportunity.get("type") or ""),
            "confidence": float(opportunity.get("confidence") or 0),
            "reason": str(opportunity.get("reason") or ""),
            "source_id": str(source_id or ""),
        },
        "occurred_at": now,
        "expires_at": expires_at,
        "cooldown_seconds": 6 * 3600,
    }


def file_opportunity_signal(payload: dict[str, Any], *, dedup_key: str, now: int) -> dict[str, Any]:
    """A successful document upload is already a trusted, explicit signal."""
    language = normalize_language(payload.get("ui_language"))
    default_name = text("proactive.document.default_name", language)
    filename = str(payload.get("filename") or default_name).strip()[:120] or default_name
    is_paper = bool(payload.get("is_paper"))
    return {
        "type": "opportunity_document_next_step",
        "source": "file_uploaded",
        "dedup_key": f"document_opportunity:{dedup_key}",
        "priority": "normal",
        "subject_ids": [str(payload.get("file_id") or payload.get("storage_key") or "")],
        "title": text("proactive.document.ready", language),
        "detail": text(
            f"proactive.document.detail.{'paper' if is_paper else 'general'}",
            language, filename=filename,
        ),
        "action": text(
            f"proactive.document.action.{'paper' if is_paper else 'general'}",
            language, filename=filename,
        ),
        "evidence": {
            "opportunity_type": "document_next_step",
            "file_id": str(payload.get("file_id") or ""),
            "storage_key": str(payload.get("storage_key") or ""),
            "filename": filename,
            "is_paper": is_paper,
        },
        "occurred_at": now,
        "expires_at": now + 7 * 24 * 3600,
    }
