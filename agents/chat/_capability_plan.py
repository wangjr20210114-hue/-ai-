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

from .._shared.skill_registry import (
    capability_skill_map,
    capability_tools_map,
    known_skill_ids,
    planner_skill_index,
    planner_topic_instructions,
    planner_topic_summaries,
    planner_topic_tools,
    skill_degradation_capabilities,
    skill_plan_flags,
)


DEFAULT_PLAN = {
    "needs_clarification": False,
    "needs_web_search": False,
    "strict_today_only": False,
    "needs_images": False,
    "needs_places": False,
    "needs_current_location": False,
    "needs_nearby_places": False,
    "needs_route": False,
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
    "route_uses_current_location": False,
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
_CAPABILITY_SKILLS = capability_skill_map()
_SKILL_PLAN_FLAGS = skill_plan_flags()
_SKILL_DEGRADATION_CAPABILITIES = skill_degradation_capabilities()


def apply_runtime_skill_policy(
    plan: dict[str, Any],
    disabled_skills: Iterable[Any],
) -> dict[str, Any]:
    """Apply persisted Skill switches after semantic planning.

    The model only states which capabilities the request needs. It never sees
    or judges enable switches. This logic-layer gate either blocks before graph
    construction or removes only an independent calendar enhancement while
    preserving a requested route.
    """
    reconciled = reconcile_capability_contract(plan)
    if reconciled.get("reuse_latest_route"):
        # This is a model-authored reference-resolution decision, not phrase
        # matching. A verified route already exists in workspace state, so the
        # current goal consumes it through the calendar adapter and must not
        # re-run Tencent place search or directions.
        reconciled["needs_route"] = False
        reconciled["route_stops"] = []
        reconciled["_capabilities"] = [
            capability
            for capability in (reconciled.get("_capabilities") or [])
            if str(capability) != "route"
        ]
    reconciled["blocked_skill"] = ""
    disabled = {
        str(skill_id or "").strip()
        for skill_id in disabled_skills
        if str(skill_id or "").strip() in KNOWN_SKILLS
    }
    required_skills: list[str] = []
    for capability in _normalize_preflight_capabilities(
        reconciled.get("_capabilities") or []
    ):
        skill_id = _CAPABILITY_SKILLS.get(capability)
        if skill_id and skill_id in disabled and skill_id not in required_skills:
            required_skills.append(skill_id)
    for skill_id, flags in _SKILL_PLAN_FLAGS.items():
        if (
            skill_id in disabled
            and any(bool(reconciled.get(flag)) for flag in flags)
            and skill_id not in required_skills
        ):
            required_skills.append(skill_id)
    if not required_skills:
        return reconciled

    # A Skill may declare that it is an independent enhancement of another
    # capability. When only that enhancement is disabled, preserve the useful
    # primary result and remove the disabled Skill from this turn.
    if len(required_skills) == 1:
        omitted_skill = required_skills[0]
        active_capabilities = set(_normalize_preflight_capabilities(
            reconciled.get("_capabilities") or []
        ))
        optional_capabilities = set(_normalize_preflight_capabilities(
            reconciled.get("optional_capabilities") or []
        ))
        omitted_capabilities = {
            capability
            for capability in active_capabilities
            if _CAPABILITY_SKILLS.get(capability) == omitted_skill
        }
        degradable = bool(
            active_capabilities
            & set(_SKILL_DEGRADATION_CAPABILITIES.get(omitted_skill, ()))
            and omitted_capabilities
            and omitted_capabilities.issubset(optional_capabilities)
        )
    else:
        omitted_skill = ""
        degradable = False
    if degradable:
        for flag in _SKILL_PLAN_FLAGS.get(omitted_skill, ()):
            reconciled[flag] = False
        reconciled["_capabilities"] = [
            capability
            for capability in (reconciled.get("_capabilities") or [])
            if _CAPABILITY_SKILLS.get(str(capability)) != omitted_skill
        ]
        reconciled["_runtime_omitted_skills"] = [omitted_skill]
        return reconciled

    reconciled["blocked_skill"] = required_skills[0]
    reconciled["_runtime_omitted_skills"] = required_skills
    return reconciled


class PlannedRouteStop(BaseModel):
    """One user-specified stop preserved verbatim and in user order."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        default="",
        description=(
            "The standalone place name exactly as written by the user. If "
            "route_uses_current_location is true, omit the implicit browser "
            "origin and list only destinations in their requested order."
        ),
    )
    near_query: str = Field(
        default="",
        description=(
            "The separate anchor place only when query is a category or brand "
            "described as near another place; otherwise empty."
        ),
    )


class PlannedClarificationField(BaseModel):
    """One minimal field required to resume the original request."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable short ASCII identifier")
    label: str = Field(description="Natural user-facing question label")
    type: str = Field(
        default="text",
        description="One of single, multi, boolean, text, date, time, datetime",
    )
    required: bool = True
    options: list[str] = Field(
        default_factory=list,
        description="Finite options for single/multi; empty for other field types",
    )
    placeholder: str = ""


class CapabilityPlan(BaseModel):
    """Validated semantic plan returned by LangChain structured output."""

    model_config = ConfigDict(extra="forbid")

    prompt_topics: list[str] = Field(
        default_factory=list,
        description=(
            "Only later execution-policy topics needed for this turn. Choose "
            "only topic IDs declared by the runtime Skill index in the system prompt."
        ),
    )
    capabilities: list[str] = Field(
        description=(
            "Independent semantic checksum of every user-required capability. "
            "Always return this field, even when empty. Choose only capability "
            "IDs declared by the runtime Skill index in the system prompt. "
            "A request to calculate "
            "or plan real travel always includes route, including when embedded "
            "inside a schedule request. Asking for an editable calendar proposal "
            "or card includes calendar_context and calendar_action even when the "
            "user says not to write it without confirmation, because the action "
            "creates the proposal rather than committing it. This list and the "
            "needs_* fields must describe the same complete goal."
        ),
    )
    needs_clarification: bool = False
    needs_web_search: bool = False
    strict_today_only: bool = False
    needs_images: bool = Field(
        default=False,
        description=(
            "True when real searched images materially improve comprehension by "
            "showing a concrete event, person, product, place, or reported subject, "
            "even if the user did not explicitly request images. False for purely "
            "abstract reasoning, simple calculations, or decorative-only imagery."
        ),
    )
    needs_places: bool = False
    needs_current_location: bool = Field(
        default=False,
        description=(
            "True when the user directly asks where they currently are or asks "
            "the assistant to identify the fresh browser location."
        ),
    )
    needs_nearby_places: bool = False
    needs_route: bool = Field(
        default=False,
        description=(
            "True for every request to calculate or plan real travel between "
            "places, including a route embedded inside a calendar proposal."
        ),
    )
    needs_map_action: bool = False
    needs_calendar_action: bool = Field(
        default=False,
        description=(
            "True when the user asks to create, edit, delete, or prepare an "
            "editable calendar proposal/card. A request not to write before "
            "confirmation still requires this proposal action."
        ),
    )
    needs_calendar_context: bool = Field(
        default=False,
        description=(
            "True when answering requires reading the user's current schedules, "
            "including calendar create, update, delete, conflict, or agenda questions."
        ),
    )
    needs_meeting_action: bool = False
    needs_workflow_action: bool = False
    needs_image_generation: bool = False
    needs_papers: bool = Field(
        default=False,
        description=(
            "True only when the user's goal explicitly requests academic papers or "
            "literature, or when scholarly-index verification is indispensable to "
            "the requested result. General news, industry updates, and current "
            "developments do not require papers merely because their subject is technical."
        ),
    )
    needs_deep_reasoning: bool = Field(
        default=False,
        description=(
            "True only for genuinely multi-step open-ended reasoning. Fixed JSON, "
            "tool arguments, routing, acknowledgements, and ordinary chat use Flash."
        ),
    )
    needs_followups: bool = Field(
        default=False,
        description=(
            "True for a substantive answer when two or three natural adjacent "
            "questions would help the user continue. False for clarification, "
            "errors, pure acknowledgements, greetings, or exhausted tasks."
        ),
    )
    needs_memory_extraction: bool = Field(
        default=False,
        description=(
            "True only when the user explicitly states a durable non-sensitive "
            "preference or fact that may help future turns."
        ),
    )
    needs_opportunity_review: bool = Field(
        default=False,
        description=(
            "True only when the completed turn may justify a useful proactive "
            "next-step notification. Runtime policy decides whether that "
            "capability is available."
        ),
    )
    use_memory_context: bool = Field(
        default=False,
        description=(
            "True only when confirmed long-term memory is directly relevant to "
            "the current request."
        ),
    )
    search_query: str = ""
    image_query: str = ""
    nearby_query: str = Field(
        default="",
        description=(
            "For a nearby-place request, the short provider category to find, "
            "such as 餐厅、景点、咖啡馆、酒店. Empty otherwise."
        ),
    )
    nearby_anchor_query: str = Field(
        default="",
        description=(
            "Explicit real-world anchor for a nearby search. Empty when the "
            "browser current location is the anchor."
        ),
    )
    nearby_anchor_queries: list[str] = Field(
        default_factory=list,
        description="Every explicit alternative nearby anchor, in user order",
    )
    nearby_uses_current_location: bool = Field(
        default=False,
        description=(
            "True when the user semantically means their browser current "
            "location as the nearby-search anchor, whether or not a fix is available."
        ),
    )
    paper_author: str = Field(
        default="",
        description=(
            "Canonical publication signature for the requested person. When "
            "the user gives a Chinese name, return the most likely Latin "
            "given-name/family-name signature; do not include institution or dates."
        ),
    )
    paper_institution: str = Field(
        default="",
        description=(
            "Canonical English institution name when the user uses affiliation "
            "to identify an author; empty when no institution was explicitly "
            "supplied in the current request or established dialogue. Never fill "
            "this from model knowledge, cached papers, or search popularity."
        ),
    )
    paper_identity_evidence_supplied: bool = Field(
        default=False,
        description=(
            "True only when the user explicitly supplied, or the established "
            "dialogue explicitly contains, identity evidence that distinguishes "
            "the requested academic author, such as an institution, laboratory, "
            "research field, profile URL, or publication title. Model knowledge, "
            "cached papers, and a guessed affiliation do not count."
        ),
    )
    paper_identity_globally_unambiguous: bool = Field(
        default=False,
        description=(
            "True only for an academic identity that is effectively unique "
            "worldwide even without any user-supplied qualifier. Keep false when "
            "plausible scholarly namesakes may exist; popularity is not uniqueness."
        ),
    )
    paper_topic: str = Field(
        default="",
        description=(
            "Only an explicitly requested research subject used to filter paper "
            "titles. Empty for an author/institution/date/count-only request; "
            "never copy the whole user request into this field."
        ),
    )
    paper_year: int = 0
    paper_year_from: int = Field(
        default=0,
        description="Inclusive start year for a range such as recent N years; 0 if absent.",
    )
    paper_year_to: int = Field(
        default=0,
        description="Inclusive end year for a range such as recent N years; 0 if absent.",
    )
    paper_limit: int = 0
    route_stops: list[PlannedRouteStop] = Field(
        default_factory=list,
        description=(
            "For a route request, every explicitly requested stop in exact order. "
            "Never omit a user-stated origin, intermediate stop, or destination. "
            "When route_uses_current_location is true, omit only that implicit "
            "browser origin. Empty otherwise."
        ),
    )
    route_city: str = Field(
        default="全国",
        description="Explicit city shared by the route stops, or 全国 when not established",
    )
    route_mode: str = Field(
        default="default",
        description=(
            "Explicit travel mode: driving, transit, walking, or bicycling. "
            "Use default when the user did not specify one."
        ),
    )
    route_strategy: str = Field(
        default="default",
        description=(
            "Explicit route preference: time_then_cost, least_time, or least_cost. "
            "Use least_time only when the user explicitly prioritizes the shortest "
            "duration. Asking for actual travel time or calendar timing is not a "
            "route preference. Use default when no preference was stated."
        ),
    )
    route_uses_current_location: bool = Field(
        default=False,
        description=(
            "True when the user semantically means their browser current "
            "location as the implicit route origin, whether or not a fix is available."
        ),
    )
    reuse_latest_route: bool = Field(
        default=False,
        description=(
            "True when the current request asks to reuse the most recent "
            "provider-verified route, such as turning that route into calendar "
            "items. In that case do not plan a new route or repeat its stops."
        ),
    )
    route_calendar_hint: str = Field(
        default="",
        description=(
            "Only the user's explicit date/time window or per-stop duration "
            "attached to a newly planned route, preserved for a later calendar "
            "continuation. Empty when the user supplied none."
        ),
    )
    optional_capabilities: list[str] = Field(
        default_factory=list,
        description=(
            "Capabilities that are helpful enhancements but not required for "
            "the user's present goal. Use installed capability IDs only. A "
            "direct request to create, edit, or delete calendar items is never "
            "optional; an unsolicited calendar add-on to a route may be."
        ),
    )
    place_resolution_target: str = Field(
        default="none",
        description=(
            "Set to calendar when an unverified real-world place belongs to a "
            "calendar create/update request, even if the place is misspelled, "
            "ambiguous, or lacks a city. Otherwise none."
        ),
    )
    clarification_title: str = Field(
        default="",
        description="Compact card title when needs_clarification is true",
    )
    clarification_prompt: str = Field(
        default="",
        description="Why the minimum missing information is required",
    )
    clarification_fields: list[PlannedClarificationField] = Field(
        default_factory=list,
        description=(
            "Only fields whose absence blocks every safe useful result. "
            "Empty unless needs_clarification is true."
        ),
    )


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def _decode_capability_plan(content: Any) -> dict[str, Any] | None:
    if isinstance(content, BaseModel):
        raw = content.model_dump()
    elif isinstance(content, dict):
        raw = content
    else:
        text = _text(content).strip()
        fenced = re.search(r"\{[\s\S]*\}", text)
        if fenced:
            text = fenced.group(0)
        try:
            raw = json.loads(text)
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
    plan["route_uses_current_location"] = bool(
        plan.get("needs_route") and raw.get("route_uses_current_location")
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
            "label": str(item.get("label") or "请补充").strip()[:80],
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
        plan["clarification_title"] = "请确认论文作者"
        plan["clarification_prompt"] = (
            f"“{plan['paper_author']}”可能对应多位研究者，请补充一条身份线索后我再检索。"
        )
        plan["clarification_fields"] = [{
            "id": "paper-author-identity",
            "label": "作者的单位、研究方向或个人主页",
            "type": "text",
            "required": True,
            "options": [],
            "placeholder": "例如：复旦大学、软件工程，或个人主页链接",
        }]
    return plan


def parse_capability_plan(content: Any) -> dict[str, Any]:
    return _decode_capability_plan(content) or dict(DEFAULT_PLAN)


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
for _topic, _summary in PROMPT_TOPIC_SUMMARIES.items():
    PLANNER_PROMPT_DETAILS.setdefault(
        _topic,
        f"【{_topic}】Use only the installed Skill capability boundaries: {_summary}",
    )

_PROMPT_TOPIC_IDS = ", ".join(PROMPT_TOPIC_SUMMARIES)
_CAPABILITY_IDS = ", ".join(capability_skill_map())


class PromptTopicSelection(BaseModel):
    """Semantic retrieval result for second-stage prompt fragments."""

    model_config = ConfigDict(extra="forbid")

    topics: list[str] = Field(
        default_factory=list,
        description=(
            "Every prompt topic whose operational details may be needed. "
            f"Choose only from the installed topic IDs: {_PROMPT_TOPIC_IDS}."
        ),
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
        description=(
            "Every prompt topic whose operational details may be needed. "
            f"Choose only from the installed topic IDs: {_PROMPT_TOPIC_IDS}."
        ),
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description=(
            "Every user-required capability, independently of prompt topics. "
            f"Choose only from installed capability IDs: {_CAPABILITY_IDS}. Include "
            "route for every request to calculate or plan real travel, even when "
            "it is part of a schedule request. Include calendar_context and "
            "calendar_action when the user asks for an editable calendar proposal "
            "or card; 'do not write yet' means propose for confirmation, not omit "
            "the calendar capability."
        ),
    )


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
) -> dict[str, Any]:
    """Jointly decide readiness and retrieve prompt topics without phrase rules."""
    catalog = "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in PROMPT_TOPIC_SUMMARIES.items()
    )
    prompt = (
        "You are the product-wide semantic preflight. Do not answer the user. "
        "In this single pass, both evaluate required-input readiness and select "
        "the dynamic prompt topics needed by the later capability planner. Also "
        "return every user-required capability in the fixed capabilities list; "
        "topics retrieve instructions, while capabilities preserve the complete "
        "goal if the later argument planner is slow or omits a dependent action. "
        "Planning or calculating real travel requires route even when combined "
        "with a schedule. An editable calendar proposal or card requires both "
        "calendar_context and calendar_action even when the user says not to "
        "commit it yet; the action is itself the confirmation proposal. "
        "Build the task's dependency graph from meaning: identify every source "
        "object, target object, or field the user explicitly makes necessary, "
        "then determine whether each is actually present in the current message, "
        "attached image/document context, or clarification supplement. Do not "
        "mistake the instruction sentence itself for a source object it merely "
        "refers to. Set needs_clarification=true only when an absent dependency "
        "blocks every safe useful result, or when a real side-effect target cannot "
        "be uniquely identified. A dependency must be entailed by the user's goal; "
        "never invent an account, provider, output format, preference, or other "
        "implementation choice that the user did not make necessary. If a safe "
        "default, assumptions, or useful options can satisfy the request, return "
        "false. Before returning true, adversarially check that every safe useful "
        "result really is blocked. When true, provide one compact card "
        "with only the minimum fields: finite choices before free text, and no "
        "optional preference questions. The request-scoped location context below "
        "is authoritative: when it says a browser location is available, that "
        "already satisfies a current-location dependency; never ask for it again. "
        "A real-world place spelling, alias, same-name branch, or uncertain POI "
        "is not a missing user dependency before the place provider runs: select "
        "the maps topic and return needs_clarification=false so the Tencent-backed "
        "place/route tool can resolve it, auto-use near-certain evidence, offer "
        "finite provider candidates, or request free text when no evidence exists. "
        "Do not ask the user to pre-correct or pre-disambiguate a supplied place. "
        "Academic author identity is different: if a paper request identifies a "
        "person only by a name or honorific and multiple real researchers could "
        "plausibly match, selecting one would corrupt every result. In that case "
        "return one clarification card asking for the minimum identity evidence "
        "(normally institution or research field). Do not silently choose the "
        "most prolific namesake. If the conversation already establishes that "
        "evidence, do not ask again."
        "\nSelect every relevant topic from the catalog, including combinations, "
        "and omit unrelated topics. Classification is semantic, never based on "
        "literal keyword or phrase matching.\n"
        f"Available prompt topics:\n{catalog}"
        f"\nRequest-scoped location context: {str(location_context or 'not supplied')[:1000]}"
        f"\nReference images attached: {bool(has_reference_images)}"
        f"\nDocument context attached: {bool(has_document_context)}"
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
            }) or dict(DEFAULT_PLAN)
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
            }
    except Exception:
        pass
    return {
        "needs_clarification": False,
        "clarification_title": "",
        "clarification_prompt": "",
        "clarification_fields": [],
        "_prompt_topics": list(PLANNER_PROMPT_DETAILS),
        "_preflight_capabilities": [],
    }


async def select_prompt_context(
    model,
    user_message: str,
    *,
    has_reference_images: bool = False,
    has_document_context: bool = False,
) -> dict[str, Any]:
    """Run semantic prompt-fragment retrieval."""
    catalog = "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in PROMPT_TOPIC_SUMMARIES.items()
    )
    prompt = (
        "You retrieve prompt fragments for a later capability planner. "
        "Read the complete user goal semantically; do not answer it. Select every "
        "topic whose operational boundary may be needed, including combinations, "
        "and omit unrelated topics. An unfamiliar phrasing must still be classified "
        "by meaning rather than literal words.\n"
        f"Available topics:\n{catalog}\n"
        f"Reference images attached: {bool(has_reference_images)}\n"
        f"Document context attached: {bool(has_document_context)}"
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
    # Failure must preserve completeness, never fall back to phrase matching.
    return {"topics": tuple(PLANNER_PROMPT_DETAILS)}


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
) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    prompt = f"""你是 FLORIS 单轮语义计划器，只填写给定 schema，不回答用户。当前北京时间日期：{today}。
总则：
- 在一次结构化输出中同时完成意图、依赖、必要信息、能力参数和 prompt_topics 规划；不要把同一问题留给另一个预检模型。理解完整目标，可同时选择多个能力；非必要字段保持默认值。capabilities 必须始终返回，并独立列出完成用户完整目标必需的每一项固定枚举能力；它与 needs_* 是互相校验的冗余协议，两者必须一致，不能因为参数还不完整就漏掉能力。只判断目标需要什么，不判断任何 Skill 是否开启；开关由运行时逻辑层处理。
- 只有缺失信息会阻断所有安全有用结果，或真实副作用对象无法唯一确定时，才设置 needs_clarification=true，并把其他 needs_* 设为 false。此时必须同时填写 clarification_title、clarification_prompt 和最少 clarification_fields，让系统直接生成主动卡片；不得只让最终模型用普通文本追问。偏好未决定时直接交给主模型给方案，不要澄清。
- 用户只是探索思路、比较假设方案，且目的地、预算、同行或节奏尚未决定时，不需要外部事实、地点核验或地图；保持所有 needs_* 为 false，让主模型直接给 2–3 套假设方案。只有用户要求当前信息、来源、真实地点推荐或可执行路线时才选择相应能力。
- 现实地点可能有错字、同名或缺城市时，不得在调用地点服务之前设置 needs_clarification。先选择地点/路线能力；地点工具会根据真实腾讯候选决定直接采用、单选或填空。
- 论文作者身份不能按“最热门同名作者”猜测。若用户只给姓名或称谓、上下文没有单位/研究方向等身份线索，且现实中可能存在多个研究者，设置 needs_clarification=true，用一张主动卡只收集能区分身份的最少信息；已有足够身份线索时不得重复询问。
- 用户要求把上一轮已核实路线写入日程时，设置 reuse_latest_route=true，只选择 calendar_context 和 calendar_action，不得重新选择 route 或抄写历史站点到 route_stops。新路线中用户明确给出的日期、时段、出发时刻或单站停留时长原样压缩到 route_calendar_hint，供后续日程续写；没有则留空。
- optional_capabilities 只列不影响当前核心目标的增强能力。用户直接要求写入、修改或删除日程时 calendar_context/calendar_action 绝不属于可选；只有路线请求中系统可额外主动附送日程提案时才可标为可选。
- 能力语义索引由已安装 Skill 的 Manifest 动态提供。只能选择索引中声明的 capability id；
  下面只附本轮候选能力的详细边界。prompt_topics 只加载判断边界，绝不能据此执行能力；
  只有 capabilities 与 needs_* 才是执行协议。一个主题被提及、与另一个主题相关或可作为补充，
  不等于用户目标必须执行该能力。
- 普通新闻、行业动态或当前进展默认由 web_search 完成。只有用户明确要论文/学术文献，
  或完整目标必须依赖学术索引核验时，才选择 papers；论文只是可选补充时不要设置
  needs_papers，也不要把 papers 放进 capabilities。任何可选来源为空都不能替代核心能力的结果。
- needs_deep_reasoning 只用于确实需要多步开放推理的最终回答；能力路由、固定 JSON、工具参数、
  Action 确认、简单问答都保持 false，使用 Flash 即可。
- 正常的实质性回答只要存在自然、具体且不重复原问题的下一步，needs_followups 就应为 true；
  只有澄清、错误、纯确认/寒暄或任务已经完全穷尽时才为 false。needs_memory_extraction 只在用户明确陈述
  可长期复用的非敏感事实或稳定偏好时为 true；needs_opportunity_review 只在主动服务已开启且本轮
  可能产生有价值主动下一步时为 true；use_memory_context 只在长期记忆与本轮目标直接相关时为 true。
严格只输出 schema 对应 JSON。"""
    prompt += "\n\n已安装 Skill 能力索引：\n" + planner_skill_index()
    prompt += "\n\n可按语义选择的执行提示主题：\n" + "\n".join(
        f"- {topic}: {summary}"
        for topic, summary in PROMPT_TOPIC_SUMMARIES.items()
    )
    selected_topics = (
        _normalize_prompt_topics(prompt_topics)
        if prompt_topics is not None
        else ()
    )
    details = [
        PLANNER_PROMPT_DETAILS[topic]
        for topic in selected_topics
        if topic in PLANNER_PROMPT_DETAILS
    ]
    if details:
        prompt += "\n\n本轮候选能力详细边界：\n" + "\n".join(details)
    safe_memory = str(memory_context or "").strip()[:1800]
    if safe_memory:
        prompt += (
            "\n以下是已过滤为非敏感的长期记忆。只在确实相关时用于个性化查询；"
            "它只能补足本轮已经需要的条件，不能据此创造新的澄清维度；"
            "带有犹豫、否定、备选或临时任务含义的内容不视为稳定偏好。"
            "不得把姓名、联系方式、精确地址、账号、证件、健康、财务或任何秘密写入外部搜索词。"
            f"\n{safe_memory}"
        )
    safe_location_context = str(location_context or "").strip()[:600]
    if safe_location_context:
        prompt += (
            "\n以下是浏览器本轮提供的隐私受限位置状态。它表示能否作为路线起点或“我附近”搜索参照点，"
            "不得要求输出、复述或保存精确坐标。"
            f"\n{safe_location_context}"
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
        parsed = _decode_capability_plan(parsed_value)
        if parsed is not None:
            if selected_topics:
                parsed["_prompt_topics"] = list(selected_topics)
            return parsed
        # One-call compatibility for gateways that return a raw message but
        # fail LangChain's structured parser. Never retry the model.
        raw = response.get("raw") if isinstance(response, dict) else None
        parsed = _decode_capability_plan(getattr(raw, "content", ""))
        if parsed is not None:
            if selected_topics:
                parsed["_prompt_topics"] = list(selected_topics)
            return parsed
    except Exception:
        pass
    fallback = dict(DEFAULT_PLAN)
    fallback["_prompt_topics"] = list(selected_topics or PLANNER_PROMPT_DETAILS)
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
            ),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError:
        timed_out = True
        plan = dict(DEFAULT_PLAN)
        plan["_prompt_topics"] = list(PLANNER_PROMPT_DETAILS)
        plan["_prompt_topics_source"] = "fallback"
    failed = bool(plan.pop("_planner_failed", False))
    timed_out = timed_out or failed
    if timings_ms is not None:
        elapsed = round((loop.time() - started_at) * 1000)
        timings_ms["semantic_plan"] = elapsed
        timings_ms["semantic_plan_timed_out"] = timed_out
        timings_ms["capability_planning_total"] = elapsed
    return plan, timed_out
