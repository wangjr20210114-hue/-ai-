"""Model-driven capability planning for a user turn.

This is intentionally semantic rather than keyword based. The result only
controls which existing tools the main agent must use; it never writes a user
answer or performs a side effect.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from .._application.i18n import normalize_language, text
from .._application.skills.registry import (
    capability_skill_map,
    capability_tools_map,
    known_skill_ids,
    planner_skill_index,
    planner_topic_instructions,
    planner_topic_summaries,
    planner_topic_tools,
)


DEFAULT_PLAN = {
    "needs_clarification": False,
    "needs_web_search": False,
    "strict_today_only": False,
    "prefer_recent_results": False,
    "needs_images": False,
    "needs_places": False,
    "needs_current_location": False,
    "needs_nearby_places": False,
    "needs_route": False,
    "needs_travel_itinerary": False,
    "needs_map_action": False,
    "needs_calendar_action": False,
    "needs_calendar_context": False,
    "needs_meeting_action": False,
    "needs_workflow_action": False,
    "needs_image_generation": False,
    "needs_papers": False,
    "needs_deep_reasoning": False,
    "needs_followups": False,
    "needs_memory_extraction": False,
    "needs_opportunity_review": False,
    "use_memory_context": False,
    "search_query": "",
    "image_query": "",
    "nearby_query": "",
    "nearby_anchor_query": "",
    "nearby_anchor_queries": [],
    "nearby_uses_current_location": False,
    "paper_author": "",
    "paper_institution": "",
    "paper_topic": "",
    "paper_identity_evidence_supplied": False,
    "paper_identity_globally_unambiguous": False,
    "paper_year": 0,
    "paper_year_from": 0,
    "paper_year_to": 0,
    "paper_limit": 0,
    "blocked_skill": "",
    "route_stops": [],
    "route_city": "全国",
    "route_mode": "default",
    "route_strategy": "default",
    "travel_budget_tier": "not_applicable",
    "route_uses_current_location": False,
    "route_origin_is_departure": False,
    "reuse_latest_route": False,
    "route_calendar_hint": "",
    "optional_capabilities": [],
    "place_resolution_target": "none",
    "clarification_title": "",
    "clarification_prompt": "",
    "clarification_fields": [],
    "_prompt_topics": [],
    "_prompt_topics_source": "none",
    "_capabilities": [],
}

BOOLEAN_KEYS = tuple(key for key, value in DEFAULT_PLAN.items() if isinstance(value, bool))
KNOWN_SKILLS = known_skill_ids()


def _schema(key: str, **params: Any) -> str:
    """Resolve model-facing structured-output copy through I18N."""
    return text(f"model.planner.schema.{key}", "zh-CN", **params)


class PlannedRouteStop(BaseModel):
    """One user-specified stop preserved verbatim and in user order."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        default="",
        description=_schema("field_01"),
    )
    near_query: str = Field(
        default="",
        description=_schema("field_02"),
    )


class PlannedClarificationField(BaseModel):
    """One minimal field required to resume the original request."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description=_schema("field_03"))
    label: str = Field(description=_schema("field_04"))
    type: str = Field(
        default="text",
        description=_schema("field_05"),
    )
    required: bool = True
    options: list[str] = Field(
        default_factory=list,
        description=_schema("field_06"),
    )
    placeholder: str = ""


class CapabilityPlan(BaseModel):
    """Validated semantic plan returned by LangChain structured output."""

    model_config = ConfigDict(extra="forbid")

    prompt_topics: list[str] = Field(
        default_factory=list,
        description=_schema("field_07"),
    )
    capabilities: list[str] = Field(
        description=_schema("field_08"),
    )
    needs_clarification: bool = False
    needs_web_search: bool = False
    strict_today_only: bool = Field(
        default=False,
        description=_schema("field_09"),
    )
    prefer_recent_results: bool = Field(
        default=False,
        description=_schema("field_49"),
    )
    needs_images: bool = Field(
        default=False,
        description=_schema("field_10"),
    )
    needs_places: bool = False
    needs_current_location: bool = Field(
        default=False,
        description=_schema("field_11"),
    )
    needs_nearby_places: bool = False
    needs_route: bool = Field(
        default=False,
        description=_schema("field_12"),
    )
    needs_travel_itinerary: bool = Field(
        default=False,
        description=_schema("field_13"),
    )
    needs_map_action: bool = False
    needs_calendar_action: bool = Field(
        default=False,
        description=_schema("field_14"),
    )
    needs_calendar_context: bool = Field(
        default=False,
        description=_schema("field_15"),
    )
    needs_meeting_action: bool = False
    needs_workflow_action: bool = False
    needs_image_generation: bool = False
    needs_papers: bool = Field(
        default=False,
        description=_schema("field_16"),
    )
    needs_deep_reasoning: bool = Field(
        default=False,
        description=_schema("field_17"),
    )
    needs_followups: bool = Field(
        default=False,
        description=_schema("field_18"),
    )
    needs_memory_extraction: bool = Field(
        default=False,
        description=_schema("field_19"),
    )
    needs_opportunity_review: bool = Field(
        default=False,
        description=_schema("field_20"),
    )
    use_memory_context: bool = Field(
        default=False,
        description=_schema("field_21"),
    )
    search_query: str = ""
    image_query: str = ""
    nearby_query: str = Field(
        default="",
        description=_schema("field_22"),
    )
    nearby_anchor_query: str = Field(
        default="",
        description=_schema("field_23"),
    )
    nearby_anchor_queries: list[str] = Field(
        default_factory=list,
        description=_schema("field_24"),
    )
    nearby_uses_current_location: bool = Field(
        default=False,
        description=_schema("field_25"),
    )
    paper_author: str = Field(
        default="",
        description=_schema("field_26"),
    )
    paper_institution: str = Field(
        default="",
        description=_schema("field_27"),
    )
    paper_identity_evidence_supplied: bool = Field(
        default=False,
        description=_schema("field_28"),
    )
    paper_identity_globally_unambiguous: bool = Field(
        default=False,
        description=_schema("field_29"),
    )
    paper_topic: str = Field(
        default="",
        description=_schema("field_30"),
    )
    paper_year: int = 0
    paper_year_from: int = Field(
        default=0,
        description=_schema("field_31"),
    )
    paper_year_to: int = Field(
        default=0,
        description=_schema("field_32"),
    )
    paper_limit: int = 0
    route_stops: list[PlannedRouteStop] = Field(
        default_factory=list,
        description=_schema("field_33"),
    )
    route_city: str = Field(
        default="全国",
        description=_schema("field_34"),
    )
    route_mode: str = Field(
        default="default",
        description=_schema("field_35"),
    )
    route_strategy: str = Field(
        default="default",
        description=_schema("field_36"),
    )
    travel_budget_tier: str = Field(
        default="not_applicable",
        description=_schema("field_37"),
    )
    route_uses_current_location: bool = Field(
        default=False,
        description=_schema("field_38"),
    )
    route_origin_is_departure: bool = Field(
        default=False,
        description=_schema("field_45"),
    )
    reuse_latest_route: bool = Field(
        default=False,
        description=_schema("field_39"),
    )
    route_calendar_hint: str = Field(
        default="",
        description=_schema("field_40"),
    )
    optional_capabilities: list[str] = Field(
        default_factory=list,
        description=_schema("field_41"),
    )
    place_resolution_target: str = Field(
        default="none",
        description=_schema("field_42"),
    )
    clarification_title: str = Field(
        default="",
        description=_schema("field_43"),
    )
    clarification_prompt: str = Field(
        default="",
        description=_schema("field_44"),
    )
    clarification_fields: list[PlannedClarificationField] = Field(
        default_factory=list,
        description=_schema("field_45"),
    )


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def _decode_capability_plan(
    content: Any,
    response_language: object = "zh-CN",
) -> dict[str, Any] | None:
    language = normalize_language(response_language)
    if isinstance(content, BaseModel):
        raw = content.model_dump()
    elif isinstance(content, dict):
        raw = content
    else:
        serialized = _text(content).strip()
        fenced = re.search(r"\{[\s\S]*\}", serialized)
        if fenced:
            serialized = fenced.group(0)
        try:
            raw = json.loads(serialized)
        except (TypeError, json.JSONDecodeError):
            return None
    if not isinstance(raw, dict):
        return None
    plan = {key: bool(raw.get(key, False)) for key in BOOLEAN_KEYS}
    plan["_prompt_topics"] = list(
        _normalize_prompt_topics(raw.get("prompt_topics") or [])
    )
    plan["_prompt_topics_source"] = "planner"
    plan["_capabilities"] = list(
        _normalize_preflight_capabilities(raw.get("capabilities") or [])
    )
    plan["search_query"] = str(raw.get("search_query") or "").strip()[:160]
    plan["image_query"] = str(raw.get("image_query") or "").strip()[:160]
    plan["nearby_query"] = str(raw.get("nearby_query") or "").strip()[:80]
    plan["nearby_anchor_query"] = str(
        raw.get("nearby_anchor_query") or ""
    ).strip()[:160]
    plan["nearby_anchor_queries"] = list(dict.fromkeys(
        str(value or "").strip()[:160]
        for value in (raw.get("nearby_anchor_queries") or [])
        if str(value or "").strip()
    ))[:4]
    plan["paper_author"] = str(raw.get("paper_author") or "").strip()[:120]
    plan["paper_institution"] = str(
        raw.get("paper_institution") or ""
    ).strip()[:160]
    plan["paper_topic"] = str(raw.get("paper_topic") or "").strip()[:160]
    blocked_skill = str(raw.get("blocked_skill") or "").strip()
    plan["blocked_skill"] = blocked_skill if blocked_skill in KNOWN_SKILLS else ""
    try:
        plan["paper_year"] = int(raw.get("paper_year") or 0)
        plan["paper_year_from"] = int(raw.get("paper_year_from") or 0)
        plan["paper_year_to"] = int(raw.get("paper_year_to") or 0)
        plan["paper_limit"] = max(0, min(10, int(raw.get("paper_limit") or 0)))
    except (TypeError, ValueError):
        plan["paper_year"] = 0
        plan["paper_year_from"] = 0
        plan["paper_year_to"] = 0
        plan["paper_limit"] = 0
    route_stops: list[dict[str, str]] = []
    for item in raw.get("route_stops") or []:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()[:160]
        near_query = str(item.get("near_query") or "").strip()[:160]
        if query:
            route_stops.append({"query": query, "near_query": near_query})
        if len(route_stops) >= 12:
            break
    plan["route_stops"] = route_stops if plan.get("needs_route") else []
    plan["route_city"] = str(raw.get("route_city") or "全国").strip()[:80] or "全国"
    route_mode = str(raw.get("route_mode") or "default").strip().lower()
    plan["route_mode"] = route_mode if route_mode in {
        "default", "driving", "transit", "walking", "bicycling",
    } else "default"
    route_strategy = str(raw.get("route_strategy") or "default").strip().lower()
    plan["route_strategy"] = route_strategy if route_strategy in {
        "default", "time_then_cost", "least_time", "least_cost",
    } else "default"
    travel_budget_tier = str(
        raw.get("travel_budget_tier") or "not_applicable"
    ).strip().lower()
    plan["travel_budget_tier"] = (
        travel_budget_tier
        if travel_budget_tier in {
            "economy", "standard", "premium", "unconsidered", "unknown",
            "not_applicable",
        }
        else "unknown" if plan.get("needs_travel_itinerary") else "not_applicable"
    )
    plan["route_uses_current_location"] = bool(
        plan.get("needs_route") and raw.get("route_uses_current_location")
    )
    plan["route_origin_is_departure"] = bool(
        plan.get("needs_route")
        and not plan["route_uses_current_location"]
        and raw.get("route_origin_is_departure")
    )
    plan["reuse_latest_route"] = bool(raw.get("reuse_latest_route"))
    plan["route_calendar_hint"] = str(
        raw.get("route_calendar_hint") or ""
    ).strip()[:240]
    plan["optional_capabilities"] = list(
        _normalize_preflight_capabilities(
            raw.get("optional_capabilities") or []
        )
    )
    place_resolution_target = str(
        raw.get("place_resolution_target") or "none"
    ).strip().lower()
    plan["place_resolution_target"] = (
        place_resolution_target
        if place_resolution_target in {"none", "calendar"}
        else "none"
    )
    if plan.get("needs_calendar_action"):
        plan["needs_calendar_context"] = True
    if not plan.get("needs_nearby_places"):
        plan["nearby_query"] = ""
        plan["nearby_anchor_query"] = ""
        plan["nearby_anchor_queries"] = []
        plan["nearby_uses_current_location"] = False
    allowed_field_types = {
        "single", "multi", "boolean", "text", "date", "time", "datetime",
    }
    clarification_fields: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("clarification_fields") or []):
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        field_type = str(item.get("type") or "text").strip().lower()
        if field_type not in allowed_field_types:
            continue
        options = list(dict.fromkeys(
            str(option or "").strip()[:120]
            for option in (item.get("options") or [])
            if str(option or "").strip()
        ))[:8]
        if field_type in {"single", "multi"} and len(options) < 2:
            continue
        field_id = re.sub(
            r"[^a-zA-Z0-9_-]",
            "-",
            str(item.get("id") or f"field-{index + 1}"),
        )[:48].strip("-") or f"field-{index + 1}"
        clarification_fields.append({
            "id": field_id,
            "label": str(
                item.get("label")
                or text("chat.clarification.default_label", language)
            ).strip()[:80],
            "type": field_type,
            "required": bool(item.get("required", True)),
            "options": options,
            "placeholder": str(item.get("placeholder") or "").strip()[:120],
        })
        if len(clarification_fields) >= 12:
            break
    plan["clarification_title"] = str(
        raw.get("clarification_title") or ""
    ).strip()[:120]
    plan["clarification_prompt"] = str(
        raw.get("clarification_prompt") or ""
    ).strip()[:300]
    plan["clarification_fields"] = (
        clarification_fields if plan.get("needs_clarification") else []
    )
    if not plan.get("needs_clarification"):
        plan["clarification_title"] = ""
        plan["clarification_prompt"] = ""
    # A real-world place ambiguity is resolvable only after provider lookup.
    # Restore the deterministic tool chain even if the semantic planner also
    # marked generic clarification. Missing dates/times keep target=none and
    # therefore remain genuine clarification blockers.
    if plan["place_resolution_target"] == "calendar":
        plan["needs_clarification"] = False
        plan["needs_places"] = True
        plan["needs_calendar_action"] = True
    plan = reconcile_capability_contract(plan)
    if (
        plan.get("needs_travel_itinerary")
        and plan.get("travel_budget_tier") in {"unknown", "not_applicable"}
        and not plan.get("needs_clarification")
    ):
        # Budget materially changes transport, accommodation and route detail
        # for a usable itinerary. Ask once with the product-approved finite
        # choices; "没考虑" is itself a complete answer and is never re-asked.
        for key in BOOLEAN_KEYS:
            if key.startswith("needs_"):
                plan[key] = False
        plan["needs_clarification"] = True
        plan["clarification_title"] = text("chat.travel_budget.title", language)
        plan["clarification_prompt"] = text("chat.travel_budget.prompt", language)
        plan["clarification_fields"] = [{
            "id": "travel-budget-tier",
            "label": text("chat.travel_budget.label", language),
            "type": "single",
            "required": True,
            "options": [
                text("chat.travel_budget.economy", language),
                text("chat.travel_budget.standard", language),
                text("chat.travel_budget.unconsidered", language),
            ],
            "placeholder": "",
        }]
    if (
        plan.get("needs_papers")
        and plan.get("paper_author")
        and not plan.get("paper_identity_evidence_supplied")
        and not plan.get("paper_identity_globally_unambiguous")
        and not plan.get("needs_clarification")
    ):
        # This is a protocol invariant over semantic planner fields, not a
        # name/keyword rule. Search must not convert a popular namesake into
        # identity evidence. One compact card collects the minimum qualifier,
        # then the normal planner resumes the paper capability.
        for key in BOOLEAN_KEYS:
            if key.startswith("needs_"):
                plan[key] = False
        plan["needs_clarification"] = True
        plan["clarification_title"] = text("chat.paper_author.title", language)
        plan["clarification_prompt"] = text(
            "chat.paper_author.prompt", language, author=plan["paper_author"],
        )
        plan["clarification_fields"] = [{
            "id": "paper-author-identity",
            "label": text("chat.paper_author.label", language),
            "type": "text",
            "required": True,
            "options": [],
            "placeholder": text("chat.paper_author.placeholder", language),
        }]
    return plan


def parse_capability_plan(
    content: Any,
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    return _decode_capability_plan(content, response_language) or dict(DEFAULT_PLAN)


def required_tools_for_plan(plan: dict[str, Any]) -> tuple[str, ...]:
    """Turn the semantic plan into the shortest required capability chain.

    The routing decision remains model-driven.  This function only maps the
    planner's semantic booleans to existing Makers-native tools so the main
    model cannot claim that a map, calendar change, meeting, or generated image
    is ready without actually producing the corresponding UI action.
    """
    plan = reconcile_capability_contract(plan)

    # Runtime policy may mark a required capability unavailable after semantic
    # planning. The switch itself is never part of the model contract.
    if str(plan.get("blocked_skill") or "").strip():
        return ()

    # Missing critical information is a terminal planning state for this turn.
    # Ask once with a structured card before spending search/provider budget or
    # attempting a side effect with guessed inputs.
    if bool(plan.get("needs_clarification")):
        return ("ask_user_clarification",)

    required: list[str] = []
    if bool(plan.get("needs_web_search")):
        required.append("rich_search")
    if bool(plan.get("needs_current_location")):
        required.append("get_current_location")

    # The composite map tool verifies every model-selected place and prepares
    # the terminal map Action in one call.  For a single non-map location (most
    # commonly a calendar destination), retain the focused place lookup.
    if bool(plan.get("needs_route")):
        required.append("plan_route_between_places")
    elif bool(plan.get("needs_nearby_places")):
        required.append("recommend_nearby_places_on_map")
    elif bool(plan.get("needs_map_action")):
        required.append("recommend_places_on_map")
    elif bool(plan.get("needs_places")):
        required.append("search_places")

    if bool(plan.get("needs_calendar_action")):
        required.append("propose_calendar_changes")
    if bool(plan.get("needs_meeting_action")):
        required.append("propose_meeting")
    if bool(plan.get("needs_workflow_action")):
        required.append("propose_workflow")
    if bool(plan.get("needs_image_generation")):
        required.append("propose_image")
    if bool(plan.get("needs_papers")):
        required.append("search_arxiv")
    # Plug-in capabilities do not need new central booleans. Their manifests
    # map capability ids directly to required adapter tools; built-in tools are
    # deduplicated against the compatibility chain above.
    registered_tools = capability_tools_map()
    for capability in _normalize_preflight_capabilities(
        plan.get("_capabilities") or []
    ):
        required.extend(registered_tools.get(capability, ()))
    return tuple(dict.fromkeys(required))


def required_tool_for_plan(plan: dict[str, Any]) -> str:
    """Backward-compatible first item of the semantic capability chain."""
    required = required_tools_for_plan(plan)
    return required[0] if required else ""


def media_enabled_for_plan(
    plan: dict[str, Any], image_limit: int, planner_timed_out: bool = False,
) -> bool:
    """Make reviewed media available for semantic web-search turns.

    The planner still decides whether external facts are needed and produces the
    merged query. Once it chooses web search, the same result may also provide
    reviewed image candidates unless the user set the image limit to zero. A
    distinct visual query still follows the planner; otherwise the fact response
    is reused and no second SearchPro request is added.
    """
    return int(image_limit) > 0 and bool(
        planner_timed_out or plan.get("needs_web_search") or plan.get("needs_images")
    )


def progressive_media_for_plan(
    plan: dict[str, Any], planner_timed_out: bool = False,
) -> bool:
    """Keep optional search media off the answer's critical path.

    SearchPro evidence is still required before synthesis. Page scraping and
    visual review can finish progressively because the frontend already merges
    ``search_media`` events into the active answer. Image generation is the one
    exception: it consumes reviewed search images as provider references, so
    that capability must keep the blocking media path.
    """
    return bool(planner_timed_out or plan.get("needs_web_search")) and not bool(
        plan.get("needs_image_generation")
    )


def next_required_tool(
    required_tools: Iterable[str],
    used_tool_names: Iterable[str],
    allowed_tool_names: set[str],
) -> str:
    """Return the next available planner-required tool not used this turn."""
    used = set(used_tool_names)
    for name in required_tools:
        clean_name = str(name or "").strip()
        if clean_name and clean_name in allowed_tool_names and clean_name not in used:
            return clean_name
    return ""


PROMPT_TOPIC_SUMMARIES = planner_topic_summaries()
PLANNER_PROMPT_DETAILS = planner_topic_instructions()

_PROMPT_TOPIC_IDS = ", ".join(PROMPT_TOPIC_SUMMARIES)
_CAPABILITY_IDS = ", ".join(capability_skill_map())


class PromptTopicSelection(BaseModel):
    """Semantic retrieval result for second-stage prompt fragments."""

    model_config = ConfigDict(extra="forbid")

    topics: list[str] = Field(
        default_factory=list,
        description=_schema("field_47", topic_ids=_PROMPT_TOPIC_IDS),
    )


class SemanticPreflight(BaseModel):
    """One semantic pass for readiness and dynamic prompt retrieval."""

    model_config = ConfigDict(extra="forbid")

    needs_clarification: bool = False
    title: str = ""
    prompt: str = ""
    fields: list[PlannedClarificationField] = Field(default_factory=list)
    topics: list[str] = Field(
        default_factory=list,
        description=_schema("field_47", topic_ids=_PROMPT_TOPIC_IDS),
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description=_schema("field_48", capability_ids=_CAPABILITY_IDS),
    )
    needs_web_search: bool = False
    strict_today_only: bool = Field(
        default=False,
        description=_schema("field_46"),
    )
    prefer_recent_results: bool = Field(
        default=False,
        description=_schema("field_49"),
    )
    search_query: str = ""
    needs_images: bool = False
    image_query: str = ""


def _normalize_prompt_topics(values: Iterable[Any]) -> tuple[str, ...]:
    allowed = set(PLANNER_PROMPT_DETAILS)
    return tuple(dict.fromkeys(
        str(value or "").strip().lower()
        for value in values
        if str(value or "").strip().lower() in allowed
    ))


_PREFLIGHT_CAPABILITY_FLAGS = {
    # Fixed structured protocol values; natural-language routing stays in the model.
    "web_search": ("needs_web_search",),
    "current_location": ("needs_current_location",),
    "nearby_places": ("needs_nearby_places",),
    "places": ("needs_places",),
    "map_action": ("needs_places", "needs_map_action"),
    "route": ("needs_route",),
    "calendar_context": ("needs_calendar_context",),
    "calendar_action": ("needs_calendar_context", "needs_calendar_action"),
    "meeting_action": ("needs_meeting_action",),
    "workflow_action": ("needs_workflow_action",),
    "image_generation": ("needs_image_generation",),
    "papers": ("needs_papers",),
}
for _registered_capability in capability_skill_map():
    _PREFLIGHT_CAPABILITY_FLAGS.setdefault(_registered_capability, ())

def _normalize_preflight_capabilities(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        str(value or "").strip().lower()
        for value in values
        if str(value or "").strip().lower() in _PREFLIGHT_CAPABILITY_FLAGS
    ))


def reconcile_capability_contract(plan: dict[str, Any]) -> dict[str, Any]:
    """Reconcile redundant execution fields without executing prompt fragments.

    ``prompt_topics`` only retrieve compact operating instructions for the
    planner. They are intentionally not an execution signal: a news turn may
    load the paper boundary to decide that academic search is unnecessary.
    Explicit capability enums may restore omitted ``needs_*`` flags. Existing
    flags are already consumed directly by the shortest-chain mapper and must
    not be expanded back into capability enums: composite map/calendar flags
    intentionally overlap and reverse inference would add duplicate tools.
    """
    merged = dict(plan or {})
    explicit = _normalize_preflight_capabilities(
        merged.get("_capabilities")
        or merged.get("capabilities")
        or merged.get("_preflight_capabilities")
        or []
    )
    effective = explicit
    for capability in effective:
        for flag in _PREFLIGHT_CAPABILITY_FLAGS[capability]:
            merged[flag] = True
    merged["_capabilities"] = list(effective)
    if merged.get("needs_calendar_action"):
        merged["needs_calendar_context"] = True
    return merged


async def plan_required_clarification(
    model,
    user_message: str,
    *,
    location_context: str = "",
    has_reference_images: bool = False,
    has_document_context: bool = False,
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    """Jointly decide readiness and retrieve prompt topics without phrase rules."""
    language = normalize_language(response_language)
    topic_summaries = planner_topic_summaries(language)
    catalog = "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in topic_summaries.items()
    )
    prompt = text(
        "model.planner.preflight",
        language,
        catalog=catalog,
        location_context=str(location_context or "not supplied")[:1000],
        has_reference_images=bool(has_reference_images),
        has_document_context=bool(has_document_context),
        user_copy_instruction=text("model.planner.user_copy_instruction", language),
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(user_message or "")[:7000]},
    ]
    try:
        gate = model.with_structured_output(
            SemanticPreflight,
            method="function_calling",
            include_raw=True,
        )
        response = await gate.ainvoke(messages)
        parsed = response.get("parsed") if isinstance(response, dict) else response
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        if isinstance(parsed, dict):
            normalized = _decode_capability_plan({
                "needs_clarification": bool(parsed.get("needs_clarification")),
                "clarification_title": parsed.get("title"),
                "clarification_prompt": parsed.get("prompt"),
                "clarification_fields": parsed.get("fields") or [],
            }, response_language) or dict(DEFAULT_PLAN)
            return {
                "needs_clarification": bool(
                    normalized.get("needs_clarification")
                    and normalized.get("clarification_fields")
                ),
                "clarification_title": normalized.get("clarification_title") or "",
                "clarification_prompt": normalized.get("clarification_prompt") or "",
                "clarification_fields": normalized.get("clarification_fields") or [],
                "_prompt_topics": list(
                    _normalize_prompt_topics(parsed.get("topics") or [])
                ),
                "_preflight_capabilities": list(
                    _normalize_preflight_capabilities(
                        parsed.get("capabilities") or []
                    )
                ),
                "needs_web_search": bool(parsed.get("needs_web_search")),
                "strict_today_only": bool(parsed.get("strict_today_only")),
                "prefer_recent_results": bool(
                    parsed.get("prefer_recent_results")
                ),
                "search_query": str(parsed.get("search_query") or "").strip()[:160],
                "needs_images": bool(parsed.get("needs_images")),
                "image_query": str(parsed.get("image_query") or "").strip()[:160],
                "_preflight_failed": False,
            }
    except Exception:
        pass
    return {
        "needs_clarification": False,
        "clarification_title": "",
        "clarification_prompt": "",
        "clarification_fields": [],
        "_prompt_topics": [],
        "_preflight_capabilities": [],
        "_preflight_failed": True,
    }


async def select_prompt_context(
    model,
    user_message: str,
    *,
    has_reference_images: bool = False,
    has_document_context: bool = False,
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    """Run semantic prompt-fragment retrieval."""
    language = normalize_language(response_language)
    topic_summaries = planner_topic_summaries(language)
    catalog = "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in topic_summaries.items()
    )
    prompt = text(
        "model.planner.topic_selector",
        language,
        catalog=catalog,
        has_reference_images=bool(has_reference_images),
        has_document_context=bool(has_document_context),
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(user_message or "")[:4000]},
    ]
    try:
        selector = model.with_structured_output(
            PromptTopicSelection,
            method="function_calling",
            include_raw=True,
        )
        response = await selector.ainvoke(messages)
        parsed = response.get("parsed") if isinstance(response, dict) else response
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        if isinstance(parsed, dict):
            topics = _normalize_prompt_topics(parsed.get("topics") or [])
            return {"topics": topics}
    except Exception:
        pass
    # An unknown semantic route must not expand into every prompt and tool.
    return {"topics": ()}


async def select_prompt_topics(
    model,
    user_message: str,
    *,
    has_reference_images: bool = False,
    has_document_context: bool = False,
) -> tuple[str, ...]:
    """Backward-compatible semantic topic-only view of the preflight."""
    result = await select_prompt_context(
        model,
        user_message,
        has_reference_images=has_reference_images,
        has_document_context=has_document_context,
    )
    return tuple(result.get("topics") or ())


def fallback_tools_for_prompt_topics(topics: Iterable[Any]) -> tuple[str, ...]:
    """Map model-selected prompt topics to a bounded recovery tool surface."""
    topic_tools = planner_topic_tools()
    names: list[str] = []
    for topic in _normalize_prompt_topics(topics):
        names.extend(topic_tools.get(topic, ()))
    return tuple(dict.fromkeys(names))


async def plan_capabilities(
    model,
    user_message: str,
    memory_context: str = "",
    location_context: str = "",
    prompt_topics: Iterable[Any] | None = None,
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    language = normalize_language(response_language)
    prompt = text(
        "model.planner.system",
        language,
        today=today,
        user_copy_instruction=text(
            "model.planner.user_copy_instruction", language,
        ),
    )
    prompt += "\n\n" + text(
        "model.planner.skill_index_header", language,
    ) + "\n" + planner_skill_index(language)
    topic_summaries = planner_topic_summaries(language)
    prompt += "\n\n" + text(
        "model.planner.topic_index_header", language,
    ) + "\n" + "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in topic_summaries.items()
    )
    selected_topics = (
        _normalize_prompt_topics(prompt_topics)
        if prompt_topics is not None
        else ()
    )
    prompt_details = planner_topic_instructions(language)
    details = [
        prompt_details[topic]
        for topic in selected_topics
        if topic in prompt_details
    ]
    if details:
        prompt += "\n\n" + text(
            "model.planner.details_header", language,
        ) + "\n" + "\n".join(details)
    safe_memory = str(memory_context or "").strip()[:1800]
    if safe_memory:
        prompt += "\n" + text(
            "model.planner.memory_context", language,
            memory_context=safe_memory,
        )
    safe_location_context = str(location_context or "").strip()[:600]
    if safe_location_context:
        prompt += "\n" + text(
            "model.planner.location_context", language,
            location_context=safe_location_context,
        )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(user_message or "")[:4000]},
    ]
    try:
        # Delegate schema/tool strategy and Pydantic validation to LangChain.
        # ``function_calling`` works across the Makers OpenAI-compatible
        # gateway while preserving the raw AIMessage for diagnostics.
        planner_model = model.with_structured_output(
            CapabilityPlan,
            method="function_calling",
            include_raw=True,
        )
        response = await planner_model.ainvoke(messages)
        parsed_value = response.get("parsed") if isinstance(response, dict) else response
        parsed = _decode_capability_plan(parsed_value, language)
        if parsed is not None:
            if selected_topics:
                parsed["_prompt_topics"] = list(selected_topics)
            return parsed
        # One-call compatibility for gateways that return a raw message but
        # fail LangChain's structured parser. Never retry the model.
        raw = response.get("raw") if isinstance(response, dict) else None
        parsed = _decode_capability_plan(getattr(raw, "content", ""), language)
        if parsed is not None:
            if selected_topics:
                parsed["_prompt_topics"] = list(selected_topics)
            return parsed
    except Exception:
        pass
    fallback = dict(DEFAULT_PLAN)
    fallback["_prompt_topics"] = list(selected_topics)
    fallback["_prompt_topics_source"] = "fallback"
    fallback["_planner_failed"] = True
    return fallback


async def plan_capabilities_bounded(
    model,
    user_message: str,
    memory_context: str = "",
    location_context: str = "",
    has_reference_images: bool = False,
    has_document_context: bool = False,
    timeout_seconds: float = 6.0,
    timings_ms: dict[str, int | bool] | None = None,
    response_language: object = "zh-CN",
) -> tuple[dict[str, Any], bool]:
    """Run one complete semantic plan without a duplicate preflight round."""
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    total_timeout = max(0.02, float(timeout_seconds))
    timed_out = False
    try:
        plan = await asyncio.wait_for(
            plan_capabilities(
                model,
                user_message,
                memory_context,
                location_context=location_context,
                response_language=response_language,
            ),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError:
        timed_out = True
        plan = dict(DEFAULT_PLAN)
        plan["_prompt_topics"] = []
        plan["_prompt_topics_source"] = "fallback"
    failed = bool(plan.pop("_planner_failed", False))
    recovered = False
    if failed and not timed_out:
        remaining = total_timeout - (loop.time() - started_at)
        if remaining >= 0.05:
            try:
                preflight = await asyncio.wait_for(
                    plan_required_clarification(
                        model,
                        user_message,
                        location_context=location_context,
                        has_reference_images=has_reference_images,
                        has_document_context=has_document_context,
                        response_language=response_language,
                    ),
                    timeout=remaining,
                )
                if not preflight.pop("_preflight_failed", False):
                    recovered_plan = dict(DEFAULT_PLAN)
                    for key in (
                        "needs_clarification",
                        "clarification_title",
                        "clarification_prompt",
                        "clarification_fields",
                        "needs_web_search",
                        "strict_today_only",
                        "prefer_recent_results",
                        "search_query",
                        "needs_images",
                        "image_query",
                    ):
                        if key in preflight:
                            recovered_plan[key] = preflight[key]
                    recovered_plan["_prompt_topics"] = list(
                        preflight.get("_prompt_topics") or []
                    )
                    recovered_plan["_prompt_topics_source"] = "recovery"
                    recovered_plan["_preflight_capabilities"] = list(
                        preflight.get("_preflight_capabilities") or []
                    )
                    recovered_plan["_capabilities"] = list(
                        preflight.get("_preflight_capabilities") or []
                    )
                    plan = reconcile_capability_contract(recovered_plan)
                    recovered = True
            except asyncio.TimeoutError:
                timed_out = True
    timed_out = timed_out or (failed and not recovered)
    if timings_ms is not None:
        elapsed = round((loop.time() - started_at) * 1000)
        timings_ms["semantic_plan"] = elapsed
        timings_ms["semantic_plan_timed_out"] = timed_out
        timings_ms["semantic_plan_recovered"] = recovered
        timings_ms["capability_planning_total"] = elapsed
    return plan, timed_out
