"""Chat turn runtime, tool-selection, and prompt composition policy."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime

from ..i18n import normalize_language, text


WEEKDAY_LABELS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)


def runtime_datetime_context(value: datetime) -> str:
    """Return an explicit runtime date and weekday; the LLM must not recalculate it."""
    weekday_index = value.weekday()
    return text(
        "model.chat.runtime_context",
        "zh-CN",
        timestamp=value.strftime("%Y-%m-%d %H:%M:%S"),
        weekday_en=WEEKDAY_LABELS[weekday_index],
        weekday_local=text(f"model.chat.weekday.{weekday_index}", "zh-CN"),
    )


def normalize_browser_current_location(
    value: object,
    *,
    now_ms: int | None = None,
    response_language: object = "zh-CN",
) -> dict | None:
    """Accept a fresh browser GPS fix without persisting or exposing it to the model."""
    if not isinstance(value, dict) or value.get("coordinate_type") != "wgs84":
        return None
    try:
        latitude = float(value.get("latitude"))
        longitude = float(value.get("longitude"))
        accuracy = max(0.0, float(value.get("accuracy_meters") or 0))
        captured_at = int(value.get("captured_at") or 0)
    except (TypeError, ValueError):
        return None
    timestamp = int(time.time() * 1000 if now_ms is None else now_ms)
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or accuracy > 5_000
        or captured_at <= 0
        or captured_at > timestamp + 2 * 60 * 1000
        or timestamp - captured_at > 10 * 60 * 1000
    ):
        return None
    return {
        "schema_version": 1,
        "place_id": "browser-current-location",
        "provider": "browser-wgs84",
        "name": text("chat.location.name", response_language),
        "address": text("chat.location.ephemeral_address", response_language),
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_type": "wgs84",
        "accuracy_meters": round(accuracy, 1),
        "captured_at": captured_at,
        "ephemeral": True,
    }


def normalize_browser_location_request(value: object) -> str:
    """Keep only a non-sensitive browser outcome used to tailor recovery UI."""
    if not isinstance(value, dict):
        return "not_attempted"
    state = str(value.get("state") or "").strip().lower()
    return state if state in {
        "available", "denied", "timed_out", "unavailable", "failed", "idle",
    } else "not_attempted"


def location_clarification_copy(
    intent: str,
    request_state: str,
    response_language: object = "zh-CN",
) -> tuple[str, str]:
    language = normalize_language(response_language)
    nearby = intent == "nearby"
    route = intent == "route"
    if request_state == "denied":
        return (
            text("chat.location.denied.title", language),
            text("chat.location.denied.prompt", language),
        )
    if request_state == "timed_out":
        return (
            text("chat.location.timeout.title", language),
            text(
                "chat.location.timeout.prompt",
                language,
                target=text(
                    "chat.location.target.nearby" if nearby else "chat.location.target.origin",
                    language,
                ),
            ),
        )
    if request_state == "unavailable":
        return (
            text("chat.location.unavailable.title", language),
            text(
                "chat.location.unavailable.prompt",
                language,
                target=text(
                    "chat.location.target.nearby" if nearby else "chat.location.target.origin",
                    language,
                ),
            ),
        )
    return (
        text(
            "chat.location.missing.nearby.title"
            if nearby
            else "chat.location.missing.route.title"
            if route
            else "chat.location.missing.current.title",
            language,
        ),
        text(
            "chat.location.missing.nearby.prompt"
            if nearby
            else "chat.location.missing.route.prompt"
            if route
            else "chat.location.missing.current.prompt",
            language,
        ),
    )


def location_clarification_arguments(
    intent: str,
    request_state: str,
    response_language: object = "zh-CN",
) -> dict:
    """Build the localized location card without leaking copy into orchestration."""
    language = normalize_language(response_language)
    title, prompt = location_clarification_copy(intent, request_state, language)
    field_id = {
        "nearby": "nearby_anchor",
        "route": "route_origin",
        "current": "manual_location",
    }[intent]
    label_key = {
        "nearby": "chat.location.field.nearby",
        "route": "chat.location.field.route",
        "current": "chat.location.field.current",
    }[intent]
    return {
        "title": title,
        "prompt": prompt,
        "fields": [{
            "id": field_id,
            "label": text(label_key, language),
            "type": "text",
            "required": True,
            "options": [],
            "placeholder": text("chat.location.placeholder", language),
        }],
    }


def run_cancelled(value: object) -> bool:
    """Treat both the platform acknowledgement and terminal marker as stop."""
    return bool(
        isinstance(value, dict)
        and value.get("status") in {"cancel_requested", "cancelled"}
    )


def empty_generation_error(
    final_answer: str,
    *,
    has_actions: bool,
    clarification_emitted: bool,
    run_error: str,
    cancelled: bool,
    response_language: object = "zh-CN",
) -> str:
    """Return a terminal error when a run produced no user-visible result."""
    if (
        not str(final_answer or "").strip()
        and not has_actions
        and not clarification_emitted
        and not run_error
        and not cancelled
    ):
        return text("chat.empty_generation", response_language)
    return ""


def should_buffer_public_answer(capability_plan: dict) -> bool:
    """Every model answer streams; trusted component output stays separate."""
    return False


SYSTEM_PROMPT_SECTION_ORDER = (
    "identity",
    "response_language",
    "runtime",
    "calendar_context",
    "browser_location",
    "capability_plan",
    "current_user_precedence",
    "reference_image_context",
    "document_context",
    "document_safety",
    "generic_tool_use",
    "relative_time",
    "rich_search",
    "search_media",
    "visual_search",
    "temporal_evidence",
    "nearby_map",
    "map_action",
    "route",
    "travel_itinerary",
    "calendar",
    "clarification",
    "preference_options",
    "meeting_image",
    "image_no_markdown",
    "image_no_strategy",
    "paper_search",
    "no_repeat_tool",
    "page_images",
    "memory_use",
    "memory_maintenance",
    "internal_protocol",
    "followups",
)
SYSTEM_PROMPT_SECTIONS = {
    section: text(f"model.chat.policy.{section}", "zh-CN")
    for section in SYSTEM_PROMPT_SECTION_ORDER
}
SYSTEM_PROMPT = "\n".join(
    SYSTEM_PROMPT_SECTIONS[section] for section in SYSTEM_PROMPT_SECTION_ORDER
)
MAP_TOOL_NAMES = {
    "get_current_location",
    "search_places",
    "search_places_batch",
    "recommend_nearby_places_on_map",
    "plan_route_between_places",
    "prepare_map_recommendation",
    "recommend_places_on_map",
}
WEB_TOOL_NAMES = {
    "rich_search",
    "collect_page_images",
    "analyze_images_parallel",
}


def tools_for_capability_stage(
    all_tools: list,
    required_tool_names: tuple[str, ...],
    *,
    blocked_skill: str = "",
    planner_timed_out: bool = False,
) -> list:
    if blocked_skill:
        return []
    if planner_timed_out:
        return list(all_tools)
    # Necessary-information collection is a product-wide interaction surface,
    # not a calendar/map special case. Keep the one strictly validated card
    # tool available even when the planner selects no domain capability, so a
    # full-history answer pass can recover a blocker the compact router missed.
    allowed_names = {"ask_user_clarification", *required_tool_names}
    return [
        tool for tool in all_tools
        if getattr(tool, "name", "") in allowed_names
    ]


def direct_paper_tool_arguments(capability_plan: dict) -> dict[str, dict]:
    """Skip an argument-model round only for self-contained paper searches.

    Cross-source turns must first let ``rich_search`` return exact paper
    evidence; the following Flash tool stage can then pass those titles to
    arXiv instead of launching a second broad topic search.
    """
    if (
        not capability_plan.get("needs_papers")
        or capability_plan.get("needs_web_search")
        or not (
            capability_plan.get("paper_topic")
            or capability_plan.get("paper_author")
        )
    ):
        return {}
    return {
        "search_arxiv": {
            "topic": str(capability_plan.get("paper_topic") or "")[:240],
            "limit": max(
                1,
                min(8, int(capability_plan.get("paper_limit") or 5)),
            ),
            "author": str(capability_plan.get("paper_author") or "")[:160],
            "institution": str(
                capability_plan.get("paper_institution") or ""
            )[:160],
            "year": int(capability_plan.get("paper_year") or 0),
            "year_from": int(capability_plan.get("paper_year_from") or 0),
            "year_to": int(capability_plan.get("paper_year_to") or 0),
        },
    }


def dynamic_system_prompt(
    *,
    selected_tools: set[str],
    now: str,
    response_language_instruction: str,
    capability_plan: dict,
    calendar_context: str,
    reference_image_context: str,
    document_context: str,
    current_location_context: str,
    current_route_context: str,
    memory_context: str,
    user_skill_context: str = "",
    public_answer: bool = False,
    full_prompt: bool = False,
    response_language: object = "zh-CN",
) -> str:
    """Render only the policy paragraphs and runtime state needed now."""
    language = normalize_language(response_language)
    if full_prompt:
        selected_sections = set(SYSTEM_PROMPT_SECTIONS)
    elif public_answer:
        selected_sections = {
            "identity",
            "response_language",
            "runtime",
            "current_user_precedence",
            "no_repeat_tool",
            "memory_use",
            "memory_maintenance",
            "internal_protocol",
            "followups",
        }
    else:
        selected_sections = {
            "identity",
            "response_language",
            "runtime",
            "capability_plan",
            "current_user_precedence",
            "generic_tool_use",
            "clarification",
            "preference_options",
            "no_repeat_tool",
            "memory_use",
            "memory_maintenance",
            "internal_protocol",
            "followups",
        }

    uses_maps = bool(selected_tools & MAP_TOOL_NAMES)
    uses_route = "plan_route_between_places" in selected_tools
    uses_place_lookup = bool(selected_tools & {
        "search_places",
        "search_places_batch",
        "recommend_nearby_places_on_map",
        "prepare_map_recommendation",
        "recommend_places_on_map",
    })
    uses_map_recommendation = bool(selected_tools & {
        "recommend_nearby_places_on_map",
        "prepare_map_recommendation",
        "recommend_places_on_map",
    })
    uses_calendar = (
        "propose_calendar_changes" in selected_tools
        or bool(capability_plan.get("needs_calendar_context"))
    )
    uses_web = bool(selected_tools & WEB_TOOL_NAMES)
    uses_images = "propose_image" in selected_tools
    uses_papers = "search_arxiv" in selected_tools
    uses_meeting = "propose_meeting" in selected_tools

    if uses_web:
        selected_sections.update({
            "relative_time",
            "rich_search",
            "search_media",
            "visual_search",
            "temporal_evidence",
            "page_images",
        })
    if uses_maps:
        selected_sections.add("browser_location")
    if uses_place_lookup:
        selected_sections.add("nearby_map")
    if uses_map_recommendation:
        selected_sections.add("map_action")
    if uses_route:
        selected_sections.add("route")
    if uses_calendar:
        selected_sections.update({"calendar_context", "calendar"})
    if uses_images or uses_meeting:
        selected_sections.add("meeting_image")
    if uses_images:
        selected_sections.update({"image_no_markdown", "image_no_strategy"})
    if uses_papers:
        selected_sections.add("paper_search")
    localized_none = text("model.chat.none", language)
    if reference_image_context and reference_image_context != localized_none:
        selected_sections.add("reference_image_context")
    if document_context and document_context != localized_none:
        selected_sections.update({"document_context", "document_safety"})

    if public_answer:
        # The public pass has no tools. Keep evidence and presentation rules,
        # but omit parameter-generation rules and large mutable state.
        selected_sections.difference_update({
            "calendar_context",
            "browser_location",
            "capability_plan",
            "generic_tool_use",
            "nearby_map",
            "route",
            "calendar",
            "clarification",
            "meeting_image",
        })
        if uses_web:
            selected_sections.update({
                "relative_time",
                "search_media",
                "visual_search",
                "temporal_evidence",
            })
        if uses_map_recommendation:
            selected_sections.add("map_action")
        if uses_images:
            selected_sections.update({"image_no_markdown", "image_no_strategy"})

    localized_sections = {
        section: text(f"model.chat.policy.{section}", language)
        for section in SYSTEM_PROMPT_SECTION_ORDER
    }
    template = "\n".join(
        paragraph
        for section, paragraph in localized_sections.items()
        if section in selected_sections
    )
    rendered = template.format(
        now=now,
        response_language_instruction=response_language_instruction,
        capability_plan=json.dumps({
            key: value
            for key, value in capability_plan.items()
            if key != "blocked_skill"
            and not key.startswith("_runtime_")
        }, ensure_ascii=False),
        calendar_context=calendar_context,
        reference_image_context=reference_image_context or localized_none,
        document_context=document_context or localized_none,
    )
    # This short truth signal is always present: direct questions such as
    # “我现在在哪” may legitimately have no map tool selected, but must never
    # hallucinate a permission grant or a successful location lookup.
    tails = []
    if (
        full_prompt
        or uses_maps
        or capability_plan.get("needs_current_location")
        or capability_plan.get("needs_nearby_places")
        or capability_plan.get("needs_route")
        or capability_plan.get("route_uses_current_location")
    ):
        tails.append(text(
            "model.chat.location_truth", language,
            location_context=current_location_context,
        ))
    if uses_route or uses_calendar:
        tails.append(text(
            "model.chat.latest_route", language,
            route_context=current_route_context,
        ))
    if memory_context and (
        full_prompt or capability_plan.get("use_memory_context")
    ):
        tails.append(text(
            "model.chat.memory_context", language,
            memory_context=memory_context,
        ))
    if user_skill_context:
        tails.append(text(
            "model.chat.private_skills", language,
            skill_context=user_skill_context,
        ))
    fallback_skills = set(
        capability_plan.get("_runtime_model_fallback_skills") or []
    )
    if fallback_skills:
        tails.append(text("model.chat.model_fallback", language))
    if "web-search" in fallback_skills:
        tails.append(text("model.chat.web_fallback", language))
    if public_answer and selected_tools:
        tails.append(text("model.chat.public_tools", language))
    if public_answer and "search_arxiv" in selected_tools:
        tails.append(text("model.chat.paper_results", language))
    if public_answer and "plan_route_between_places" in selected_tools:
        tails.append(text("model.chat.route_results", language))
    return rendered + "\n\n" + "\n\n".join(tail for tail in tails if tail)


__all__ = (
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_SECTIONS",
    "SYSTEM_PROMPT_SECTION_ORDER",
    "direct_paper_tool_arguments",
    "dynamic_system_prompt",
    "empty_generation_error",
    "location_clarification_arguments",
    "location_clarification_copy",
    "normalize_browser_current_location",
    "normalize_browser_location_request",
    "run_cancelled",
    "runtime_datetime_context",
    "should_buffer_public_answer",
    "tools_for_capability_stage",
)
