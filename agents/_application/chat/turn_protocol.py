"""Structured clarification and deterministic turn-resume protocol."""

from __future__ import annotations

import copy
import re

from ..i18n import normalize_language, text


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict)
        )
    return str(content or "")


def clarification_response_answers(body: dict) -> list[dict]:
    """Normalize structured card answers as bounded protocol data."""
    response = body.get("clarification_response")
    if body.get("interaction_mode") != "clarification" or not isinstance(response, dict):
        return []
    normalized: list[dict] = []
    for raw in response.get("answers") or []:
        if not isinstance(raw, dict):
            continue
        field_id = str(raw.get("id") or "").strip()[:80]
        if not field_id:
            continue
        value = raw.get("value")
        if isinstance(value, list):
            clean_value = [
                " ".join(str(item or "").split())[:240]
                for item in value[:12]
                if str(item or "").strip()
            ]
        else:
            clean_value = " ".join(str(value or "").split())[:240]
        if not clean_value:
            continue
        normalized.append({
            "id": field_id,
            "label": " ".join(str(raw.get("label") or "").split())[:160],
            "value": clean_value,
        })
        if len(normalized) >= 12:
            break
    return normalized


async def checkpoint_clarification_state(
    checkpointer,
    conversation_id: str,
) -> dict:
    """Recover answers and unfinished machine protocol in one checkpoint read."""
    empty = {"answer_texts": [], "answers": [], "resume": {}}
    if checkpointer is None or not hasattr(checkpointer, "aget_tuple"):
        return empty
    try:
        checkpoint_tuple = await checkpointer.aget_tuple({
            "configurable": {"thread_id": conversation_id},
        })
        checkpoint = _field(checkpoint_tuple, "checkpoint", {}) or {}
        channels = (
            checkpoint.get("channel_values", {})
            if isinstance(checkpoint, dict)
            else {}
        )
        messages = (
            channels.get("messages", [])
            if isinstance(channels, dict)
            else []
        )
    except Exception:
        return empty
    answer_texts: list[str] = []
    structured_answer_groups: list[list[dict]] = []
    resume: dict = {}
    for item in reversed(list(messages or [])):
        try:
            role = str(
                _field(item, "type", _field(item, "role", "")) or ""
            ).lower()
            additional = _field(item, "additional_kwargs", {}) or {}
            if (
                not resume
                and role in {"ai", "assistant"}
                and isinstance(additional, dict)
                and isinstance(additional.get("floris_resume"), dict)
            ):
                resume = copy.deepcopy(additional["floris_resume"])
            if role not in {"human", "user"}:
                continue
            if not (
                isinstance(additional, dict)
                and additional.get("floris_interaction") == "clarification"
            ):
                break
            content = _text_content(_field(item, "content", "")).strip()
            raw_answers = additional.get("floris_answers") or []
        except Exception:
            continue
        if content:
            answer_texts.append(content[:500])
        if isinstance(raw_answers, list):
            structured_answer_groups.append([
                copy.deepcopy(answer)
                for answer in raw_answers
                if isinstance(answer, dict)
            ])
        if len(answer_texts) >= 8:
            break
    answer_texts.reverse()
    structured_answers = [
        answer
        for group in reversed(structured_answer_groups)
        for answer in group
    ]
    return {
        "answer_texts": answer_texts,
        "answers": structured_answers[-48:],
        "resume": resume,
    }


async def checkpoint_clarification_answers(
    checkpointer,
    conversation_id: str,
) -> list[str]:
    """Backward-compatible text-only view of checkpoint clarification state."""
    state = await checkpoint_clarification_state(checkpointer, conversation_id)
    return state["answer_texts"]


def clarification_response_id(body: dict) -> str:
    response = body.get("clarification_response")
    if body.get("interaction_mode") != "clarification" or not isinstance(response, dict):
        return ""
    return str(response.get("id") or "").strip()


def clarification_answer_value(body: dict, field_id: str) -> str:
    for answer in clarification_response_answers(body):
        if answer["id"] != field_id:
            continue
        value = answer.get("value")
        if isinstance(value, list):
            value = "、".join(value)
        return str(value or "")[:240]
    return ""


def should_persist_user_message(body: dict) -> bool:
    return not clarification_response_id(body) and not bool(
        body.get("_location_retry")
    )


def explicit_activity_capability_protocol(
    body: dict,
    message: str,
) -> tuple[dict, dict]:
    """Translate trusted UI activities into a fixed Adapter invocation.

    Activities are versioned client protocol, not natural-language intent. A
    route card already carries the exact persisted route-plan identity, so
    asking the model to choose tools and rebuild calendar arguments here adds
    a second, lossy decision after the user has made an explicit choice.
    """
    if str(body.get("activity") or "").strip() != "route_calendar_offer_accepted":
        return {}, {}
    summary = " ".join(str(message or "").split())[:500]
    return (
        {
            "needs_calendar_context": True,
            "needs_calendar_action": True,
            "reuse_latest_route": True,
        },
        {
            "propose_calendar_changes": {
                "summary": summary,
                "changes": [],
            },
        },
    )


def has_resumable_capability_protocol(resume: object) -> bool:
    """Return whether a checkpoint contains our fixed clarification protocol."""
    return (
        isinstance(resume, dict)
        and str(resume.get("version") or "") == "1"
        and isinstance(resume.get("required_tools"), list)
        and bool(resume.get("required_tools"))
    )


def deterministic_capability_protocol(
    default_plan: dict,
    body: dict,
    message: str,
    *,
    direct_public_answer: bool,
    silent_clarification: bool,
    resume: object,
) -> tuple[dict | None, dict]:
    """Select a machine protocol before semantic planning, when available."""
    if direct_public_answer:
        return dict(default_plan), {}
    patch, arguments = explicit_activity_capability_protocol(body, message)
    if patch:
        return {**default_plan, **patch}, arguments
    if silent_clarification and has_resumable_capability_protocol(resume):
        return dict(default_plan), {}
    return None, {}


def graph_user_message(
    content: str,
    clarification_id: str = "",
    clarification_answers: list[dict] | None = None,
) -> dict:
    message = {"role": "user", "content": content}
    if clarification_id:
        message["additional_kwargs"] = {
            "floris_ui_hidden": True,
            "floris_interaction": "clarification",
            "clarification_id": clarification_id,
            "floris_answers": copy.deepcopy(clarification_answers or []),
        }
    return message


_RESUME_TOOL_PLAN_FLAGS = {
    # These are stable internal protocol names, not natural-language routing.
    "rich_search": ("needs_web_search",),
    "get_current_location": ("needs_current_location",),
    "search_places": ("needs_places",),
    "recommend_nearby_places_on_map": ("needs_nearby_places",),
    "recommend_places_on_map": ("needs_places", "needs_map_action"),
    "plan_route_between_places": ("needs_route",),
    "propose_calendar_changes": ("needs_calendar_context", "needs_calendar_action"),
    "propose_meeting": ("needs_meeting_action",),
    "propose_workflow": ("needs_workflow_action",),
    "propose_image": ("needs_image_generation",),
    "search_arxiv": ("needs_papers",),
}


def _clarification_scalar(answer: dict) -> str:
    value = answer.get("value")
    if isinstance(value, list):
        return str(value[0] if value else "").strip()[:240]
    return str(value or "").strip()[:240]


def _apply_route_protocol_answers(
    arguments: dict,
    answers: list[dict],
) -> dict:
    """Apply route card fields to original ordered stops by stable field ids."""
    updated = copy.deepcopy(arguments)
    raw_stops = updated.get("ordered_stops")
    ordered_stops = (
        [copy.deepcopy(item) for item in raw_stops if isinstance(item, dict)]
        if isinstance(raw_stops, list)
        else []
    )
    for answer in answers:
        field_id = str(answer.get("id") or "")
        match = re.fullmatch(
            r"(route_origin|route_destination|route_stop_(\d+))(_anchor)?(?:_[0-9a-f]{6})?",
            field_id,
        )
        value = _clarification_scalar(answer)
        if not match or not value:
            continue
        target = match.group(1)
        is_anchor = bool(match.group(3))
        if ordered_stops:
            if target == "route_origin":
                index = 0
            elif target == "route_destination":
                index = len(ordered_stops) - 1
            else:
                index = int(match.group(2) or 0) - 1
            if 0 <= index < len(ordered_stops):
                ordered_stops[index] = (
                    {
                        "query": str(ordered_stops[index].get("query") or ""),
                        "near_query": value,
                    }
                    if is_anchor
                    else {"query": value, "near_query": ""}
                )
            continue
        if is_anchor:
            if target == "route_origin":
                updated["origin_near_query"] = value
            elif target == "route_destination":
                updated["destination_near_query"] = value
            continue
        if target == "route_origin":
            updated["origin_query"] = value
            updated["origin_near_query"] = ""
            updated["use_current_location_as_origin"] = False
        elif target == "route_destination":
            updated["destination_query"] = value
            updated["destination_near_query"] = ""
    if ordered_stops:
        updated["ordered_stops"] = ordered_stops
    return updated


def _apply_calendar_protocol_answers(
    arguments: dict,
    answers: list[dict],
) -> dict:
    """Bind route-calendar card values without asking the model to rebuild stops."""
    updated = copy.deepcopy(arguments)
    for answer in answers:
        field_id = str(answer.get("id") or "")
        value = _clarification_scalar(answer)
        if not value:
            continue
        if field_id == "route_calendar_start":
            updated["route_start_time"] = value
        elif field_id == "route_calendar_stop_minutes":
            try:
                updated["route_stop_minutes"] = max(15, min(720, int(value)))
            except ValueError:
                continue
    if updated.get("route_start_time"):
        updated["changes"] = []
    return updated


def _apply_nearby_protocol_answers(
    arguments: dict,
    answers: list[dict],
) -> dict:
    """Apply selected nearby anchors to the original tool arguments."""
    updated = copy.deepcopy(arguments)
    requested_anchors = list(dict.fromkeys(
        str(value or "").strip()
        for value in [
            updated.get("anchor_query"),
            *(updated.get("anchor_queries") or []),
        ]
        if str(value or "").strip()
    ))
    for answer in answers:
        field_id = str(answer.get("id") or "")
        match = re.fullmatch(
            r"(nearby_anchor|anchor_(\d+))(?:_[0-9a-f]{6})?",
            field_id,
        )
        value = _clarification_scalar(answer)
        if not match or not value:
            continue
        if match.group(1) == "nearby_anchor":
            if requested_anchors:
                requested_anchors[0] = value
            else:
                requested_anchors.append(value)
            updated["use_current_location_as_anchor"] = False
            continue
        index = int(match.group(2) or 0)
        if 0 <= index < len(requested_anchors):
            requested_anchors[index] = value
    if requested_anchors:
        updated["anchor_query"] = requested_anchors[0]
        updated["anchor_queries"] = requested_anchors[1:]
    return updated


def resume_capability_protocol(
    capability_plan: dict,
    resume: dict | None,
    clarification_answers: list[dict] | None = None,
) -> tuple[dict, dict]:
    """Restore an interrupted tool chain without semantic phrase heuristics."""
    plan = dict(capability_plan or {})
    if not isinstance(resume, dict) or str(resume.get("version") or "") != "1":
        return plan, {}
    required_tools = [
        str(name or "").strip()
        for name in (resume.get("required_tools") or [])
        if str(name or "").strip() in _RESUME_TOOL_PLAN_FLAGS
    ]
    if not required_tools or str(plan.get("blocked_skill") or "").strip():
        return plan, {}
    plan["needs_clarification"] = False
    plan["clarification_title"] = ""
    plan["clarification_prompt"] = ""
    plan["clarification_fields"] = []
    for tool_name in required_tools:
        for flag in _RESUME_TOOL_PLAN_FLAGS[tool_name]:
            plan[flag] = True
    raw_arguments = resume.get("planned_tool_arguments")
    planned_arguments = (
        copy.deepcopy(raw_arguments)
        if isinstance(raw_arguments, dict)
        else {}
    )
    nearby_arguments = planned_arguments.get(
        "recommend_nearby_places_on_map"
    )
    if isinstance(nearby_arguments, dict):
        nearby_arguments = _apply_nearby_protocol_answers(
            nearby_arguments,
            clarification_answers or [],
        )
        planned_arguments[
            "recommend_nearby_places_on_map"
        ] = nearby_arguments
        plan["nearby_anchor_query"] = str(
            nearby_arguments.get("anchor_query") or ""
        ).strip()[:160]
        plan["nearby_anchor_queries"] = [
            str(value or "").strip()[:160]
            for value in (nearby_arguments.get("anchor_queries") or [])[:4]
            if str(value or "").strip()
        ]
        plan["nearby_query"] = str(
            nearby_arguments.get("query") or ""
        ).strip()[:80]
        plan["nearby_uses_current_location"] = bool(
            nearby_arguments.get("use_current_location_as_anchor")
        )
    route_arguments = planned_arguments.get("plan_route_between_places")
    if isinstance(route_arguments, dict):
        route_arguments = _apply_route_protocol_answers(
            route_arguments,
            clarification_answers or [],
        )
        planned_arguments["plan_route_between_places"] = route_arguments
        raw_stops = route_arguments.get("ordered_stops")
        if isinstance(raw_stops, list):
            plan["route_stops"] = [
                {
                    "query": str(item.get("query") or "").strip()[:160],
                    "near_query": str(item.get("near_query") or "").strip()[:160],
                }
                for item in raw_stops[:12]
                if isinstance(item, dict) and str(item.get("query") or "").strip()
            ]
        else:
            route_stops = []
            if not route_arguments.get("use_current_location_as_origin"):
                origin = str(route_arguments.get("origin_query") or "").strip()
                if origin:
                    route_stops.append({
                        "query": origin[:160],
                        "near_query": str(
                            route_arguments.get("origin_near_query") or ""
                        ).strip()[:160],
                    })
            destination = str(
                route_arguments.get("destination_query") or ""
            ).strip()
            if destination:
                route_stops.append({
                    "query": destination[:160],
                    "near_query": str(
                        route_arguments.get("destination_near_query") or ""
                    ).strip()[:160],
                })
            plan["route_stops"] = route_stops
        plan["route_city"] = str(
            route_arguments.get("city") or plan.get("route_city") or "全国"
        )[:80]
        plan["route_mode"] = str(
            route_arguments.get("route_mode") or "default"
        )
        plan["route_strategy"] = str(
            route_arguments.get("route_strategy") or "default"
        )
        plan["route_uses_current_location"] = bool(
            route_arguments.get("use_current_location_as_origin")
        )
    calendar_arguments = planned_arguments.get("propose_calendar_changes")
    if isinstance(calendar_arguments, dict):
        planned_arguments["propose_calendar_changes"] = _apply_calendar_protocol_answers(
            calendar_arguments,
            clarification_answers or [],
        )
        if any(
            str(answer.get("id") or "").startswith("route_calendar_")
            for answer in (clarification_answers or [])
            if isinstance(answer, dict)
        ):
            plan["reuse_latest_route"] = True
    return plan, planned_arguments


def capability_planning_message(
    message: str,
    clarification_id: str = "",
    recent_user_messages: list[str] | None = None,
    prior_clarification_answers: list[str] | None = None,
    recent_dialogue: list[dict[str, str]] | None = None,
    *,
    response_language: object = "zh-CN",
) -> str:
    """Attach only the history needed for continuation and reference resolution."""
    language = normalize_language(response_language)
    current = str(message or "").strip()
    recent = [
        str(item or "").strip()
        for item in (recent_user_messages or [])
        if str(item or "").strip()
    ]
    dialogue_lines = [
        f"{text('model.chat.role.user', language) if item.get('role') == 'user' else 'Floris'}: "
        f"{str(item.get('content') or '')}"
        for item in (recent_dialogue or [])
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    dialogue_context = ""
    if dialogue_lines:
        dialogue_context = (
            text("model.chat.recent_dialogue_header", language)
            + "\n"
            + "\n".join(dialogue_lines)
            + "\n"
            + text("model.chat.current_message_header", language)
            + "\n"
        )
    if not clarification_id or not recent:
        return f"{dialogue_context}{current}"
    prior_answers = [
        str(item or "").strip()[:500]
        for item in (prior_clarification_answers or [])
        if str(item or "").strip()
    ][-8:]
    prior_context = (
        "\n".join(
            text(
                "model.chat.prior_answer",
                language,
                index=index,
                answer=answer,
            )
            for index, answer in enumerate(prior_answers, 1)
        )
        + "\n"
        if prior_answers
        else ""
    )
    continuation = text(
        "model.chat.clarification_continuation",
        language,
        goal=recent[0][:600],
        prior=prior_context,
        current=current,
    )
    return f"{dialogue_context}{continuation}"

__all__ = (
    "capability_planning_message",
    "checkpoint_clarification_answers",
    "checkpoint_clarification_state",
    "clarification_answer_value",
    "clarification_response_answers",
    "clarification_response_id",
    "graph_user_message",
    "resume_capability_protocol",
    "should_persist_user_message",
)
