"""Bounded chat input, checkpoint, and tool-message translation helpers."""

from __future__ import annotations

import json
import logging

from ...chat._protocol import public_content
from ..._application.workspace.service import (
    load_user_workspace,
    merge_public_action_snapshot,
)
from ..._application.i18n import text as copy_text


def checkpoint_final_answer(snapshot) -> str:
    """Recover a manual graph fallback that message-token streaming omits.

    LangGraph's ``stream_mode="messages"`` yields LLM tokens and tool messages,
    but an ``AIMessage`` constructed by a graph node as a safe terminal fallback
    is only visible in the final checkpoint. Returning it here keeps live SSE
    and a later ``/messages`` reload consistent.
    """
    values = getattr(snapshot, "values", None)
    if not isinstance(values, dict) and isinstance(snapshot, dict):
        values = snapshot.get("values")
    messages = values.get("messages") if isinstance(values, dict) else []
    for message in reversed(messages if isinstance(messages, list) else []):
        if getattr(message, "type", "") in {"human", "user"}:
            break
        if getattr(message, "type", "") not in {"ai", "assistant"}:
            continue
        content = public_content(_text_content(getattr(message, "content", ""))).strip()
        if content:
            return content
    return ""


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _usage_values(message) -> tuple[int, int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return input_tokens, output_tokens, total_tokens


def _document_context(body: dict) -> str:
    raw = body.get("document_context")
    if not isinstance(raw, dict):
        return ""
    fallback_name = copy_text(
        "chat.uploaded_document", body.get("response_language"),
    )
    filename = str(raw.get("filename") or fallback_name).strip()[:180] or fallback_name
    text = str(raw.get("text") or "").replace("\x00", "").strip()[:60_000]
    if not text:
        return ""
    return f"<uploaded_document filename={json.dumps(filename, ensure_ascii=False)}>\n{text}\n</uploaded_document>"


def _ui_action(content: str) -> dict | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not str(value.get("ui_action", "")):
        return None
    return value


async def hydrate_durable_map_action(store, user_id: str, envelope: dict | None):
    """Restore provider geometry without exposing it to the answer model."""
    if (
        not envelope
        or envelope.get("ui_action") != "map_action"
        or not isinstance(envelope.get("action"), dict)
    ):
        return envelope
    action_id = str(envelope["action"].get("id") or "")
    if not action_id:
        return envelope
    try:
        workspace = await load_user_workspace(store, user_id=user_id)
        action = workspace.get("actions", {}).get(action_id)
        if isinstance(action, dict):
            return {
                **envelope,
                "action": merge_public_action_snapshot(
                    envelope["action"], action,
                ),
            }
    except Exception:
        logging.exception("durable map action enrichment failed action=%s", action_id)
    return envelope


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _recent_user_questions(store, conversation_id: str, current_message: str) -> list[str]:
    """Read a small, non-sensitive recent-question window off the answer path.

    This is only context for semantic proactive judgment. It is intentionally
    bounded, de-duplicated, and never exposed as a user-facing memory list.
    """
    if not hasattr(store, "get_messages"):
        return []
    try:
        result = await store.get_messages(
            conversation_id=conversation_id,
            limit=24,
            order="desc",
        )
    except Exception:
        return []
    items = result if isinstance(result, list) else _field(result, "items", [])
    if not isinstance(items, list):
        return []
    current = str(current_message or "").strip()
    seen: set[str] = set()
    questions: list[str] = []
    for item in items:
        role = str(_field(item, "role", "") or "").lower()
        if role not in {"user", "human"}:
            continue
        content = _text_content(_field(item, "content", "")).replace("\x00", "").strip()
        if not content or content == current:
            continue
        normalized = " ".join(content.split()).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        questions.append(content[:240])
        if len(questions) >= 6:
            break
    return questions


async def checkpoint_dialogue_context(
    checkpointer,
    conversation_id: str,
    current_message: str = "",
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Read a small visible dialogue slice for reference resolution.

    The capability planner normally sees only the current turn so it can stay
    fast. That made ordinal/anaphoric requests such as selecting an earlier
    fourth recommendation look like a literal POI. A bounded visible slice is
    enough to resolve the reference without injecting tool traces or the full
    conversation into every prompt.
    """
    if checkpointer is None or not hasattr(checkpointer, "aget_tuple"):
        return []
    try:
        checkpoint_tuple = await checkpointer.aget_tuple({
            "configurable": {"thread_id": conversation_id},
        })
        checkpoint = _field(checkpoint_tuple, "checkpoint", {}) or {}
        channels = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
        messages = channels.get("messages", []) if isinstance(channels, dict) else []
    except Exception:
        return []
    current = " ".join(str(current_message or "").split())
    output: list[dict[str, str]] = []
    total_chars = 0
    for item in reversed(list(messages or [])):
        role = str(_field(item, "type", _field(item, "role", "")) or "").lower()
        if role not in {"human", "user", "ai", "assistant"}:
            continue
        additional = _field(item, "additional_kwargs", {}) or {}
        if isinstance(additional, dict) and (
            additional.get("floris_ui_hidden")
            or additional.get("floris_interaction") == "clarification"
        ):
            continue
        content = " ".join(
            _text_content(_field(item, "content", "")).replace("\x00", "").split()
        )
        if not content or (role in {"human", "user"} and content == current):
            continue
        normalized_role = "user" if role in {"human", "user"} else "assistant"
        per_message_limit = 500 if normalized_role == "user" else 1800
        content = content[:per_message_limit]
        remaining = 5000 - total_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        output.append({"role": normalized_role, "content": content})
        total_chars += len(content)
        if len(output) >= max(1, min(12, int(limit or 8))):
            break
    output.reverse()
    return output


__all__ = (
    "_document_context",
    "_recent_user_questions",
    "_text_content",
    "_ui_action",
    "hydrate_durable_map_action",
    "_usage_values",
    "checkpoint_dialogue_context",
    "checkpoint_final_answer",
)
