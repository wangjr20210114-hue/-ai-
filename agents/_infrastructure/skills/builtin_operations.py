"""Turn-local business operations supplied to trusted system Skill adapters."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from .calendar_operations import build_calendar_operation
from ..._application.skills.tool_contracts import ClarificationFieldInput
from ..._application.i18n import normalize_language, text

from ..._infrastructure.providers.tencent_location import (
    plan_verified_route as provider_plan_route,
    reverse_geocode as provider_reverse_geocode,
    search_verified_places_bounded as provider_search_places,
    search_verified_places_nearby as provider_search_places_nearby,
)
from ..._infrastructure.providers.web_media import collect_page_images as provider_collect_page_images
from ..._application.search.evidence_presenter import evidence_for_model
from ..._infrastructure.providers.rich_search import rich_search as provider_rich_search
from ..._infrastructure.providers.side_effects import generate_image as provider_generate_image, resolve_image_reference
from ..._infrastructure.providers.arxiv import search_arxiv as provider_search_arxiv
from ..._application.proactive.service import load_proactive_state, propose_workflow as create_workflow_proposal, save_proactive_state
from ..._infrastructure.makers.provider_usage_repository import record_provider_usage, record_vision_diagnostics
from ..._infrastructure.makers.identity import required_user_id
from ..._application.skills.registry import (
    capability_skill_map,
    default_skill_preferences,
    locked_skill_ids,
    resolve_enabled_skills,
    tool_skill_map,
)
from ..._application.skills.runtime import build_adapter_tools
from ..._application.skills.component_api import ComponentPublicationJournal
from ..._application.skills.runtime_ports import (
    SKILL_SERVICE_NAMES,
    ToolOperationService,
)
from ..._application.workspace.service import (
    load_user_workspace,
    meeting_action_payload,
    new_action,
    put_action,
    save_user_workspace,
)

from .route_resolution import _clarification_action
from .image_operations import build_image_operations
from .map_runtime import MapProviderRuntime
from .nearby_operations import build_nearby_operation
from .paper_operations import build_paper_search_operation
from .place_operations import PlaceOperations
from .route_operations import build_route_operation
from .search_operations import build_rich_search_operation
from .visual_context import TurnVisualContext

def build_system_skill_tools(
    model, *, store=None, conversation_id: str = "", env: dict | None = None,
    place_disambiguation_model=None,
    paper_discovery_model=None,
    paper_constraints: dict | None = None,
    temporal_context: dict[str, Any] | None = None,
    progressive_media: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    user_id: str = "",
    initial_visual_references: list[str] | None = None,
    media_enabled: bool = True,
    planned_media_preferred: bool = False,
    planned_search_query: str = "",
    planned_image_query: str = "",
    force_search_refresh: bool = False,
    rich_search_operation: Callable[[str, str, str], Awaitable[str]] | None = None,
    search_result_limit: int = 8,
    search_image_limit: int = 8,
    parallel_image_search: bool = True,
    enabled_skills: set[str] | None = None,
    identity: dict[str, Any] | None = None,
    planned_route_stops: list[dict[str, str]] | None = None,
    route_user_message: str = "",
    planned_route_city: str = "全国",
    planned_route_mode: str = "default",
    planned_route_strategy: str = "default",
    planned_route_uses_current_location: bool = False,
    planned_route_origin_is_departure: bool = False,
    planned_route_calendar_hint: str = "",
    planned_reuse_latest_route: bool = False,
    requested_route_plan_id: str = "",
    planned_calendar_place_resolution: bool = False,
    browser_current_location: dict[str, Any] | None = None,
    map_preferences: dict[str, Any] | None = None,
    proactive_preferences: dict[str, Any] | None = None,
    tracer: Any = None,
    makers_checkpointer: Any = None,
    request_id: str = "",
    component_journal: ComponentPublicationJournal | None = None,
    response_language: object = "zh-CN",
) -> list[StructuredTool]:
    user_id = required_user_id(user_id)
    response_language = normalize_language(response_language)
    runtime_env = env or {}
    place_skill_id = capability_skill_map().get("places", "")
    calendar_skill_id = capability_skill_map().get("calendar_action", "")
    paper_scope = paper_constraints or {}
    time_scope = temporal_context or {}
    map_scope = map_preferences or {}
    map_service_mode = str(map_scope.get("service_mode") or "balanced")
    map_place_result_limit = max(3, min(12, int(map_scope.get("place_result_limit") or 6)))
    map_route_stop_limit = max(2, min(12, int(map_scope.get("route_stop_limit") or 8)))
    map_search_timeout = max(10.0, min(55.0, float(map_scope.get("search_timeout_seconds") or 30)))
    provider_place_review_enabled = bool(
        place_disambiguation_model is not None
        and map_service_mode != "fast"
    )
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
    # Explicit turn-local handoff: reviewed search media can become image
    # references without asking the model to copy fragile URLs between tools.
    turn_visual_context = TurnVisualContext.from_initial(initial_visual_references)

    async def _load_state() -> dict[str, Any]:
        return await load_user_workspace(store, user_id=user_id)

    async def _save_state(state: dict[str, Any]) -> dict[str, Any]:
        return await save_user_workspace(store, state, user_id=user_id)

    map_runtime = MapProviderRuntime(
        store=store,
        user_id=user_id,
        service_mode=map_service_mode,
        search_timeout=map_search_timeout,
        place_result_limit=map_place_result_limit,
        tracer=tracer,
        # Resolve providers at operation time so the Adapter remains swappable
        # without capturing a stale provider during tool construction.
        search_places_provider=lambda: provider_search_places,
        search_nearby_provider=lambda: provider_search_places_nearby,
        reverse_geocode_provider=lambda: provider_reverse_geocode,
        plan_route_provider=lambda: provider_plan_route,
    )
    _search_places_metered = map_runtime.search_places
    _search_places_nearby_metered = map_runtime.search_nearby
    _plan_route_metered = map_runtime.plan_route

    place_operations = PlaceOperations(
        runtime_env=runtime_env,
        conversation_id=conversation_id,
        browser_current_location=browser_current_location,
        map_runtime=map_runtime,
        load_state=_load_state,
        save_state=_save_state,
        place_disambiguation_model=place_disambiguation_model,
        planned_calendar_place_resolution=planned_calendar_place_resolution,
        provider_place_review_enabled=provider_place_review_enabled,
        place_result_limit=map_place_result_limit,
        route_stop_limit=map_route_stop_limit,
        parallelism=map_parallelism,
        search_timeout=map_search_timeout,
        response_language=response_language,
    )
    get_current_location = place_operations.get_current_location
    search_places = place_operations.search_places
    search_places_batch = place_operations.search_places_batch

    recommend_nearby_places_on_map = build_nearby_operation(
        _load_state=_load_state,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        _search_places_nearby_metered=_search_places_nearby_metered,
        browser_current_location=browser_current_location,
        conversation_id=conversation_id,
        map_place_result_limit=map_place_result_limit,
        map_search_timeout=map_search_timeout,
        runtime_env=runtime_env,
        response_language=response_language,
    )

    plan_route_between_places = build_route_operation(
        _load_state=_load_state,
        _plan_route_metered=_plan_route_metered,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        _search_places_nearby_metered=_search_places_nearby_metered,
        browser_current_location=browser_current_location,
        calendar_skill_id=calendar_skill_id,
        conversation_id=conversation_id,
        enabled_skills=enabled_skills,
        map_learn_route_preferences=map_learn_route_preferences,
        map_near_time_tolerance=map_near_time_tolerance,
        map_parallelism=map_parallelism,
        map_preferred_route_mode=map_preferred_route_mode,
        map_route_stop_limit=map_route_stop_limit,
        map_route_strategy=map_route_strategy,
        map_search_timeout=map_search_timeout,
        place_disambiguation_model=place_disambiguation_model,
        planned_route_calendar_hint=planned_route_calendar_hint,
        planned_route_city=planned_route_city,
        planned_route_mode=planned_route_mode,
        planned_route_stops=planned_route_stops,
        planned_route_strategy=planned_route_strategy,
        planned_route_uses_current_location=planned_route_uses_current_location,
        planned_route_origin_is_departure=planned_route_origin_is_departure,
        provider_place_review_enabled=provider_place_review_enabled,
        route_user_message=route_user_message,
        runtime_env=runtime_env,
        store=store,
        user_id=user_id,
        response_language=response_language,
    )

    prepare_map_recommendation = (
        place_operations.prepare_map_recommendation
    )
    recommend_places_on_map = place_operations.recommend_places_on_map

    propose_calendar_changes = build_calendar_operation(
        _load_state=_load_state,
        _plan_route_metered=_plan_route_metered,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        browser_current_location=browser_current_location,
        conversation_id=conversation_id,
        enabled_skills=enabled_skills,
        map_search_timeout=map_search_timeout,
        place_disambiguation_model=place_disambiguation_model,
        place_skill_id=place_skill_id,
        planned_reuse_latest_route=planned_reuse_latest_route,
        provider_place_review_enabled=provider_place_review_enabled,
        provider_schedule_limit=provider_schedule_limit,
        requested_route_plan_id=requested_route_plan_id,
        route_gap_hours=route_gap_hours,
        runtime_env=runtime_env,
        store=store,
        travel_buffer_minutes=travel_buffer_minutes,
        user_id=user_id,
        response_language=response_language,
    )

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

    image_operations = build_image_operations(
        model=model,
        store=store,
        user_id=user_id,
        runtime_env=runtime_env,
        load_state=_load_state,
        save_state=_save_state,
        visual_context=turn_visual_context,
        generate_image_provider=lambda: provider_generate_image,
        resolve_image_reference_provider=lambda: resolve_image_reference,
        collect_page_images_provider=lambda: provider_collect_page_images,
        record_provider_usage_provider=lambda: record_provider_usage,
        response_language=response_language,
    )
    propose_image = image_operations["propose_image"]
    collect_page_images = image_operations["collect_page_images"]
    analyze_images_parallel = image_operations["analyze_images_parallel"]
    rich_search = build_rich_search_operation(
        store=store,
        user_id=user_id,
        conversation_id=conversation_id,
        runtime_env=runtime_env,
        time_scope=time_scope,
        visual_context=turn_visual_context,
        progressive_media=progressive_media,
        media_callback=media_callback,
        background_tasks=background_tasks,
        media_enabled=media_enabled,
        planned_media_preferred=planned_media_preferred,
        planned_search_query=planned_search_query,
        planned_image_query=planned_image_query,
        force_search_refresh=force_search_refresh,
        search_use_case_operation=rich_search_operation,
        search_result_limit=search_result_limit,
        search_image_limit=search_image_limit,
        parallel_image_search=parallel_image_search,
        provider_rich_search_provider=lambda: provider_rich_search,
        evidence_for_model_provider=lambda: evidence_for_model,
        record_provider_usage_provider=lambda: record_provider_usage,
        record_vision_diagnostics_provider=lambda: record_vision_diagnostics,
        response_language=response_language,
    )
    search_arxiv = build_paper_search_operation(
        store=store,
        user_id=user_id,
        runtime_env=runtime_env,
        paper_scope=paper_scope,
        paper_discovery_model=paper_discovery_model,
        provider_search_arxiv_provider=lambda: provider_search_arxiv,
        provider_rich_search_provider=lambda: provider_rich_search,
        record_provider_usage_provider=lambda: record_provider_usage,
        response_language=response_language,
    )
    async def propose_workflow(title: str, steps: list[dict[str, Any]], reason: str) -> str:
        """Create a user-confirmable persistent multi-step workflow."""
        state = await load_proactive_state(store, user_id)
        mode = str((state.get("preferences") or {}).get("autonomy_mode") or "propose")
        if mode not in {"propose", "low_risk_auto"}:
            raise ValueError(text(
                "skill.workflow.permission_denied", response_language,
            ))
        workflow = create_workflow_proposal(
            state, title=title, steps=steps, reason=reason, now=int(time.time()),
        )
        await save_proactive_state(store, state, user_id)
        return json.dumps({
            "workflow_proposal": workflow,
            "message": text("skill.workflow.proposed", response_language),
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
            label = str(
                raw.get("label")
                or text("chat.clarification.default_label", response_language)
            ).strip()[:80]
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
                item["placeholder"] = str(
                    raw.get("placeholder")
                    or text("skill.clarification.fill", response_language)
                ).strip()[:120]
            normalized.append(item)
            if len(normalized) >= 12:
                break
        if not normalized:
            raise ValueError(text(
                "skill.clarification.invalid_fields", response_language,
            ))
        return _clarification_action(
            conversation_id,
            title=str(title or text(
                "skill.clarification.default_title", response_language,
            )),
            prompt=str(prompt or text(
                "skill.clarification.default_prompt", response_language,
            )),
            fields=normalized,
        )

    definitions = [
        (get_current_location, "get_current_location", text("model.tool.get_current_location.description", response_language)),
        (search_places, "search_places", text("model.tool.search_places.description", response_language)),
        (search_places_batch, "search_places_batch", text("model.tool.search_places_batch.description", response_language)),
        (recommend_nearby_places_on_map, "recommend_nearby_places_on_map", text("model.tool.recommend_nearby_places_on_map.description", response_language)),
        (plan_route_between_places, "plan_route_between_places", text("model.tool.plan_route_between_places.description", response_language)),
        (prepare_map_recommendation, "prepare_map_recommendation", text("model.tool.prepare_map_recommendation.description", response_language)),
        (recommend_places_on_map, "recommend_places_on_map", text("model.tool.recommend_places_on_map.description", response_language)),
        (propose_calendar_changes, "propose_calendar_changes", text("model.tool.propose_calendar_changes.description", response_language)),
        (propose_meeting, "propose_meeting", text("model.tool.propose_meeting.description", response_language)),
        (propose_image, "propose_image", text("model.tool.propose_image.description", response_language)),
        (collect_page_images, "collect_page_images", text("model.tool.collect_page_images.description", response_language)),
        (rich_search, "rich_search", text("model.tool.rich_search.description", response_language)),
        (analyze_images_parallel, "analyze_images_parallel", text("model.tool.analyze_images_parallel.description", response_language)),
        (search_arxiv, "search_arxiv", text("model.tool.search_arxiv.description", response_language)),
        (propose_workflow, "propose_workflow", text("model.tool.propose_workflow.description", response_language)),
        (ask_user_clarification, "ask_user_clarification", text("model.tool.ask_user_clarification.description", response_language)),
    ]
    active = (
        enabled_skills
        if enabled_skills is not None
        else {
            skill_id
            for skill_id, enabled in default_skill_preferences().items()
            if enabled
        }
    )
    active = set(active)
    locked_skills = locked_skill_ids()
    active.update(locked_skills)
    active = set(resolve_enabled_skills(active))
    tool_owners = tool_skill_map()
    operations = {
        name: function
        for function, name, _description in definitions
    }
    if set(operations) != set(tool_owners):
        raise RuntimeError(
            "System Skill implementation/manifest mismatch: "
            f"missing={sorted(set(tool_owners) - set(operations))}, "
            f"undeclared={sorted(set(operations) - set(tool_owners))}"
        )
    services = {
        SKILL_SERVICE_NAMES[skill_id]: ToolOperationService({
            name: operations[name]
            for name, owner in tool_owners.items()
            if owner == skill_id
        })
        for skill_id in active
        if skill_id in SKILL_SERVICE_NAMES
    }
    journal = component_journal or ComponentPublicationJournal()
    adapter_tools = build_adapter_tools({
        "state_store": store,
        "checkpointer": makers_checkpointer,
        "model": model,
        "tracer": tracer,
        "conversation_id": conversation_id,
        "request_id": str(request_id or conversation_id),
        "user_id": user_id,
        "response_language": response_language,
        "identity": identity or {"user_id": user_id, "membership": "free"},
        "env": runtime_env,
        "browser_location": browser_current_location,
        "services": services,
        "components": journal.handlers(),
    }, active)
    adapter_names = [str(getattr(tool, "name", "") or "") for tool in adapter_tools]
    duplicate_adapter_names = {
        name for name in adapter_names if adapter_names.count(name) > 1
    }
    if len(adapter_names) != len(set(adapter_names)):
        raise ValueError(
            "Skill adapter tool names must be globally unique: "
            f"{sorted(duplicate_adapter_names)}"
        )
    return adapter_tools
