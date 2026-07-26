"""Verified production tools for the Makers travel workspace."""

from __future__ import annotations

import asyncio
import copy
import difflib
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._shared.tencent_location import (
    plan_verified_route as provider_plan_route,
    reverse_geocode as provider_reverse_geocode,
    search_places as provider_search_place_candidates,
    search_verified_places_bounded as provider_search_places,
    search_verified_places_nearby as provider_search_places_nearby,
)
from .._shared.web_media import collect_page_images as provider_collect_page_images
from .._shared.rich_search import evidence_for_model, rich_search as provider_rich_search
from .._shared.data_version import namespace as data_namespace
from .._shared.side_effects import generate_image as provider_generate_image, resolve_image_reference
from .._shared.arxiv import search_arxiv as provider_search_arxiv
from .._shared.proactive import load_proactive_state, propose_workflow as create_workflow_proposal, save_proactive_state
from .._shared.provider_metering import record_provider_usage, record_vision_diagnostics
from .._shared.place_cache import load_place_cache, save_place_cache
from .._shared.route_cache import load_route_cache, save_route_cache
from .._shared.workspace import (
    begin_action_execution,
    apply_calendar_changes,
    calendar_change_warnings,
    finish_provider_call,
    get_action,
    image_versions,
    load_user_workspace,
    meeting_action_payload,
    new_action,
    put_action,
    save_user_workspace,
    seal_action_snapshot,
    start_provider_call,
    validate_calendar_change_window,
)
from ._location_intent import is_browser_current_location_reference


class ClarificationFieldInput(BaseModel):
    """Strong schema shown to the model for every clarification field."""

    id: str = Field(description="Stable semantic field id derived from the unresolved part of the user's request")
    label: str = Field(
        description=(
            "Short user-visible question grounded in the current request, recent dialogue, "
            "or a directly relevant safe memory; never invent a generic profile question"
        ),
    )
    type: Literal["single", "multi", "boolean", "text", "date", "time", "datetime"] = Field(
        description=(
            "Interaction type. Prefer single/multi for finite choices, boolean for yes/no, "
            "date for a missing date, time when the date is already known, datetime when both "
            "are missing, and text only when the answer cannot be enumerated."
        ),
    )
    required: bool = Field(default=True, description="Whether the user must answer this field")
    options: list[str] = Field(
        default_factory=list,
        description="Two to eight natural-language options for single or multi; empty for other types",
    )
    placeholder: str = Field(
        default="",
        description="Short example only for a text field; do not use it for choices or dates",
    )


class RouteStopInput(BaseModel):
    """A single ordered route stop exposed to the model as a strict schema."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=160,
        description=(
            "Standalone place name or resolved dialogue reference. The first "
            "list item is the origin; preserve every user-requested stop."
        ),
    )
    near_query: str = Field(
        default="",
        max_length=160,
        description=(
            "Separate anchor for a place described relative to another place, "
            "for example query=锦江之星 and near_query=北京301医院."
        ),
    )


class RoutePlanInput(BaseModel):
    """Validated LangChain input contract for two-point and multi-stop routes."""

    model_config = ConfigDict(extra="forbid")

    origin_query: str = Field(
        default="",
        max_length=160,
        description="Origin for a two-place route; do not use when ordered_stops is supplied.",
    )
    destination_query: str = Field(
        default="",
        max_length=160,
        description="Destination for a two-place route; do not use when ordered_stops is supplied.",
    )
    city: str = Field(default="全国", max_length=80)
    origin_near_query: str = Field(default="", max_length=160)
    destination_near_query: str = Field(default="", max_length=160)
    nearby_radius_meters: int = Field(default=5_000, ge=500, le=20_000)
    route_mode: Literal["default", "driving", "transit", "walking", "bicycling"] = Field(
        default="default",
        description=(
            "Travel mode explicitly requested by the user. Use default to honor "
            "the user's saved map preference."
        ),
    )
    route_strategy: Literal[
        "default", "time_then_cost", "least_time", "least_cost",
    ] = Field(
        default="default",
        description=(
            "Explicit route tradeoff. Use default when unstated; the saved and "
            "learned preference then applies."
        ),
    )
    use_current_location_as_origin: bool = Field(
        default=False,
        description=(
            "Use the fresh browser location supplied for this request as the origin. "
            "Never invent coordinates or use it when the user stated another origin."
        ),
    )
    ordered_stops: list[RouteStopInput] = Field(
        default_factory=list,
        min_length=0,
        max_length=12,
        description=(
            "For a multi-stop trip, every stop in the user's exact order. "
            "The first item must be the stated origin and the last item the destination."
        ),
    )

    @model_validator(mode="after")
    def validate_endpoints(self):
        if self.ordered_stops:
            if len(self.ordered_stops) < 2 and not self.use_current_location_as_origin:
                raise ValueError("有序路线至少需要起点和终点")
            return self
        if (
            not self.destination_query.strip()
            or (not self.origin_query.strip() and not self.use_current_location_as_origin)
        ):
            raise ValueError("两点路线必须同时提供起点和终点")
        return self


def preserve_planned_route_stops(
    model_stops: list[tuple[str, str]],
    planned_stops: list[dict[str, str]] | None,
    user_message: str = "",
) -> list[tuple[str, str]]:
    """Keep the capability planner's ordered, user-authored stop handoff.

    The capability model sees the original user goal and records its ordered
    stop list. The later fixed-schema model may otherwise silently correct a
    typo or choose a branch before the location provider sees the literal
    query. A complete planner handoff therefore wins wholesale; Tencent search
    remains the only component allowed to resolve aliases and corrections.
    """
    normalized_plan = [
        (
            str(item.get("query") or "").strip(),
            str(item.get("near_query") or "").strip(),
        )
        for item in (planned_stops or [])
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ][:12]
    if len(normalized_plan) >= 2:
        return normalized_plan

    source = str(user_message or "")

    def literal(value: str) -> str:
        query = str(value or "").strip()
        if not query or not source or query in source:
            return query
        if (
            not 2 <= len(query) <= 24
            or not re.fullmatch(r"[\w\u4e00-\u9fff]+", query)
            or not re.search(r"[\u4e00-\u9fff]", query)
        ):
            return query
        candidates = []
        for chunk_match in re.finditer(r"[\w\u4e00-\u9fff]+", source):
            chunk = chunk_match.group(0)
            if len(chunk) < len(query):
                continue
            for index in range(len(chunk) - len(query) + 1):
                candidate = chunk[index:index + len(query)]
                score = difflib.SequenceMatcher(None, query, candidate).ratio()
                aligned = sum(
                    left == right for left, right in zip(query, candidate)
                ) / len(query)
                candidates.append((
                    score,
                    aligned,
                    chunk_match.start() + index,
                    candidate,
                ))
        if not candidates:
            return query
        score, _aligned, _position, candidate = max(
            candidates,
            key=lambda item: (item[0], item[1], -item[2]),
        )
        threshold = 0.64 if len(query) == 3 else 0.72
        return candidate if score >= threshold else query

    return [
        (literal(query), literal(near_query))
        for query, near_query in model_stops
    ]


def _parse_datetime(value: str) -> datetime:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
    return str(content or "")


def _clarification_action(
    conversation_id: str,
    *,
    title: str,
    prompt: str,
    fields: list[dict[str, Any]],
) -> str:
    prompt_id = hashlib.sha256(
        f"{conversation_id}:{time.time_ns()}:{title}".encode()
    ).hexdigest()[:16]
    return json.dumps({
        "ui_action": "clarification_action",
        "clarification": {
            "id": f"clarify-{prompt_id}",
            "title": str(title).strip()[:120],
            "prompt": str(prompt).strip()[:300],
            "fields": fields[:8],
        },
    }, ensure_ascii=False)


def _normalized_place_name(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _is_browser_current_location_anchor(value: Any) -> bool:
    """Recognize only explicit first-person/current-position map anchors.

    The value is never sent to Tencent as a POI query. It is either replaced
    with the fresh, request-scoped browser fix or rejected truthfully.
    """
    return is_browser_current_location_reference(value)


def _verified_candidate_matches(
    query: str,
    place: dict[str, Any],
    city: str,
) -> bool:
    """Reject provider fallbacks that do not match the requested POI or city."""
    clean_query = _normalized_place_name(query)
    clean_name = _normalized_place_name(place.get("name"))
    if not clean_query or not clean_name:
        return False
    matcher = difflib.SequenceMatcher(None, clean_query, clean_name)
    edits = {tag for tag, *_rest in matcher.get_opcodes() if tag != "equal"}
    correction = place.get("query_correction")
    correction_query = (
        _normalized_place_name(correction.get("original_query"))
        if isinstance(correction, dict)
        else ""
    )
    correction_evidence = (
        str(correction.get("evidence") or "")
        if isinstance(correction, dict)
        else ""
    )
    verified_correction = bool(
        correction_query == clean_query
        and correction_evidence.startswith("tencent_")
    )
    query_bigrams = {
        clean_query[index:index + 2]
        for index in range(max(0, len(clean_query) - 1))
    }
    descriptive_coverage = (
        sum(part in clean_name for part in query_bigrams) / len(query_bigrams)
        if query_bigrams
        else 0.0
    )
    typo_threshold = (
        0.64 if len(clean_query) == 3
        else 0.72 if len(clean_query) == 4
        else 0.76
    )
    likely_semantic_insertion = bool(edits and edits <= {"insert", "delete"})
    if not (
        clean_query in clean_name
        or clean_name in clean_query
        or (
            len(clean_query) >= 5
            and descriptive_coverage >= 0.65
        )
        or (
            verified_correction
            and not likely_semantic_insertion
            and matcher.ratio() >= typo_threshold
        )
    ):
        return False
    clean_city = _normalized_place_name(city)
    if not clean_city or clean_city in {"全国", "中国"}:
        return True
    locality = _normalized_place_name(
        f"{place.get('city') or ''}{place.get('address') or ''}"
    )
    return clean_city in locality


def _rank_verified_workspace_matches(
    query: str,
    candidates: dict[str, Any],
    city: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Reuse provider-verified POIs for aliases before spending another call.

    This is generic name matching over existing Makers workspace records. It
    does not invent a place: every returned item already has a provider place
    id and still passes the same city/name validation as a fresh lookup.
    """
    clean_query = _normalized_place_name(query)
    ranked: list[tuple[int, float, str, dict[str, Any]]] = []
    for place_id, raw_place in candidates.items():
        if not isinstance(raw_place, dict) or not str(raw_place.get("place_id") or place_id):
            continue
        clean_name = _normalized_place_name(raw_place.get("name"))
        correction = raw_place.get("query_correction")
        corrected_from = (
            _normalized_place_name(correction.get("original_query"))
            if isinstance(correction, dict)
            else ""
        )
        clean_option = _normalized_place_name(_place_option_label(raw_place))
        if not (
            _verified_candidate_matches(query, raw_place, city)
            or clean_query == clean_option
            or clean_query == corrected_from
        ):
            continue
        exact_rank = (
            0 if clean_query == clean_option
            else 1 if clean_query == clean_name
            else 2 if clean_query == corrected_from
            else 3
        )
        similarity = difflib.SequenceMatcher(None, clean_query, clean_name).ratio()
        current_place = copy.deepcopy(raw_place)
        if (
            isinstance(current_place.get("query_correction"), dict)
            and corrected_from != clean_query
        ):
            # Correction evidence describes one specific spelling. A canonical
            # POI may be reused by later exact queries, but that must not make
            # the old typo appear in the new answer.
            current_place.pop("query_correction", None)
        ranked.append((
            exact_rank,
            -similarity,
            str(place_id),
            current_place,
        ))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    if (
        len(ranked) == 1
        and ranked[0][0] == 3
        and len(clean_query) <= 4
    ):
        # A short area/landmark query can be a substring of an unrelated
        # branch cached by an earlier nearby search (for example, a venue
        # whose branch suffix contains the area name). One such fuzzy hit is
        # not evidence of uniqueness: force a fresh provider lookup so the
        # user sees all real candidates, or a fill-in prompt when none exist.
        return []
    return [item[3] for item in ranked[:max(1, min(12, int(limit or 6)))]]


def _place_choice_field(field_id: str, label: str, places: list[dict[str, Any]]) -> dict[str, Any]:
    options = []
    for place in places[:6]:
        distance = place.get("distance_to_anchor_meters")
        distance_text = f" · 距参照地点约 {max(1, round(float(distance)))} 米" if isinstance(distance, (int, float)) else ""
        option = f"{place.get('name') or '未命名地点'}｜{place.get('address') or '地址未提供'}{distance_text}"
        if option not in options:
            options.append(option[:240])
    return {
        "id": field_id,
        "label": label,
        "type": "single",
        "required": True,
        "options": options,
    }


def _place_option_label(place: dict[str, Any]) -> str:
    return (
        f"{place.get('name') or '未命名地点'}｜"
        f"{place.get('address') or '地址未提供'}"
    )[:240]


def _place_resolution(
    query: str,
    places: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, str]:
    """Return the deterministic three-level decision for a side-effect place.

    Auto-use is deliberately limited to one exact provider match or one unique
    verified candidate. Multiple real POIs always require a finite choice;
    no candidates require free text.
    """
    clean_query = _normalized_place_name(query)
    exact = [
        place for place in places
        if _normalized_place_name(place.get("name")) == clean_query
    ]
    if len(exact) == 1:
        return "auto_use", exact[0], "unique_exact_provider_match"
    if len(places) == 1:
        correction = places[0].get("query_correction")
        return (
            "auto_use",
            places[0],
            "unique_verified_correction"
            if isinstance(correction, dict)
            else "unique_verified_candidate",
        )
    if places:
        return "choose", None, "multiple_verified_candidates"
    return "fill", None, "no_verified_candidate"


def _learned_route_preference(
    learning: dict[str, Any],
    key: str,
    allowed: set[str],
) -> str:
    counts = learning.get(key) if isinstance(learning, dict) else None
    if not isinstance(counts, dict):
        return ""
    ranked = sorted(
        (
            (str(value), max(0, int(count)))
            for value, count in counts.items()
            if str(value) in allowed
        ),
        key=lambda item: (-item[1], item[0]),
    )
    total = sum(count for _value, count in ranked)
    if not ranked or total < 3 or ranked[0][1] / total < 0.6:
        return ""
    return ranked[0][0]


async def verify_place_queries_parallel(
    provider: Callable[..., Awaitable[list[dict[str, Any]]]],
    map_key: str,
    queries: list[str],
    *,
    city: str = "全国",
    timeout_seconds: float = 10.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Verify independent model-selected places concurrently, preserving query order."""
    timeout = max(3.0, min(15.0, float(timeout_seconds)))

    async def verify(query: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            matches = await asyncio.wait_for(
                provider(map_key, query, city=city or "全国", limit=3),
                timeout=timeout,
            )
        except Exception:
            matches = []
        return query, matches

    results = await asyncio.gather(*(verify(query) for query in queries))
    selected: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    missing: list[str] = []
    for query, matches in results:
        verified_matches = [
            place for place in matches
            if isinstance(place, dict)
            and _verified_candidate_matches(query, place, city)
        ]
        if verified_matches:
            selected.append(verified_matches[0])
            all_candidates.extend(verified_matches)
        else:
            missing.append(query)
    return selected, all_candidates, missing


def build_production_tools(
    model, *, store=None, conversation_id: str = "", env: dict | None = None,
    paper_constraints: dict | None = None,
    temporal_context: dict[str, Any] | None = None,
    progressive_media: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    user_id: str = "local-user",
    initial_visual_references: list[str] | None = None,
    media_enabled: bool = True,
    planned_search_query: str = "",
    planned_image_query: str = "",
    search_cache_ttl_seconds: int = 86_400,
    search_cache_identity: str = "",
    search_result_limit: int = 8,
    search_image_limit: int = 2,
    parallel_image_search: bool = True,
    enabled_skills: set[str] | None = None,
    planned_route_stops: list[dict[str, str]] | None = None,
    route_user_message: str = "",
    planned_route_city: str = "全国",
    planned_route_mode: str = "default",
    planned_route_strategy: str = "default",
    planned_route_uses_current_location: bool = False,
    planned_calendar_place_resolution: bool = False,
    browser_current_location: dict[str, Any] | None = None,
    map_preferences: dict[str, Any] | None = None,
    proactive_preferences: dict[str, Any] | None = None,
    tracer: Any = None,
) -> list[StructuredTool]:
    runtime_env = env or {}
    paper_scope = paper_constraints or {}
    time_scope = temporal_context or {}
    map_scope = map_preferences or {}
    map_service_mode = str(map_scope.get("service_mode") or "balanced")
    map_place_result_limit = max(3, min(12, int(map_scope.get("place_result_limit") or 6)))
    map_route_stop_limit = max(2, min(12, int(map_scope.get("route_stop_limit") or 8)))
    map_search_timeout = max(10.0, min(55.0, float(map_scope.get("search_timeout_seconds") or 30)))
    map_preferred_route_mode = str(map_scope.get("preferred_route_mode") or "driving")
    if map_preferred_route_mode not in {"driving", "transit", "walking", "bicycling"}:
        map_preferred_route_mode = "driving"
    map_route_strategy = str(map_scope.get("route_strategy") or "time_then_cost")
    if map_route_strategy not in {"time_then_cost", "least_time", "least_cost"}:
        map_route_strategy = "time_then_cost"
    map_near_time_tolerance = max(
        0, min(30, int(map_scope.get("near_time_tolerance_minutes", 10) or 0)),
    )
    map_learn_route_preferences = bool(
        map_scope.get("learn_route_preferences", True)
    )
    map_parallelism = {"fast": 4, "balanced": 3, "complete": 2}.get(map_service_mode, 3)
    proactive_scope = proactive_preferences or {}
    travel_buffer_minutes = max(0, min(120, int(
        proactive_scope.get("travel_buffer_minutes")
        if proactive_scope.get("travel_buffer_minutes") is not None
        else 15
    )))
    route_gap_hours = max(1, min(8, int(proactive_scope.get("route_gap_hours") or 3)))
    provider_schedule_limit = max(2, min(12, int(
        proactive_scope.get("provider_schedule_limit") or 6
    )))
    # Per-request handoff: rich-search media can be consumed by image
    # generation without asking the model to copy fragile URLs between tools.
    turn_visual_references: list[str] = [
        str(item) for item in (initial_visual_references or [])
        if str(item).startswith(("https://", "data:image/"))
    ][:3]
    turn_image_group_id = ""
    rich_search_task: asyncio.Task | None = None
    rich_search_invocations = 0
    rich_search_provider_calls = 0

    async def _load_state() -> dict[str, Any]:
        return await load_user_workspace(store, conversation_id, user_id)

    async def _save_state(state: dict[str, Any]) -> dict[str, Any]:
        return await save_user_workspace(store, state, user_id)

    async def _record_map_call(source: str, map_key: str) -> None:
        if str(map_key or "").strip():
            await record_provider_usage(
                store, user_id, "tencent_maps", "requests", 1, source=source,
            )

    async def _traced_map_call(name: str, operation: str, call):
        span_method = getattr(tracer, "span", None)
        if not callable(span_method):
            return await call()

        async def run(span):
            result = await call()
            set_attributes = getattr(span, "set_attributes", None)
            if callable(set_attributes):
                attributes: dict[str, str | int | float | bool] = {
                    "maps.operation": operation,
                    "maps.service_mode": map_service_mode,
                    "maps.timeout_seconds": map_search_timeout,
                }
                if isinstance(result, list):
                    attributes["maps.result_count"] = len(result)
                elif isinstance(result, dict):
                    attributes["maps.provider"] = str(result.get("provider") or "unknown")
                    attributes["maps.result_count"] = len(result.get("places") or [])
                set_attributes(attributes)
            return result

        return await span_method(name, run, {
            "maps.operation": operation,
            "maps.service_mode": map_service_mode,
        })

    async def _search_places_metered(map_key: str, *args, **kwargs):
        query = str(args[0] if args else kwargs.get("query") or "")
        city = str(kwargs.get("city") or "全国")
        limit = int(kwargs.get("limit") or map_place_result_limit)
        cached = await load_place_cache(store, user_id, query, city, limit)
        if cached is not None:
            return cached
        try:
            places = await _traced_map_call(
                "maps.place_search",
                "place_search",
                lambda: asyncio.wait_for(
                    provider_search_places(map_key, *args, **kwargs),
                    timeout=map_search_timeout,
                ),
            )
        finally:
            await _record_map_call("chat_place_search", map_key)
        await save_place_cache(store, user_id, query, city, limit, places)
        return places

    async def _search_place_candidates_metered(map_key: str, *args, **kwargs):
        try:
            return await _traced_map_call(
                "maps.tencent_place_candidates",
                "tencent_place_candidates",
                lambda: provider_search_place_candidates(map_key, *args, **kwargs),
            )
        finally:
            await _record_map_call("chat_place_candidates", map_key)

    async def _search_places_nearby_metered(map_key: str, *args, **kwargs):
        try:
            return await _traced_map_call(
                "maps.nearby_search",
                "nearby_search",
                lambda: provider_search_places_nearby(map_key, *args, **kwargs),
            )
        finally:
            await _record_map_call("chat_nearby_search", map_key)

    async def _reverse_geocode_metered(map_key: str, location: dict[str, Any]):
        try:
            return await _traced_map_call(
                "maps.reverse_geocode",
                "reverse_geocode",
                lambda: asyncio.wait_for(
                    provider_reverse_geocode(map_key, location),
                    timeout=min(12.0, map_search_timeout),
                ),
            )
        finally:
            await _record_map_call("chat_reverse_geocode", map_key)

    async def _plan_route_metered(map_key: str, *args, **kwargs):
        try:
            return await _traced_map_call(
                "maps.tencent_route",
                "tencent_route",
                lambda: asyncio.wait_for(
                    provider_plan_route(map_key, *args, **kwargs),
                    timeout=min(18.0, max(8.0, 58.0 - map_search_timeout)),
                ),
            )
        finally:
            await _record_map_call("chat_route", map_key)

    async def get_current_location() -> str:
        """Describe the fresh browser location through Tencent reverse geocoding."""
        if browser_current_location is None:
            return _clarification_action(
                conversation_id,
                title="需要你的位置",
                prompt=(
                    "浏览器没有提供当前位置。你可以在浏览器设置中允许定位后重试，"
                    "也可以填写大致位置，我会用它继续附近推荐或路线规划。"
                ),
                fields=[{
                    "id": "manual_location",
                    "label": "你目前所在的位置或出发地",
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": "例如：北京市海淀区中关村，或吉林大学前卫南区",
                }],
            )
        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        try:
            resolved = await _reverse_geocode_metered(
                map_key,
                browser_current_location,
            )
        except Exception as exc:
            logging.warning("reverse geocode current location failed error=%s", exc)
            raise ValueError(
                "腾讯地图暂时无法把当前位置解析为地址，请稍后重试"
            ) from exc
        return json.dumps({
            "location_available": True,
            "location": resolved,
            "accuracy_meters": browser_current_location.get("accuracy_meters"),
            "response_constraint": (
                "只说明腾讯逆地址解析返回的地址、行政区和附近地标；"
                "不得输出经纬度，不得声称定位精度高于浏览器 accuracy_meters，"
                "也不得把本次位置写入日程或长期记忆。"
            ),
        }, ensure_ascii=False)

    async def search_places(
        query: str,
        city: str = "全国",
        limit: int = 10,
        purpose: Literal["browse", "calendar"] = "browse",
    ) -> str:
        """Search real places; calendar mode enforces auto/choose/fill resolution."""
        effective_purpose = (
            "calendar" if planned_calendar_place_resolution else purpose
        )
        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        selected_option = next(
            (
                place for place in candidates.values()
                if isinstance(place, dict)
                and _normalized_place_name(_place_option_label(place))
                == _normalized_place_name(query)
            ),
            None,
        )
        if effective_purpose == "calendar" and isinstance(selected_option, dict):
            return json.dumps({
                "places": [selected_option],
                "count": 1,
                "resolution": {
                    "decision": "auto_use",
                    "reason": "user_selected_verified_candidate",
                    "selected_place_id": selected_option.get("place_id"),
                },
            }, ensure_ascii=False)
        places = await _search_places_metered(
            str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or ""),
            query,
            city=city,
            limit=max(1, min(map_place_result_limit, int(limit))),
        )
        for place in places:
            candidates[str(place["place_id"])] = place
        # Keep the short-lived candidate set bounded even in a long conversation.
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])
        await _save_state(state)
        if effective_purpose != "calendar":
            return json.dumps({"places": places, "count": len(places)}, ensure_ascii=False)
        decision, selected, reason = _place_resolution(query, places)
        if decision == "auto_use" and isinstance(selected, dict):
            return json.dumps({
                "places": [selected],
                "count": 1,
                "resolution": {
                    "decision": decision,
                    "reason": reason,
                    "selected_place_id": selected.get("place_id"),
                },
            }, ensure_ascii=False)
        if decision == "choose":
            return _clarification_action(
                conversation_id,
                title="请选择日程地点",
                prompt=f"查到多个符合“{query}”的真实地点。请选择要写入日程的地点。",
                fields=[_place_choice_field(
                    "calendar_place",
                    "日程安排在哪个地点？",
                    places,
                )],
            )
        return _clarification_action(
            conversation_id,
            title="请补充日程地点",
            prompt=f"地点服务没有足够证据确认“{query}”。请填写更完整的名称或城市。",
            fields=[{
                "id": "calendar_place",
                "label": "日程的正确地点是什么？",
                "type": "text",
                "required": True,
                "options": [],
                "placeholder": f"例如：城市 + {query}",
            }],
        )

    async def search_places_batch(queries: list[str], city: str = "全国", limit_per_query: int = 3) -> str:
        """Verify every named destination independently and retain every candidate ID."""
        normalized = []
        seen_queries = set()
        for raw_query in queries or []:
            query = str(raw_query or "").strip()
            if query and query not in seen_queries:
                seen_queries.add(query)
                normalized.append(query)
        if not 1 <= len(normalized) <= map_route_stop_limit:
            raise ValueError(
                f"批量地点查询必须包含 1 到 {map_route_stop_limit} 个独立地点名称；"
                "可在设置的“地图与路线”中调整上限"
            )

        map_key = str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or "")
        groups = []
        all_places = []
        seen_ids = set()
        semaphore = asyncio.Semaphore(map_parallelism)

        async def search_one(query: str) -> dict[str, Any]:
            try:
                async with semaphore:
                    places = await _search_places_metered(
                        map_key,
                        query,
                        city=city,
                        limit=max(1, min(map_place_result_limit, int(limit_per_query))),
                    )
                return {"query": query, "places": places}
            except Exception as exc:
                return {"query": query, "places": [], "error": str(exc)[:200]}

        try:
            groups = await asyncio.wait_for(
                asyncio.gather(*(search_one(query) for query in normalized)),
                timeout=map_search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"批量地点搜索超过 {round(map_search_timeout)} 秒；"
                "请减少地点数量或在设置中选择快速档"
            ) from exc
        for group in groups:
            places = group.get("places") or []
            for place in places:
                place_id = str(place["place_id"])
                if place_id not in seen_ids:
                    seen_ids.add(place_id)
                    all_places.append(place)

        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])
        await _save_state(state)
        return json.dumps(
            {
                "groups": groups,
                "places": all_places,
                "verified_query_count": sum(bool(group.get("places")) for group in groups),
            },
            ensure_ascii=False,
        )

    async def recommend_nearby_places_on_map(
        anchor_query: str,
        query: str,
        anchor_queries: list[str] | None = None,
        use_current_location_as_anchor: bool = False,
        city: str = "全国",
        radius_meters: int = 2_000,
        strict_radius: bool = False,
        limit: int = 5,
        title: str = "",
        action_text: str = "",
    ) -> str:
        """Find a category near one or more verified anchors and prepare a map Action.

        Put the first or only anchor in anchor_query. When the user names
        alternative anchors, also put every alternative in anchor_queries; the
        tool keeps successful groups even if another anchor returns no result.
        Anchors are resolved from the Makers user workspace first, including
        verified places attached to schedules. Only a missing anchor reaches
        the location provider. Each nearby lookup is one Tencent boundary query
        rather than a web search plus repeated relative-name lookups.
        """
        requested_anchor_queries = list(dict.fromkeys(
            str(value or "").strip()
            for value in [anchor_query, *(anchor_queries or [])]
            if str(value or "").strip()
        ))
        current_location_requested = bool(
            use_current_location_as_anchor
            or any(
                _is_browser_current_location_anchor(value)
                for value in requested_anchor_queries
            )
        )
        clean_anchor_queries = [
            value
            for value in requested_anchor_queries
            if not _is_browser_current_location_anchor(value)
        ]
        if current_location_requested:
            clean_anchor_queries.insert(0, "__browser_current_location__")
        clean_query = str(query or "").strip()
        if not clean_anchor_queries:
            raise ValueError("附近搜索缺少参照地点")
        if len(clean_anchor_queries) > 4:
            raise ValueError("一次附近搜索最多支持 4 个备选参照地点")
        if not clean_query:
            raise ValueError("附近搜索缺少要查找的地点类别")
        if current_location_requested and browser_current_location is None:
            if len(clean_anchor_queries) == 1:
                return _clarification_action(
                    conversation_id,
                    title="需要附近搜索的起点",
                    prompt=(
                        "浏览器没有提供当前位置。请填写你所在的区域或附近地标，"
                        "提交后我会自动继续查找，不需要重新描述需求。"
                    ),
                    fields=[{
                        "id": "nearby_anchor",
                        "label": "你现在在哪里？",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "placeholder": "例如：北京市海淀区中关村，或吉林大学前卫南区",
                    }],
                )
            # Keep explicit alternative anchors useful even when the browser
            # branch is unavailable. The response reports only anchors that
            # were actually resolved and never claims a current-position scan.
            clean_anchor_queries = [
                value
                for value in clean_anchor_queries
                if value != "__browser_current_location__"
            ]

        state = await _load_state()
        stored_places: list[dict[str, Any]] = []
        seen_stored_ids: set[str] = set()

        def remember_stored(place: Any) -> None:
            if not isinstance(place, dict):
                return
            place_id = str(place.get("place_id") or "").strip()
            if (
                not place_id
                or place_id in seen_stored_ids
                or not isinstance(place.get("latitude"), (int, float))
                or not isinstance(place.get("longitude"), (int, float))
            ):
                return
            seen_stored_ids.add(place_id)
            stored_places.append(place)

        # Schedules are intentional user state, so their verified place is a
        # stronger anchor than a stale search candidate from an older turn.
        for event in (state.get("schedules") or {}).values():
            if not isinstance(event, dict):
                continue
            extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
            remember_stored(extra.get("place"))
        for place in (state.get("place_candidates") or {}).values():
            remember_stored(place)

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

        async def resolve_anchor(clean_anchor_query: str) -> dict[str, Any] | None:
            if clean_anchor_query == "__browser_current_location__":
                return copy.deepcopy(browser_current_location)
            normalized_anchor = _normalized_place_name(clean_anchor_query)

            def anchor_score(place: dict[str, Any]) -> tuple[float, int]:
                normalized_name = _normalized_place_name(place.get("name"))
                if not normalized_anchor or not normalized_name:
                    return (0.0, 0)
                if normalized_name == normalized_anchor:
                    return (4.0, len(normalized_name))
                if normalized_anchor in normalized_name:
                    return (
                        3.0 + len(normalized_anchor) / max(1, len(normalized_name)),
                        len(normalized_name),
                    )
                if normalized_name in normalized_anchor:
                    return (
                        2.0 + len(normalized_name) / max(1, len(normalized_anchor)),
                        len(normalized_name),
                    )
                return (0.0, 0)

            ranked_stored = sorted(
                ((anchor_score(place), index, place) for index, place in enumerate(stored_places)),
                key=lambda item: (-item[0][0], item[1]),
            )
            stored_anchor = (
                ranked_stored[0][2]
                if ranked_stored and ranked_stored[0][0][0] > 0
                else None
            )
            if stored_anchor is not None:
                return stored_anchor
            anchors = await _search_place_candidates_metered(
                map_key,
                clean_anchor_query,
                city=city or "全国",
                limit=5,
            )
            exact = [
                place for place in anchors
                if _normalized_place_name(place.get("name")) == normalized_anchor
            ]
            return exact[0] if len(exact) == 1 else (anchors[0] if anchors else None)

        search_deadline = asyncio.get_running_loop().time() + map_search_timeout
        try:
            resolved_anchors = await asyncio.wait_for(
                asyncio.gather(*(
                    resolve_anchor(clean_anchor_query)
                    for clean_anchor_query in clean_anchor_queries
                )),
                timeout=map_search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"参照地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            ) from exc

        requested_radius = max(300, min(20_000, int(radius_meters or 2_000)))
        # A model sometimes invents an overly narrow radius even though the
        # user only said "nearby". Keep the product default stable unless the
        # model marks a distance explicitly stated by the user as strict.
        radius = requested_radius if strict_radius else max(2_000, requested_radius)
        bounded_limit = max(1, min(map_place_result_limit, int(limit or 5)))

        async def lookup_nearby(
            clean_anchor_query: str,
            anchor: dict[str, Any] | None,
        ) -> dict[str, Any]:
            display_anchor_query = (
                "当前位置"
                if clean_anchor_query == "__browser_current_location__"
                else clean_anchor_query
            )
            if anchor is None:
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": None,
                    "places": [],
                    "error": f"没有核实到参照地点“{display_anchor_query}”",
                }
            try:
                found = await _search_places_nearby_metered(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=bounded_limit,
                    accept_category_results=True,
                )
                places = [{
                    **place,
                    "nearby_anchor_query": display_anchor_query,
                    "nearby_anchor_name": str(anchor.get("name") or display_anchor_query),
                    "nearby_anchor_place_id": str(anchor.get("place_id") or ""),
                } for place in found]
                logging.info(
                    "nearby place lookup anchor=%s query=%s radius=%s strict=%s results=%s",
                    str(anchor.get("name") or display_anchor_query)[:120],
                    clean_query[:120],
                    radius,
                    bool(strict_radius),
                    len(places),
                )
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": anchor,
                    "places": places,
                    "error": "",
                }
            except Exception as exc:
                logging.warning(
                    "nearby place lookup failed anchor=%s query=%s error=%s",
                    display_anchor_query[:120],
                    clean_query[:120],
                    exc,
                )
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": anchor,
                    "places": [],
                    "error": str(exc)[:200],
                }

        remaining = search_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"附近地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            )
        try:
            groups = await asyncio.wait_for(
                asyncio.gather(*(
                    lookup_nearby(clean_anchor_query, anchor)
                    for clean_anchor_query, anchor in zip(clean_anchor_queries, resolved_anchors)
                )),
                timeout=remaining,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"附近地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            ) from exc
        places: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()
        max_group_size = max((len(group["places"]) for group in groups), default=0)
        # Interleave groups so every successful alternative remains represented
        # when the combined map reaches the user-selected result cap.
        for index in range(max_group_size):
            for group in groups:
                if index >= len(group["places"]):
                    continue
                place = group["places"][index]
                place_id = str(place.get("place_id") or "")
                if not place_id or place_id in seen_place_ids:
                    continue
                seen_place_ids.add(place_id)
                places.append(place)
                if len(places) >= map_place_result_limit:
                    break
            if len(places) >= map_place_result_limit:
                break
        if not places:
            anchors_text = "、".join(
                "“当前位置”" if value == "__browser_current_location__" else f"“{value}”"
                for value in clean_anchor_queries
            )
            raise ValueError(
                f"没有在{anchors_text}附近 {radius} 米内核实到“{clean_query}”"
            )

        candidates = state.setdefault("place_candidates", {})
        for anchor in resolved_anchors:
            if anchor is not None:
                candidates[str(anchor["place_id"])] = anchor
        for place in places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])

        anchor_names = [
            str(group["anchor"].get("name") or group["anchor_query"])
            for group in groups
            if group["anchor"] is not None
        ]
        natural_title = str(
            title or f"{'、'.join(anchor_names or clean_anchor_queries)}附近的{clean_query}"
        )[:120]
        action = new_action(
            "map_recommendation",
            {
                "title": natural_title,
                "action_text": str(action_text or "在地图中查看附近地点")[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "anchor": next((anchor for anchor in resolved_anchors if anchor is not None), None),
            "anchors": [anchor for anchor in resolved_anchors if anchor is not None],
            "groups": groups,
            "places": places,
            "verified_place_count": len(places),
            "radius_meters": radius,
            "response_constraint": (
                f"已基于 {len([anchor for anchor in resolved_anchors if anchor is not None])} 个"
                f"参照地点的核实坐标，在 {radius} 米范围内合并找到 {len(places)} 个真实地点。"
                "每个地点的 nearby_anchor_name 表示其对应参照点；正文只使用这些地点及其"
                " distance_to_anchor_meters，不要补写未核实地点、评分或营业时间。"
            ),
        }, ensure_ascii=False)

    async def plan_route_between_places(
        origin_query: str = "",
        destination_query: str = "",
        city: str = "全国",
        origin_near_query: str = "",
        destination_near_query: str = "",
        nearby_radius_meters: int = 5_000,
        route_mode: str = "default",
        route_strategy: str = "default",
        use_current_location_as_origin: bool = False,
        ordered_stops: list[dict[str, str]] | None = None,
    ) -> str:
        """Resolve an ordered itinerary and calculate one verified Tencent route.

        For a two-place request, pass origin_query and destination_query. For a
        multi-stop trip, pass ordered_stops in the user's exact order; every
        item contains query and may contain near_query. Never optimize or
        reorder user-provided stops. When a place is described relative to
        another place, keep them separate, for example
        {"query":"锦江之星","near_query":"北京301医院"}.
        """
        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        requested_route_mode = str(route_mode or "default").strip().lower()
        planner_route_mode = str(planned_route_mode or "default").strip().lower()
        if requested_route_mode not in {"default", "driving", "transit", "walking", "bicycling"}:
            requested_route_mode = "default"
        explicit_route_mode = (
            requested_route_mode
            if requested_route_mode != "default"
            else planner_route_mode
            if planner_route_mode in {"driving", "transit", "walking", "bicycling"}
            else ""
        )
        requested_route_strategy = str(route_strategy or "default").strip().lower()
        planner_route_strategy = str(planned_route_strategy or "default").strip().lower()
        if requested_route_strategy not in {
            "default", "time_then_cost", "least_time", "least_cost",
        }:
            requested_route_strategy = "default"
        explicit_route_strategy = (
            requested_route_strategy
            if requested_route_strategy != "default"
            else planner_route_strategy
            if planner_route_strategy in {"time_then_cost", "least_time", "least_cost"}
            else ""
        )
        should_use_current_location = bool(
            browser_current_location
            and (use_current_location_as_origin or planned_route_uses_current_location)
            and not str(origin_query or "").strip()
        )
        if (
            (use_current_location_as_origin or planned_route_uses_current_location)
            and not browser_current_location
            and not str(origin_query or "").strip()
        ):
            return _clarification_action(
                conversation_id,
                title="需要路线起点",
                prompt="浏览器当前位置未授权或已经过期。请先在地图卡片授权定位，或直接填写起点。",
                fields=[{
                    "id": "route_origin",
                    "label": "从哪里出发？",
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": "例如：吉林大学前卫南区",
                }],
            )
        route_operation_deadline = asyncio.get_running_loop().time() + 58.0
        radius = max(500, min(20_000, int(nearby_radius_meters or 5_000)))
        state = await _load_state()
        learning = state.setdefault("route_preference_learning", {
            "mode_counts": {},
            "strategy_counts": {},
        })
        learned_route_mode = (
            _learned_route_preference(
                learning,
                "mode_counts",
                {"driving", "transit", "walking", "bicycling"},
            )
            if map_learn_route_preferences
            else ""
        )
        learned_route_strategy = (
            _learned_route_preference(
                learning,
                "strategy_counts",
                {"time_then_cost", "least_time", "least_cost"},
            )
            if map_learn_route_preferences
            else ""
        )
        selected_route_mode = (
            explicit_route_mode or learned_route_mode or map_preferred_route_mode
        )
        selected_route_strategy = (
            explicit_route_strategy or learned_route_strategy or map_route_strategy
        )
        candidates = state.setdefault("place_candidates", {})
        for event in (state.get("schedules") or {}).values():
            extra = event.get("extra") if isinstance(event, dict) and isinstance(event.get("extra"), dict) else {}
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place

        async def resolve(
            endpoint: str,
            query: str,
            near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            clean_query = str(query or "").strip()
            clean_near = str(near_query or "").strip()
            if clean_query == "__browser_current_location__":
                return copy.deepcopy(browser_current_location), None
            if not clean_query:
                raise ValueError(f"{endpoint}地点不能为空")
            if clean_near:
                try:
                    anchors = await _search_place_candidates_metered(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                except Exception:
                    anchors = await _search_places_metered(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                if not anchors:
                    raise ValueError(f"没有核实到{endpoint}参照地点“{clean_near}”")
                anchor_exact = [
                    item for item in anchors
                    if _normalized_place_name(item.get("name")) == _normalized_place_name(clean_near)
                ]
                anchor = anchor_exact[0] if len(anchor_exact) == 1 else anchors[0]
                matches = await _search_places_nearby_metered(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=6,
                )
            else:
                matches = _rank_verified_workspace_matches(
                    clean_query,
                    candidates,
                    city or "全国",
                    limit=6,
                )
                if not matches:
                    matches = await _search_places_metered(
                        map_key, clean_query, city=city or "全国", limit=6,
                    )
            if not matches:
                qualifier = f"（{clean_near}附近 {radius} 米内）" if clean_near else ""
                return None, _clarification_action(
                    conversation_id,
                    title=f"请确认{endpoint}",
                    prompt=(
                        f"地点服务没有足够证据确认“{clean_query}”{qualifier}。"
                        "可能是错别字、同名地点或缺少城市，请补充更完整名称。"
                    ),
                    fields=[{
                        "id": f"route_{endpoint}_{hashlib.sha256(clean_query.encode()).hexdigest()[:6]}",
                        "label": f"{endpoint}的正确名称或城市是什么？",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "placeholder": f"例如：城市 + {clean_query}",
                    }],
                )
            for match in matches:
                place_id = str(match.get("place_id") or "").strip()
                if place_id:
                    candidates[place_id] = match
            if len(candidates) > 200:
                state["place_candidates"] = dict(list(candidates.items())[-200:])

            # A brand near an anchor commonly has several legitimate branches.
            # Even when one branch has the exact bare brand name, choosing it
            # silently would be arbitrary; let the user pick from real nearby
            # candidates instead.
            if clean_near and len(matches) > 1:
                field = _place_choice_field(
                    f"route_{'origin' if endpoint == '起点' else 'destination'}",
                    f"请选择具体{endpoint}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=f"查到多个位于“{clean_near}”附近的“{clean_query}”。为避免算错距离，请先选择具体{endpoint}。",
                    fields=[field],
                )
            exact = [
                item for item in matches
                if _normalized_place_name(item.get("name")) == _normalized_place_name(clean_query)
            ]
            if len(exact) == 1:
                return exact[0], None
            if len(matches) > 1:
                field = _place_choice_field(
                    f"route_{'origin' if endpoint == '起点' else 'destination'}",
                    f"请选择具体{endpoint}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=f"查到多个符合“{clean_query}”的地点。为避免算错距离，请先选择具体{endpoint}。",
                    fields=[field],
                )
            return matches[0], None

        requested_stops: list[tuple[str, str]] = []
        if ordered_stops:
            if not isinstance(ordered_stops, list) or not 2 <= len(ordered_stops) <= map_route_stop_limit:
                raise ValueError(
                    f"有序行程必须包含 2 到 {map_route_stop_limit} 个地点；"
                    "可在设置的“地图与路线”中调整上限"
                )
            for index, raw_stop in enumerate(ordered_stops, 1):
                if isinstance(raw_stop, BaseModel):
                    raw_stop = raw_stop.model_dump()
                if not isinstance(raw_stop, dict):
                    raise ValueError(f"第 {index} 个行程地点格式无效")
                query = str(raw_stop.get("query") or "").strip()
                near_query = str(raw_stop.get("near_query") or "").strip()
                if not query:
                    raise ValueError(f"第 {index} 个行程地点不能为空")
                requested_stops.append((query, near_query))
        else:
            requested_stops = [
                (str(origin_query or "").strip(), str(origin_near_query or "").strip()),
                (str(destination_query or "").strip(), str(destination_near_query or "").strip()),
            ]
        if should_use_current_location:
            requested_stops = [
                ("__browser_current_location__", ""),
                *[item for item in requested_stops if item[0]],
            ]
        model_stop_count = len(requested_stops)
        requested_stops = preserve_planned_route_stops(
            requested_stops,
            planned_route_stops,
            route_user_message,
        )
        if len(requested_stops) > map_route_stop_limit:
            raise ValueError(
                f"当前地图设置允许单条路线最多 {map_route_stop_limit} 个地点，"
                "请减少站点或在设置中提高上限"
            )
        logging.info(
            "route stop handoff planner=%s tool_model=%s selected=%s",
            len(planned_route_stops or []),
            model_stop_count,
            len(requested_stops),
        )
        if (not city or city == "全国") and str(planned_route_city or "").strip():
            city = str(planned_route_city).strip()[:80]

        route_search_semaphore = asyncio.Semaphore(map_parallelism)

        async def resolve_indexed(
            index: int, query: str, near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            endpoint = (
                "起点" if index == 1
                else "终点" if index == len(requested_stops)
                else f"第 {index} 站"
            )
            async with route_search_semaphore:
                return await resolve(endpoint, query, near_query)

        try:
            resolution_results = await asyncio.wait_for(
                asyncio.gather(*(
                    resolve_indexed(index, query, near_query)
                    for index, (query, near_query) in enumerate(requested_stops, 1)
                )),
                timeout=map_search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"路线地点搜索超过 {round(map_search_timeout)} 秒；"
                "请减少站点或在设置中选择快速档"
            ) from exc

        resolved_stops: list[dict[str, Any]] = []
        for index, (place, clarification) in enumerate(resolution_results, 1):
            if clarification:
                await _save_state(state)
                return clarification
            endpoint = (
                "起点" if index == 1
                else "终点" if index == len(requested_stops)
                else f"第 {index} 站"
            )
            if not place:
                raise ValueError(f"{endpoint}没有完成核实")
            if (
                resolved_stops
                and str(resolved_stops[-1].get("place_id") or "")
                == str(place.get("place_id") or "")
            ):
                raise ValueError(f"{endpoint}和上一站解析成了同一个地点，请选择不同地点")
            resolved_stops.append(place)

        remaining_route_time = route_operation_deadline - asyncio.get_running_loop().time()
        if remaining_route_time <= 1:
            raise TimeoutError(
                "路线规划总耗时已接近 60 秒上限，请减少站点或在设置中选择快速档"
            )
        route = await load_route_cache(
            store,
            user_id,
            resolved_stops,
            False,
            mode=selected_route_mode,
            strategy=selected_route_strategy,
            near_time_tolerance_minutes=map_near_time_tolerance,
        )
        if route is None:
            try:
                route = await asyncio.wait_for(
                    _plan_route_metered(
                        map_key,
                        resolved_stops,
                        optimize=False,
                        mode=selected_route_mode,
                        strategy=selected_route_strategy,
                        near_time_tolerance_minutes=map_near_time_tolerance,
                    ),
                    # The selected mode comes from the explicit request, semantic
                    # plan, or user setting—in that order.
                    timeout=remaining_route_time,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "路线规划超过 60 秒上限，请减少站点或在设置中选择快速档"
                ) from exc
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        provider_places = route.get("places")
        if isinstance(provider_places, list) and len(provider_places) == len(resolved_stops):
            current_resolution = list(resolved_stops)
            resolved_stops = [
                copy.deepcopy(item)
                for item in provider_places
                if isinstance(item, dict)
            ]
            # A cached road route is keyed by canonical provider place ids and
            # intentionally ignores how the user spelled a stop. Preserve the
            # current lookup's Tencent-backed correction evidence when cached
            # normalized places replace this turn's resolved candidates.
            if len(resolved_stops) == len(current_resolution):
                for resolved, current in zip(resolved_stops, current_resolution):
                    correction = current.get("query_correction")
                    if isinstance(correction, dict):
                        resolved["query_correction"] = copy.deepcopy(correction)
                    else:
                        resolved.pop("query_correction", None)
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        distance_meters = float(route.get("distance_meters") or 0)
        duration_seconds = float(route.get("duration_seconds") or 0)
        query_corrections = [
            copy.deepcopy(place.get("query_correction"))
            for place in resolved_stops
            if isinstance(place.get("query_correction"), dict)
        ]
        for place in resolved_stops:
            candidates[str(place["place_id"])] = place
        route_plan_id = "routeplan-" + hashlib.sha256(
            (
                "|".join(str(place.get("place_id") or "") for place in resolved_stops)
                + f":{time.time_ns()}"
            ).encode()
        ).hexdigest()[:16]
        state["latest_route_plan"] = {
            "id": route_plan_id,
            "created_at": int(time.time()),
            "ordered_stops": resolved_stops,
            "query_corrections": query_corrections,
            "distance_meters": round(distance_meters),
            "duration_seconds": round(duration_seconds),
            "mode": selected_route_mode,
            "strategy": selected_route_strategy,
            "selection": copy.deepcopy(route.get("selection") or {}),
        }
        map_action = new_action(
            "map_recommendation",
            {
                "title": f"{resolved_stops[0].get('name') or '起点'} → {resolved_stops[-1].get('name') or '终点'}",
                "action_text": "在地图中查看这条路线",
                "places": resolved_stops,
                "route_plan_id": route_plan_id,
                "route_mode": selected_route_mode,
                "route_strategy": selected_route_strategy,
                "preference_signal": (
                    {
                        **({"mode": explicit_route_mode} if explicit_route_mode else {}),
                        **(
                            {"strategy": explicit_route_strategy}
                            if explicit_route_strategy else {}
                        ),
                    }
                    if map_learn_route_preferences
                    and (explicit_route_mode or explicit_route_strategy)
                    else {}
                ),
                "show_route": True,
            },
            requires_confirmation=False,
        )
        put_action(state, map_action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": map_action,
            "route_plan_id": route_plan_id,
            "origin": resolved_stops[0],
            "destination": resolved_stops[-1],
            "ordered_stops": resolved_stops,
            "route": {
                "provider": route.get("provider"),
                "mode": route.get("mode") or "driving",
                "distance_meters": round(distance_meters),
                "distance_kilometers": round(distance_meters / 1000, 1),
                "duration_seconds": round(duration_seconds),
                "duration_minutes": max(1, round(duration_seconds / 60)),
                "fare": route.get("fare") or {},
                "transit": route.get("transit") or {},
                "selection": route.get("selection") or {},
            },
            "response_constraint": (
                f"距离和耗时来自按用户指定顺序核实的 {len(resolved_stops)} 个地点之间的真实道路路线；"
                f"交通方式为 {selected_route_mode}；"
                f"路线策略为 {selected_route_strategy}，由腾讯返回候选并按"
                f"{map_near_time_tolerance} 分钟的时间相近容差选择；"
                + (
                    "query_corrections 是腾讯地点候选提供的高置信度纠错证据，回答应简短说明按纠正名称规划；"
                    if query_corrections else ""
                )
                + "必须按 ordered_stops 原顺序描述各站，绝不能重新排序；"
                "回答必须使用这里的数值，不得改用网页估算、直线距离或模型猜测。"
            ),
        }, ensure_ascii=False)

    async def prepare_map_recommendation(
        title: str,
        place_ids: list[str],
        action_text: str,
        expected_place_count: int = 2,
    ) -> str:
        """Prepare a clickable map recommendation from verified place IDs.

        action_text is natural, contextual Chinese link copy generated for this answer.
        This tool does not change the user's map until the user clicks the action.
        """
        if not isinstance(place_ids, list) or not 1 <= len(place_ids) <= map_place_result_limit:
            raise ValueError(
                f"地图推荐必须包含 1 到 {map_place_result_limit} 个地点 ID；"
                "可在设置的“地图与路线”中调整候选数量"
            )
        state = await _load_state()
        candidates = dict(state.get("place_candidates", {}))
        for event in (state.get("schedules") or {}).values():
            extra = event.get("extra") if isinstance(event, dict) and isinstance(event.get("extra"), dict) else {}
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place
        places = []
        seen = set()
        for raw_id in place_ids:
            place_id = str(raw_id or "").strip()
            place = candidates.get(place_id)
            if place_id and place_id not in seen and isinstance(place, dict):
                seen.add(place_id)
                places.append(place)
        if not places:
            raise ValueError("推荐地点均未通过地点服务验证，不能显示到地图")
        expected = max(1, min(map_place_result_limit, int(expected_place_count or 2)))
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or "相关地点")[:120],
                "action_text": str(action_text or "在地图中看看这些地点")[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": len(places),
            "requested_place_count": expected,
            "partial": len(places) < expected,
        }, ensure_ascii=False)

    async def recommend_places_on_map(
        queries: list[str],
        city: str,
        title: str,
        action_text: str,
    ) -> str:
        """Verify model-selected destinations and prepare one terminal map Action."""
        normalized = list(dict.fromkeys(str(item or "").strip() for item in queries if str(item or "").strip()))
        if not 2 <= len(normalized) <= map_place_result_limit:
            raise ValueError(
                f"地图推荐需要模型提供 2 到 {map_place_result_limit} 个独立地点名称；"
                "可在设置的“地图与路线”中调整候选数量"
            )
        map_key = str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or "")
        selected, all_candidates, missing = await verify_place_queries_parallel(
            _search_places_metered,
            map_key,
            normalized,
            city=city or "全国",
            timeout_seconds=float(runtime_env.get("PLACE_LOOKUP_TIMEOUT_SECONDS") or 5),
        )
        if not selected:
            raise ValueError("所有候选地点都未通过真实地点服务核实，不能生成地图")
        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_candidates:
            candidates[str(place["place_id"])] = place
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or f"{city}推荐地点")[:120],
                "action_text": str(action_text or "在地图中查看这些地点")[:80],
                "places": selected,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        verified_count = len(selected)
        requested_count = len(normalized)
        response_constraint = (
            f"实际核实成功 {verified_count}/{requested_count} 个地点；正文只能声称地图显示了 {verified_count} 个。"
        )
        if missing:
            response_constraint += f" 未核实且不得放入地图：{'、'.join(missing)}。"
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": verified_count,
            "requested_place_count": requested_count,
            "partial": bool(missing),
            "unverified_queries": missing,
            "response_constraint": response_constraint,
        }, ensure_ascii=False)

    async def propose_calendar_changes(
        summary: str,
        changes: list[dict],
        source_route_plan_id: str = "",
    ) -> str:
        """Prepare create/update/delete changes; the calendar is mutated only after UI confirmation."""
        if not isinstance(changes, list) or not 1 <= len(changes) <= 24:
            raise ValueError("日程变更数量必须在 1 到 24 项之间")
        state = await _load_state()
        candidates = state.get("place_candidates", {})
        normalized = []
        for raw in changes:
            if not isinstance(raw, dict):
                raise ValueError("日程变更格式无效")
            operation = str(raw.get("operation") or "create")
            if operation not in {"create", "update", "delete"}:
                raise ValueError("日程操作只能是 create、update 或 delete")
            change: dict[str, Any] = {"operation": operation}
            previous_event: dict[str, Any] = {}
            if operation in {"update", "delete"}:
                schedule_id = str(raw.get("schedule_id") or "")
                if schedule_id not in state.get("schedules", {}):
                    raise ValueError("当前日程已变化，旧日程 ID 已失效；请根据本轮系统提供的当前日程标题和时间重新匹配后再提案")
                change["schedule_id"] = schedule_id
                previous_event = state.get("schedules", {}).get(schedule_id) or {}
            if operation != "delete":
                nested_event = raw.get("event")
                # Some tool-calling models flatten list-item fields. Accept
                # both wire shapes, then normalize into the canonical contract.
                event = nested_event if isinstance(nested_event, dict) else raw
                title = str(event.get("title") or event.get("name") or "").strip()[:120]
                start_value = str(event.get("start_time") or event.get("start") or "").strip()
                if operation == "create" and (not title or not start_value):
                    raise ValueError("新增日程必须包含标题和开始时间")
                normalized_event: dict[str, Any] = {}
                if title:
                    normalized_event["title"] = title
                end_value = str(event.get("end_time") or event.get("end") or "").strip()
                if start_value:
                    start = _parse_datetime(start_value)
                    normalized_event["start_time"] = int(start.timestamp())
                    if end_value:
                        end = _parse_datetime(end_value)
                    elif operation == "update":
                        end = start + timedelta(
                            minutes=max(1, int(previous_event.get("duration_minutes") or 60))
                        )
                    else:
                        end = start + timedelta(hours=1)
                    if end <= start:
                        raise ValueError(f"日程结束时间必须晚于开始时间：{title}")
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif end_value and operation == "update":
                    start = datetime.fromtimestamp(int(previous_event.get("start_time") or 0), timezone.utc)
                    end = _parse_datetime(end_value)
                    if end <= start:
                        raise ValueError(f"日程结束时间必须晚于开始时间：{title or previous_event.get('title') or '该日程'}")
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif "duration_minutes" in event:
                    normalized_event["duration_minutes"] = max(1, min(10_080, int(event.get("duration_minutes") or 60)))
                for key in ("category", "description", "done"):
                    if key in event:
                        normalized_event[key] = event[key]
                place_id = str(event.get("place_id") or event.get("location_place_id") or "").strip()
                location_text = str(event.get("location") or "").strip()
                clear_location = bool(event.get("clear_location", False))
                online_location = bool(
                    location_text
                    and re.search(
                        r"(?:zoom|腾讯会议|teams|google\s*meet|线上|在线|视频会议|电话会议)",
                        location_text,
                        re.I,
                    )
                )
                if clear_location:
                    place_id = ""
                    location_text = ""
                    normalized_event["place"] = None
                    normalized_event["location"] = ""
                elif online_location:
                    normalized_event["location"] = location_text
                if location_text and not place_id:
                    if online_location:
                        change["event"] = normalized_event
                        normalized.append(change)
                        continue
                    # A route or place tool in an earlier turn has already
                    # persisted verified candidates.  Reuse an unambiguous
                    # match instead of making the model transport a fragile
                    # provider id across turns.  This remains provider-backed:
                    # free-form locations that were never verified are refused.
                    normalized_location = _normalized_place_name(location_text)
                    matched = [
                        (candidate_id, candidate)
                        for candidate_id, candidate in candidates.items()
                        if isinstance(candidate, dict)
                        and normalized_location
                        and _normalized_place_name(candidate.get("name"))
                        and (
                            normalized_location == _normalized_place_name(candidate.get("name"))
                            or normalized_location == _normalized_place_name(candidate.get("address"))
                            or _normalized_place_name(candidate.get("name")) in normalized_location
                        )
                    ]
                    if len(matched) == 1:
                        place_id = str(matched[0][0])
                    elif len(matched) > 1:
                        raise ValueError(f"“{location_text}”对应多个已核实地点，请先选择具体地点")
                    else:
                        # A semantic planner normally schedules search_places
                        # before this tool. Keep the Action reliable when that
                        # optional hint omits needs_places: the calendar tool
                        # safely reuses the same Tencent/OSM adapter once,
                        # rather than failing and leaving a phantom card.
                        maps_enabled = enabled_skills is None or "maps" in enabled_skills
                        if not maps_enabled:
                            raise ValueError(
                                f"“{location_text}”需要地图 Skill 核实，请先到 Skills 广场开启地图"
                            )
                        verified = await _search_places_metered(
                            str(
                                runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                or runtime_env.get("TENCENT_MAP_KEY")
                                or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                or ""
                            ),
                            location_text,
                            city="全国",
                            limit=6,
                        )
                        if not verified:
                            raise ValueError(f"没有核实到地点“{location_text}”")
                        for candidate in verified:
                            candidate_id = str(candidate.get("place_id") or "").strip()
                            if candidate_id:
                                candidates[candidate_id] = candidate
                        place_id = str(verified[0].get("place_id") or "")
                if place_id:
                    place = candidates.get(place_id)
                    if not isinstance(place, dict) and location_text:
                        # Tool-calling models occasionally copy a display id
                        # incorrectly. Resolve the explicit user-visible
                        # location instead of accepting or persisting that id.
                        maps_enabled = enabled_skills is None or "maps" in enabled_skills
                        if maps_enabled:
                            verified = await _search_places_metered(
                                str(
                                    runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                    or runtime_env.get("TENCENT_MAP_KEY")
                                    or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                    or ""
                                ),
                                location_text,
                                city="全国",
                                limit=6,
                            )
                            for candidate in verified:
                                candidate_id = str(candidate.get("place_id") or "").strip()
                                if candidate_id:
                                    candidates[candidate_id] = candidate
                            if verified:
                                place_id = str(verified[0].get("place_id") or "")
                                place = candidates.get(place_id)
                    if not isinstance(place, dict):
                        raise ValueError(f"地点 ID 未通过本轮地点搜索验证：{place_id}")
                    normalized_event["place"] = place
                    normalized_event["location"] = place.get("address") or place.get("name")
                change["event"] = normalized_event
            normalized.append(change)
        latest_route = state.get("latest_route_plan")
        route_source_id = str(source_route_plan_id or "").strip()
        if not route_source_id and isinstance(latest_route, dict):
            # If a proposal contains at least two places from a very recent
            # verified route, it is semantically a route-derived calendar
            # proposal even when the model omitted the explicit source id.
            # Enforce completeness instead of silently accepting a compressed
            # two-event version of a four-stop itinerary.
            route_age = int(time.time()) - int(latest_route.get("created_at") or 0)
            route_place_ids = {
                str(item.get("place_id") or "")
                for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            }
            proposed_place_ids = {
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in normalized
                if change.get("operation") == "create"
            }
            if 0 <= route_age <= 10_800 and len(route_place_ids & proposed_place_ids) >= 2:
                route_source_id = str(latest_route.get("id") or "")

        if route_source_id:
            if (
                not isinstance(latest_route, dict)
                or route_source_id != str(latest_route.get("id") or "")
            ):
                raise ValueError("引用的路线规划已经变化，请根据最近一次已核实路线重新生成日程提案")
            required_stops = [
                item for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            ]
            required_ids = [str(item.get("place_id") or "") for item in required_stops]
            created = [
                change for change in normalized if change.get("operation") == "create"
            ]
            created.sort(key=lambda change: int(
                ((change.get("event") or {}).get("start_time") or 0)
            ))
            proposed_ids = [
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in created
            ]
            missing_names = [
                str(stop.get("name") or "未命名地点")
                for stop, place_id in zip(required_stops, required_ids)
                if place_id not in proposed_ids
            ]
            proposed_route_order = [
                place_id for place_id in proposed_ids if place_id in set(required_ids)
            ]
            if len(created) < len(required_ids) or missing_names:
                raise ValueError(
                    f"完整路线包含 {len(required_ids)} 个站点，日程提案必须至少创建 "
                    f"{len(required_ids)} 个按站点拆分的事件；尚未覆盖："
                    f"{'、'.join(missing_names) or '部分站点'}"
                )
            if proposed_route_order[:len(required_ids)] != required_ids:
                raise ValueError("日程事件顺序必须与已核实路线的站点顺序完全一致，不能合并或重排")

        validate_calendar_change_window(state, normalized)
        warnings = calendar_change_warnings(state, normalized)

        # Preview route feasibility before confirmation. The mutation remains
        # independent: route failure never writes or cancels the calendar
        # proposal, but users see whether travel time was verified.
        preview = copy.deepcopy(state)
        preview_changed = apply_calendar_changes(preview, normalized)
        changed_ids = {
            str(item.get("id") or "")
            for item in preview_changed
            if not item.get("deleted")
        }
        preview_schedules = sorted(
            (
                item for item in (preview.get("schedules") or {}).values()
                if (
                    isinstance(item, dict)
                    and not item.get("done")
                    and int(item.get("start_time") or 0) >= int(time.time()) - 24 * 60 * 60
                )
            ),
            key=lambda item: int(item.get("start_time") or 0),
        )[:provider_schedule_limit]
        route_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for previous, current in zip(preview_schedules, preview_schedules[1:]):
            if (
                str(previous.get("id") or "") not in changed_ids
                and str(current.get("id") or "") not in changed_ids
            ):
                continue
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            if not 0 < available <= route_gap_hours * 3600:
                continue
            previous_place = (
                (previous.get("extra") or {}).get("place")
                if isinstance(previous.get("extra"), dict) else None
            )
            current_place = (
                (current.get("extra") or {}).get("place")
                if isinstance(current.get("extra"), dict) else None
            )
            if isinstance(previous_place, dict) and isinstance(current_place, dict):
                route_pairs.append((previous, current))
            if len(route_pairs) >= 3:
                break

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

        async def preview_route_pair(
            previous: dict[str, Any], current: dict[str, Any],
        ) -> str:
            previous_place = (previous.get("extra") or {}).get("place")
            current_place = (current.get("extra") or {}).get("place")
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            try:
                route = await load_route_cache(
                    store, user_id, [previous_place, current_place], False,
                )
                if route is None:
                    route = await _plan_route_metered(
                        map_key, [previous_place, current_place], optimize=False,
                    )
                    await save_route_cache(
                        store, user_id, [previous_place, current_place], False, route,
                    )
                route_minutes = max(1, round(float(route.get("duration_seconds") or 0) / 60))
                required_minutes = route_minutes + travel_buffer_minutes
                available_minutes = max(0, available // 60)
                if required_minutes > available_minutes:
                    return (
                        f"“{previous.get('title') or '前一项日程'}”到"
                        f"“{current.get('title') or '后一项日程'}”道路路线约 {route_minutes} 分钟，"
                        f"加 {travel_buffer_minutes} 分钟缓冲共需 {required_minutes} 分钟，"
                        f"当前只有 {available_minutes} 分钟"
                    )
            except Exception:
                return (
                    f"暂未核验“{previous.get('title') or '前一项日程'}”到"
                    f"“{current.get('title') or '后一项日程'}”的道路通勤时间"
                )
            return ""

        if route_pairs:
            route_warning_results = await asyncio.gather(*(
                preview_route_pair(previous, current)
                for previous, current in route_pairs
            ))
            warnings.extend(value for value in route_warning_results if value)
            warnings = list(dict.fromkeys(warnings))[:8]
        action = new_action(
            "calendar_changes",
            {
                "summary": str(summary or "日程变更")[:300],
                "changes": normalized,
                "warnings": warnings,
                **({"source_route_plan_id": route_source_id} if route_source_id else {}),
            },
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "calendar_action", "action": action}, ensure_ascii=False)

    async def propose_meeting(subject: str = "", start_time: str = "", end_time: str = "") -> str:
        """Prepare an editable Tencent Meeting action, preserving missing user details."""
        state = await _load_state()
        action = new_action(
            "meeting_create",
            meeting_action_payload(state, subject, start_time, end_time),
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "side_effect_action", "action": action}, ensure_ascii=False)

    async def propose_image(
        prompt: str,
        parent_action_id: str = "",
        reference_image_urls: list[str] | None = None,
    ) -> str:
        """Generate an image immediately, optionally editing one prior generated version."""
        nonlocal turn_image_group_id
        clean_prompt = str(prompt or "").strip()[:2000]
        if not clean_prompt:
            raise ValueError("生图提示词不能为空")
        state = await _load_state()
        parent = state.get("actions", {}).get(str(parent_action_id or ""))
        references: list[str] = []
        group_id = ""
        if isinstance(parent, dict) and parent.get("kind") == "image_generate":
            parent_payload = parent.get("payload") or {}
            parent_result = parent.get("result") or {}
            reference_url = await resolve_image_reference(parent_result)
            if reference_url.startswith(("https://", "data:image/")):
                references.append(reference_url)
            group_id = str(parent_payload.get("group_id") or parent.get("id") or "")
        elif turn_image_group_id:
            group_id = turn_image_group_id
        for raw_url in reference_image_urls or []:
            url = str(raw_url or "").strip()
            if url.startswith(("https://", "data:image/")) and url not in references:
                references.append(url)
            if len(references) >= 3:
                break
        if not group_id and not references:
            references.extend(turn_visual_references[:3])
        action = new_action(
            "image_generate",
            {
                "prompt": clean_prompt,
                "parent_action_id": str(parent_action_id or ""),
                "group_id": group_id,
                "reference_image_urls": references,
            },
            requires_confirmation=False,
        )
        action["payload"]["group_id"] = group_id or action["id"]
        seal_action_snapshot(action)
        if not turn_image_group_id:
            turn_image_group_id = str(action["payload"]["group_id"])
        now = int(datetime.now().timestamp())
        begin_action_execution(action, owner=f"chat:{action['id']}", now=now)
        put_action(state, action)
        start_provider_call(state, action, now)
        state = await _save_state(state)
        result = await provider_generate_image(runtime_env, clean_prompt, references, user_id=user_id)
        if result.get("ok"):
            await record_provider_usage(
                store,
                user_id,
                str(result.get("provider") or "image_provider"),
                "images",
                1,
                model=str(result.get("model") or ""),
                source="chat_image",
            )
        state = await _load_state()
        current = get_action(state, action["id"])
        finish_provider_call(state, current, result, int(datetime.now().timestamp()))
        if result.get("ok"):
            current["result"]["versions"] = image_versions(state, str(current["payload"]["group_id"]))
        state = await _save_state(state)
        action = state["actions"][action["id"]]
        return json.dumps({"ui_action": "side_effect_action", "action": action}, ensure_ascii=False)

    async def collect_page_images(page_url: str, max_images: int = 30) -> str:
        """Collect up to 30 real image candidates from one public HTML page."""
        images = await provider_collect_page_images(page_url, max_images)
        return json.dumps({"page_url": page_url, "images": images, "count": len(images)}, ensure_ascii=False)

    async def rich_search(query: str, image_query: str = "", depth: str = "standard") -> str:
        """Run one planner-shaped rich search per turn, with a persistent result cache."""
        nonlocal rich_search_task, rich_search_invocations
        rich_search_invocations += 1
        if rich_search_task is None:
            clean_query = str(planned_search_query or query or "").strip()[:500]
            clean_image_query = str(planned_image_query or image_query or "").strip()[:500] if media_enabled else ""
            if not clean_query:
                raise ValueError("富搜索查询不能为空")
            clean_depth = depth if depth in {"basic", "standard", "deep"} else "standard"
            target_date = str(time_scope.get("target_date") or "")
            strict_date = bool(time_scope.get("strict_date"))
            cache_input = json.dumps(
                {
                    # Increment whenever cached search metadata semantics change
                    # so an older text-only entry cannot mask new rich media.
                    # Invalidate pre-vision-review entries that can only
                    # restore text/source metadata and therefore make a
                    # previously rich news answer appear permanently
                    # text-only after the media fallback change.
                    "pipeline_version": 5,
                    "identity": re.sub(r"\s+", " ", str(search_cache_identity or clean_query)).strip().casefold()[:4000],
                    "depth": clean_depth,
                    "target_date": target_date,
                    "strict_date": strict_date,
                    "media": media_enabled,
                    "result_limit": search_result_limit,
                    "image_limit": search_image_limit,
                    "parallel_image_search": parallel_image_search,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            cache_key = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
            cache_namespace = data_namespace("search_cache", str(user_id or "local-user"))

            async def run_once() -> str:
                nonlocal turn_visual_references, rich_search_provider_calls
                metadata = None
                stale_metadata = None
                stale_age = 0
                if store is not None:
                    try:
                        cached_item = await store.aget(cache_namespace, cache_key)
                        cached = cached_item.get("value") if isinstance(cached_item, dict) else getattr(cached_item, "value", None)
                        cached_at = int((cached or {}).get("cached_at") or 0) if isinstance(cached, dict) else 0
                        candidate = cached.get("metadata") if isinstance(cached, dict) else None
                        if cached_at and isinstance(candidate, dict):
                            stale_age = max(0, int(time.time()) - cached_at)
                            stale_metadata = candidate
                            if stale_age <= max(0, int(search_cache_ttl_seconds)):
                                metadata = candidate
                                metadata = {
                                    **metadata,
                                    "media_pending": False,
                                    "cache_hit": True,
                                    "cache_age_seconds": stale_age,
                                }
                                logging.info("rich_search cache_hit key=%s media=%s", cache_key[:12], media_enabled)
                    except Exception:
                        # Search must remain available when the optional cache is unavailable.
                        metadata = None
                if metadata is None:
                    logging.info("rich_search provider_call key=%s media=%s", cache_key[:12], media_enabled)
                    try:
                        async def publish_enriched_media(enriched: dict[str, Any]) -> None:
                            completed = {**enriched, "cache_hit": False, "media_pending": False}
                            await record_vision_diagnostics(
                                store,
                                user_id,
                                completed.get("vision_diagnostics"),
                                source="rich_search_media",
                            )
                            if store is not None:
                                try:
                                    await store.aput(cache_namespace, cache_key, {
                                        "cached_at": int(time.time()),
                                        "metadata": completed,
                                    })
                                except Exception:
                                    pass
                            if media_callback is not None:
                                await media_callback(completed)

                        rich_search_provider_calls += 1
                        try:
                            metadata = await provider_rich_search(
                                runtime_env,
                                clean_query,
                                image_query=clean_image_query,
                                depth=clean_depth,
                                target_date=target_date,
                                strict_date=strict_date,
                                media_callback=publish_enriched_media if progressive_media and media_enabled else None,
                                background_tasks=background_tasks if progressive_media and media_enabled else None,
                                include_media=media_enabled,
                                result_limit=search_result_limit,
                                image_limit=search_image_limit,
                                parallel_queries=parallel_image_search,
                            )
                        finally:
                            await record_provider_usage(
                                store, user_id, "wsa", "requests", 1, source="rich_search",
                            )
                        metadata = {**metadata, "cache_hit": False}
                        if not progressive_media:
                            await record_vision_diagnostics(
                                store,
                                user_id,
                                metadata.get("vision_diagnostics"),
                                source="rich_search_media",
                            )
                    except Exception:
                        stale_limit = max(3600, int(search_cache_ttl_seconds) * 4)
                        if isinstance(stale_metadata, dict) and stale_age <= stale_limit:
                            metadata = {
                                **stale_metadata,
                                "media_pending": False,
                                "cache_hit": True,
                                "stale_cache_hit": True,
                                "cache_age_seconds": stale_age,
                            }
                            logging.warning(
                                "rich_search stale_cache_hit key=%s age=%s",
                                cache_key[:12], stale_age,
                            )
                        else:
                            raise
                    if (
                        store is not None
                        and not metadata.get("media_pending")
                        and not metadata.get("stale_cache_hit")
                    ):
                        try:
                            await store.aput(cache_namespace, cache_key, {
                                "cached_at": int(time.time()),
                                "metadata": metadata,
                            })
                        except Exception:
                            pass
                reviewed_references = [
                    str(item.get("url") or "")
                    for item in metadata.get("media", [])
                    if str(item.get("url") or "").startswith("https://")
                ][:3]
                turn_visual_references = list(dict.fromkeys([*turn_visual_references, *reviewed_references]))[:3]
                return json.dumps({
                    "ui_action": "rich_search_results",
                    "search_results": metadata,
                    "papers": [],
                    "evidence": evidence_for_model(metadata),
                }, ensure_ascii=False)

            rich_search_task = asyncio.create_task(run_once())
        serialized = await rich_search_task
        result = json.loads(serialized)
        metadata = result.get("search_results") if isinstance(result, dict) else None
        if isinstance(metadata, dict):
            search_config = metadata.get("search_config")
            if not isinstance(search_config, dict):
                search_config = {}
            metadata["search_config"] = {
                **search_config,
                "turn_tool_invocations": rich_search_invocations,
                "turn_provider_calls": rich_search_provider_calls,
            }
            logging.info(
                "rich_search turn_audit conversation=%s invocations=%s provider_calls=%s cache_hit=%s",
                conversation_id,
                rich_search_invocations,
                rich_search_provider_calls,
                bool(metadata.get("cache_hit")),
            )
        return json.dumps(result, ensure_ascii=False)

    async def analyze_images_parallel(image_urls: list[str], goal: str) -> str:
        """Evaluate up to 30 images in small isolated concurrent batches."""
        image_urls = list(dict.fromkeys(str(url) for url in image_urls))[:30]
        if not image_urls:
            raise ValueError("至少需要一个图片 URL")
        for url in image_urls:
            if urlparse(url).scheme not in {"http", "https"}:
                raise ValueError("图片 URL 必须使用 http 或 https")
        semaphore = asyncio.Semaphore(4)

        async def inspect(index: int, image_url: str) -> dict:
            async with semaphore:
                try:
                    response = await asyncio.wait_for(
                        model.ainvoke([{"role": "user", "content": [
                            {"type": "text", "text": f"视觉评估目标：{goal}\n简洁返回画面内容、相关性和是否建议采用。"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ]}]),
                        timeout=45,
                    )
                    return {"index": index, "url": image_url, "analysis": _message_text(getattr(response, "content", ""))[:1200], "ok": True}
                except Exception as exc:
                    return {"index": index, "url": image_url, "analysis": "", "ok": False, "error": str(exc)[:200]}

        results = await asyncio.gather(*(inspect(index, url) for index, url in enumerate(image_urls)))
        return json.dumps({"ui_action": "image_analysis", "analyses": results}, ensure_ascii=False)

    async def search_arxiv(
        topic: str = "",
        limit: int = 5,
        titles: list[str] | None = None,
        author: str = "",
        year: int = 0,
    ) -> str:
        """Search structured academic papers from arXiv."""
        clean_topic = str(topic or "").strip()[:240]
        clean_titles = [str(title).strip()[:240] for title in (titles or []) if str(title).strip()][:8]
        clean_author = str(paper_scope.get("author") or author or "").strip()[:160]
        clean_year = int(paper_scope.get("year") or year or 0)
        requested_limit = int(paper_scope.get("limit") or 0)
        if requested_limit:
            limit = min(max(1, int(limit or requested_limit)), requested_limit)
        if not clean_topic and not clean_titles and not clean_author:
            raise ValueError("论文主题、准确标题或作者至少需要一项")
        papers = await provider_search_arxiv(clean_topic, limit, clean_titles, clean_author, clean_year)
        return json.dumps({"ui_action": "paper_results", "papers": papers, "topic": clean_topic}, ensure_ascii=False)

    async def propose_workflow(title: str, steps: list[dict[str, Any]], reason: str) -> str:
        """Create a user-confirmable persistent multi-step workflow."""
        state = await load_proactive_state(store, user_id)
        mode = str((state.get("preferences") or {}).get("autonomy_mode") or "propose")
        if mode not in {"propose", "low_risk_auto"}:
            raise ValueError("当前主动权限只允许观察或提醒；请先在主动提醒设置中允许提案")
        workflow = create_workflow_proposal(
            state, title=title, steps=steps, reason=reason, now=int(time.time()),
        )
        await save_proactive_state(store, state, user_id)
        return json.dumps({
            "workflow_proposal": workflow,
            "message": "工作流提案已加入主动提醒中心，只有用户确认后才会激活",
        }, ensure_ascii=False)

    async def ask_user_clarification(
        title: str,
        prompt: str,
        fields: list[ClarificationFieldInput],
    ) -> str:
        """Present one compact, structured clarification card instead of prose interrogation."""
        allowed = {"single", "multi", "boolean", "text", "date", "time", "datetime"}
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(fields or []):
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            if not isinstance(raw, dict):
                continue
            field_type = str(raw.get("type") or "text").strip().lower()
            options = list(dict.fromkeys(
                str(option).strip()[:120]
                for option in (raw.get("options") or [])
                if str(option).strip()
            ))[:8]
            # Enforce the product-wide interaction hierarchy even if a model
            # asks for a text box while already supplying finite choices.
            if len(options) >= 2 and field_type not in {"single", "multi"}:
                field_type = "single"
            if field_type not in allowed:
                field_type = "single" if len(options) >= 2 else "text"
            field_id = re.sub(r"[^a-zA-Z0-9_-]", "-", str(raw.get("id") or f"field-{index + 1}"))[:48] or f"field-{index + 1}"
            label = str(raw.get("label") or "请补充").strip()[:80]
            item: dict[str, Any] = {
                "id": field_id,
                "label": label,
                "type": field_type,
                "required": bool(raw.get("required", True)),
            }
            if field_type in {"single", "multi"}:
                if len(options) < 2:
                    continue
                item["options"] = options
            elif field_type == "text":
                item["placeholder"] = str(raw.get("placeholder") or "请填写").strip()[:120]
            normalized.append(item)
            if len(normalized) >= 8:
                break
        if not normalized:
            raise ValueError("至少需要一个有效的澄清字段")
        return _clarification_action(
            conversation_id,
            title=str(title or "请补充几个信息"),
            prompt=str(prompt or "为了更准确地帮你处理，请选择或补充以下信息。"),
            fields=normalized,
        )

    definitions = [
        (get_current_location, "get_current_location", "用户直接询问“我现在在哪、当前位置是什么、你能否读到我的位置”时使用。它只读取本轮浏览器真实上传的新鲜定位，并调用腾讯逆地址解析返回可读地址、行政区和附近地标；不得输出经纬度、不得使用 IP 猜测、不得保存位置。没有浏览器定位时会生成填写大致位置的结构化卡片，以便继续附近推荐或路线规划。"),
        (search_places, "search_places", "使用腾讯地点服务搜索真实地点。普通查看传 purpose=browse；新增或修改含现实地点的日程必须传 purpose=calendar，工具会强制执行三级决策：唯一高置信候选直接返回可用 place_id，多个真实候选生成单选卡，无候选生成文本填空卡。"),
        (search_places_batch, "search_places_batch", "多地点推荐必须使用：把每个地点作为独立 query 核实，并从每组选择一个最匹配的真实 place_id。"),
        (recommend_nearby_places_on_map, "recommend_nearby_places_on_map", "用户要找某个已知地点、当前位置或日程地点附近的餐馆、早餐店、酒店、商店、景点等真实地点时使用。用户说“我附近/当前位置附近”时必须设置 use_current_location_as_anchor=true；工具只会使用本轮浏览器实际上传的新鲜坐标，未收到坐标会明确失败，绝不能把“当前位置”当普通 POI 搜索或声称已经定位。其他情况传入完整明确的 anchor_query 与要找的类别 query；若用户给出多个备选参照地点，还必须把全部备选放入 anchor_queries，一次并行查询并保留各组成功结果，不能只选一个或拆成多次调用。工具优先复用 Makers 工作区和日程中已核实的参照地点坐标，再调用腾讯位置附近检索，并一次生成地图 Action。用户没有明确距离时不要自行缩小 radius_meters，保持默认 2000 米且 strict_radius=false；只有用户明确说“X 米内”时才传该距离并设 strict_radius=true。不要先用 rich_search 发现地点，也不要把“某地附近某类别”拼成普通 search_places 查询。"),
        (plan_route_between_places, "plan_route_between_places", "查询真实地点之间的道路距离、耗时或费用，或规划含多个停靠点的有序出行时必须使用。支持 route_mode=driving/transit/walking/bicycling 和 route_strategy=time_then_cost/least_time/least_cost，未指定均传 default。默认由腾讯多方案按省时优先、时间相近选省钱；用户明确选择会形成非敏感习惯计数，至少三次且占比达到 60% 后可影响后续默认。浏览器当前位置可用且用户未给起点时传 use_current_location_as_origin=true；不得把当前位置作为普通 POI 搜索。两点路线传 origin_query/destination_query；多段行程把全部文本地点按用户指定先后一次传入 ordered_stops，每项包含 query，可选 near_query，禁止拆成多次调用或自行重排。工具会核实全部地点并调用真实腾讯路线服务，禁止先用网页搜索估算距离。若地点形如“301医院附近的锦江之星”，把 query 传“锦江之星”、near_query 传“北京301医院”；唯一高置信错字可纠正，多个候选单选，无候选填空。"),
        (prepare_map_recommendation, "prepare_map_recommendation", "从已核实的真实 ID 生成可点击地图推荐；多地点推荐必须传 expected_place_count 和每组各一个 ID，数量不足时继续核实。只准备 Action，不直接更新地图。"),
        (recommend_places_on_map, "recommend_places_on_map", "模型驱动的非周边多地点推荐组合工具：根据用户目标自行给出 2-12 个具体地点名称、城市、自然地图标题和自然链接文案；工具逐个核实并准备最终地图 Action。用户指定数量时 queries 必须严格等于该数量。只要用户目标表达了相对某个或多个参照点“附近、周边、离它近”，不得使用本工具，也不得从模型知识猜餐厅名称；必须改用 recommend_nearby_places_on_map，把全部参照点放入 anchor_queries。"),
        (propose_calendar_changes, "propose_calendar_changes", "必须用此工具准备日程新增、更新或删除提案并生成确认卡；不要只在正文里口头询问。格式示例：changes=[{operation:'create',event:{title:'游览北海公园',start_time:'2026-07-16T09:00:00+08:00',end_time:'2026-07-16T10:00:00+08:00',place_id:'地点工具返回的ID'}}]。把刚规划的多站路线写入日程时，必须传路线工具返回的 source_route_plan_id，并为 ordered_stops 中每个地点分别创建至少一个事件，严格保持顺序，禁止把多个站点合并成一个事件。更新/删除还要传 schedule_id。用户点击确认前不会真正写入。"),
        (propose_meeting, "propose_meeting", "准备可编辑的腾讯会议确认卡；即使主题、开始时间或结束时间不完整也要调用本工具，把未知值留空，不要在正文中连续追问多个条件。确认卡会让用户逐项补齐、检查冲突并确认，之后才由后台通过腾讯会议官方 MCP Skill 执行。"),
        (propose_image, "propose_image", "直接调用混元生图并返回图片，不要询问确认。现实人物、地点或物体可先用 rich_search 获取经 HY-Vision 审核的图片 URL，再通过 reference_image_urls（最多 3 张）作为视觉参考；修改历史版本时传 parent_action_id。"),
        (collect_page_images, "collect_page_images", "从一个公开网页提取最多 30 张真实图片候选，网页图片不足时返回实际数量。"),
        (rich_search, "rich_search", "项目 v4.2 富搜索。搜索前的独立 LLM 规划器已经合并本轮事实查询，并判断图片是否有助于理解；同一轮无论怎样改写参数都只执行一次 Provider 搜索。"),
        (analyze_images_parallel, "analyze_images_parallel", "并行视觉评估最多 30 张图片；单张失败不影响其他图片。"),
        (search_arxiv, "search_arxiv", "补充获取 arXiv 可下载结果。富搜索已找到论文时，把准确标题列表一次性传给 titles；按作者和年份查找时分别传 author（英文署名）与 year，不要把作者年份混在宽泛 topic 中。工具会严格过滤作者/年份与标题，每轮最多调用一次。"),
        (propose_workflow, "propose_workflow", "用户明确要求建立跨时间、多步骤的持续提醒或计划时创建工作流提案。steps 每项包含 offset_minutes、title、body、action_prompt，可用 depends_on=['step_1'] 建立 DAG 依赖；失败时需要回退提示的步骤可增加 compensation={title,body,action_prompt}。默认按顺序依赖。必须由用户确认后才会激活，依赖步骤需用户标记完成后才推进。"),
        (ask_user_clarification, "ask_user_clarification", "所有问答场景统一的必要信息收集入口。只有缺少该字段会阻断所有安全有用的回答，或无法唯一确定真实副作用对象时才能调用；“知道后更好”、可选偏好和用户尚未决定都不得调用，应直接在正文给出 2–3 套带假设与取舍的方案。这条边界适用于所有主题，禁止套用固定画像问题。本轮最多调用一次并只收最少必要字段；能由当前上下文、已核实结果、其他字段或安全默认值推导出的字段不得再问。有限候选优先 single/multi，能用是/否表达就用 boolean，只缺日期用 date、日期已知只缺时刻用 time、两者都缺才用 datetime，仅答案无法枚举时用 text。卡片提交后由前端自动把答案作为对话补充信息继续推理，不要要求用户再次发送，也不要重复询问已提交字段。"),
    ]
    meeting_ready = bool(str(runtime_env.get("TENCENT_MEETING_TOKEN") or "").strip())
    if not meeting_ready:
        definitions = [definition for definition in definitions if definition[1] != "propose_meeting"]
    active = enabled_skills if enabled_skills is not None else {
        "web-search", "vision", "image-studio", "maps", "calendar",
        "proactive-agent", "paper-reading", "tencent-meeting",
    }
    active = set(active)
    if "calendar" not in active:
        active.discard("tencent-meeting")
    tool_skills = {
        "get_current_location": "maps",
        "search_places": "maps",
        "search_places_batch": "maps",
        "recommend_nearby_places_on_map": "maps",
        "plan_route_between_places": "maps",
        "prepare_map_recommendation": "maps",
        "recommend_places_on_map": "maps",
        "propose_calendar_changes": "calendar",
        "propose_meeting": "tencent-meeting",
        "propose_image": "image-studio",
        "collect_page_images": "web-search",
        "rich_search": "web-search",
        "analyze_images_parallel": "vision",
        "search_arxiv": "paper-reading",
        "propose_workflow": "proactive-agent",
        "ask_user_clarification": "core",
    }
    definitions = [definition for definition in definitions if tool_skills.get(definition[1]) == "core" or tool_skills.get(definition[1]) in active]
    return [
        StructuredTool.from_function(
            coroutine=fn,
            name=name,
            description=description,
            **({"args_schema": RoutePlanInput} if name == "plan_route_between_places" else {}),
        )
        for fn, name, description in definitions
    ]
