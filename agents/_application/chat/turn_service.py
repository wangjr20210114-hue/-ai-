"""LangGraph chat endpoint running on the EdgeOne Makers agent runtime."""

import asyncio
import copy
import contextlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from .turn_context import experience_hints_for_plan
from .turn_io import (
    _document_context,
    _recent_user_questions,
    _text_content,
    _ui_action,
    _usage_values,
    checkpoint_dialogue_context,
    checkpoint_final_answer,
    hydrate_durable_map_action,
)
from .turn_policy import (
    direct_paper_tool_arguments,
    dynamic_system_prompt,
    empty_generation_error,
    location_clarification_arguments,
    run_cancelled,
    runtime_datetime_context,
    should_buffer_public_answer,
    tools_for_capability_stage,
)
from .turn_protocol import (
    capability_planning_message,
    checkpoint_clarification_state,
    graph_user_message,
    resume_capability_protocol,
)
from .turn_search import PlannedSearchRunner
from .turn_admission import admit_turn
from .skill_policy import apply_runtime_skill_policy
from ..i18n import text
from ...chat._graph import build_graph, grounded_route_stream_answer
from ...chat._llm import get_model
from ..._infrastructure.skills import build_system_skill_tools
from ..._application.skills.access import resolve_skill_access
from ..._application.skills.component_api import (
    ComponentPublicationJournal,
    attach_component_publications,
)
from ...chat._capability_plan import (
    DEFAULT_PLAN,
    fallback_tools_for_prompt_topics,
    media_enabled_for_plan,
    plan_capabilities_bounded,
    progressive_media_for_plan,
    required_tools_for_plan,
)
from ...chat._followups import generate_followups, should_generate_followups
from ...chat._protocol import (
    MarkdownImageStreamFilter,
    PublicStreamFilter,
    StreamDeltaNormalizer,
    checkpoint_recovery_needed,
    public_error,
    safe_error_diagnostics,
)
from ...chat._calendar_context import calendar_context, latest_route_context
from ..._application.intelligence.service import (
    apply_automatic_memory_candidates,
    confirmed_memory_context,
    extract_automatic_memory_candidates,
    load_intelligence_state,
    record_usage,
    save_intelligence_state,
    usage_summary,
    skill_runtime_env,
    user_skill_prompt_context,
)
from ..._infrastructure.makers.data_version import namespace as data_namespace
from ..._infrastructure.makers.conversation_repository import (
    read_chat_run,
    write_chat_run,
)
from ..._infrastructure.http import error
from ..._application.workspace.service import load_user_workspace
from ..._infrastructure.providers.vision import describe_reference_images
from ..._infrastructure.makers.provider_usage_repository import (
    record_vision_diagnostics,
)
from ..._application.proactive.opportunities import detect_opportunity, opportunity_signal
from ..._application.proactive.service import (
    load_proactive_state,
    process_schedule_signals,
    public_proactive_state,
    save_proactive_state,
)
from ..._presenters.chat_stream import ChatStreamPresenter
HEARTBEAT_SECONDS = 5
MAX_GRAPH_RECURSION = 24

class ChatTurnService:
    """Execute one authenticated chat turn behind the thin controller."""

    def __init__(self, ctx) -> None:
        self._ctx = ctx

    async def handle(self):
        return await _handle(self._ctx)


async def _handle(ctx):
    handler_started_at = time.monotonic()
    stage_timings_ms: dict[str, int | bool] = {}
    admission, rejection = await admit_turn(ctx)
    if rejection is not None:
        return rejection
    assert admission is not None
    identity = admission.identity
    user_id = admission.user_id
    raw_conversation_id = admission.raw_conversation_id
    conversation_id = admission.conversation_id
    body = admission.body
    message = admission.message
    clarification_id = admission.clarification_id
    current_clarification_answers = admission.current_clarification_answers
    silent_clarification = admission.silent_clarification
    direct_public_answer = admission.direct_public_answer
    response_language = admission.response_language
    presenter = ChatStreamPresenter(response_language)
    response_language_instruction = admission.response_language_instruction
    browser_current_location = admission.browser_current_location
    browser_location_request = admission.browser_location_request
    current_location_context = admission.current_location_context
    run_id = admission.run_id

    async def fail_run(
        message_text: str, diagnostics: dict | None = None,
    ) -> None:
        await write_chat_run(
            ctx.store,
            conversation_id,
            run_id=run_id,
            status="failed",
            error=str(message_text or text("chat.request_failed", response_language)),
            diagnostics=diagnostics,
        )
    reference_images = admission.reference_images

    current_beijing = datetime.now(timezone(timedelta(hours=8)))
    current_date = current_beijing.date().isoformat()
    try:
        model = get_model(ctx.env)
        # Capability routing, fixed tool JSON, validated Action summaries and
        # optional post-turn judgments share a non-thinking Flash sibling.
        # The reasoning profile remains available only when the semantic plan
        # marks the user-visible answer as genuinely open-ended.
        fast_model = get_model(
            ctx.env,
            thinking_mode="disabled",
            fallback_profile="fast",
        )
    except Exception as exc:
        logging.exception("chat model configuration failed")
        message_text = public_error(exc, response_language)
        await fail_run(
            message_text,
            safe_error_diagnostics(exc, stage="model_configuration"),
        )
        return error(message_text, 503)
    intelligence_started_at = time.monotonic()
    stage_timings_ms["request_setup"] = round(
        (intelligence_started_at - handler_started_at) * 1000
    )
    # Intelligence contains Skill switches, budgets, search/map settings and
    # confirmed memory, so it is the only state every turn needs before routing.
    # Workspace and proactive state are loaded later only when the selected
    # chain can consume them.
    intelligence = await load_intelligence_state(
        ctx.store.langgraph_store, user_id,
    )
    runtime_env = skill_runtime_env(ctx.env, intelligence)
    stage_timings_ms["intelligence_load"] = round(
        (time.monotonic() - intelligence_started_at) * 1000
    )
    planning_context_started_at = time.monotonic()
    proactive_state: dict = {}
    workspace: dict = {}
    budget = usage_summary(intelligence)
    if (
        str((budget.get("preferences") or {}).get("enforcement") or "soft") == "hard"
        and ((budget.get("alerts") or {}).get("daily") or (budget.get("alerts") or {}).get("monthly"))
    ):
        message_text = text("chat.token_budget_reached", response_language)
        await fail_run(message_text)
        return error(message_text, 429)
    # The planner only needs a bounded recent slice to decide whether memory is
    # relevant. The answer prompt receives it only when use_memory_context=true.
    memory_context = confirmed_memory_context(intelligence, limit=8)
    search_preferences = intelligence.get("search_preferences") or {}
    search_result_limit = max(4, min(18, int(search_preferences.get("result_limit") or 8)))
    search_image_limit = max(0, min(8, int(
        search_preferences.get("image_limit") if search_preferences.get("image_limit") is not None else 8
    )))
    parallel_image_search = bool(search_preferences.get("parallel_image_search", True))
    map_preferences = intelligence.get("map_preferences") or {}
    skill_access = resolve_skill_access(
        identity,
        intelligence.get("skill_preferences"),
    )
    private_skill_context = user_skill_prompt_context(intelligence)
    enabled_skills = set(skill_access.enabled_skills)
    disabled_skills = sorted(skill_access.disabled_skills)
    disabled_skill_reasons = dict(skill_access.downgrade_reasons)
    enabled_capabilities = set(skill_access.enabled_capabilities)
    vision_enabled = "vision_analysis" in enabled_capabilities
    current_calendar_context = "[]"
    current_route_context = text("model.chat.none", response_language)
    reference_image_context = ""
    if reference_images and vision_enabled:
        reference_image_context, vision_diagnostics = await describe_reference_images(
            ctx.env,
            reference_images,
            message,
            timeout=float(ctx.env.get("REFERENCE_VISION_TIMEOUT_SECONDS") or 8),
            response_language=response_language,
        )
        logging.info(
            "reference image analysis provider=%s attempted=%s",
            vision_diagnostics.get("provider") or "none",
            vision_diagnostics.get("attempted") or 0,
        )
        await record_vision_diagnostics(
            ctx.store.langgraph_store,
            user_id,
            vision_diagnostics,
            source="chat_reference_images",
        )
        if not reference_image_context:
            reference_image_context = text(
                "model.chat.vision_unavailable", response_language,
            )
    document_context = _document_context(body)
    clarification_context: list[str] = []
    recent_dialogue: list[dict[str, str]] = []
    prior_clarification_answers: list[str] = []
    checkpoint_clarification = {
        "answer_texts": [],
        "answers": [],
        "resume": {},
    }
    recent_dialogue_task = checkpoint_dialogue_context(
        getattr(ctx.store, "langgraph_checkpointer", None),
        conversation_id,
        message,
    )
    if silent_clarification:
        clarification_context, checkpoint_clarification, recent_dialogue = await asyncio.gather(
            _recent_user_questions(ctx.store, conversation_id, message),
            checkpoint_clarification_state(
                getattr(ctx.store, "langgraph_checkpointer", None),
                conversation_id,
            ),
            recent_dialogue_task,
        )
        prior_clarification_answers = checkpoint_clarification["answer_texts"]
    else:
        recent_dialogue = await recent_dialogue_task
    planning_message = capability_planning_message(
        message,
        clarification_id,
        clarification_context,
        prior_clarification_answers,
        recent_dialogue,
        response_language=response_language,
    )
    if reference_images and not vision_enabled:
        reference_image_context = text(
            "model.chat.vision_disabled", response_language,
        )
    if reference_image_context:
        planning_message += (
            "\n\n"
            + text("model.chat.reference_facts_header", response_language)
            + f"\n{reference_image_context[:1600]}"
        )
    if document_context:
        planning_message += (
            "\n\n"
            + text("model.chat.document_context_header", response_language)
            + f"\n{document_context[:6000]}"
        )
    stage_timings_ms["planning_context"] = round(
        (time.monotonic() - planning_context_started_at) * 1000
    )
    planner_timeout = max(12.0, min(25.0, float(
        ctx.env.get("CAPABILITY_PLAN_TIMEOUT_SECONDS") or 18
    )))
    if direct_public_answer:
        capability_plan = dict(DEFAULT_PLAN)
        planner_timed_out = False
    else:
        capability_plan, planner_timed_out = await plan_capabilities_bounded(
            fast_model,
            planning_message,
            memory_context,
            location_context=current_location_context,
            has_reference_images=bool(reference_images),
            has_document_context=bool(document_context),
            timeout_seconds=planner_timeout,
            timings_ms=stage_timings_ms,
            response_language=response_language,
        )
    post_plan_started_at = time.monotonic()
    resumed_planned_arguments: dict = {}
    if silent_clarification:
        capability_plan, resumed_planned_arguments = resume_capability_protocol(
            capability_plan,
            checkpoint_clarification.get("resume"),
            [
                *(checkpoint_clarification.get("answers") or []),
                *current_clarification_answers,
            ],
        )
    capability_plan = apply_runtime_skill_policy(
        capability_plan,
        disabled_skills,
        disabled_skill_reasons,
    )
    model_only_fallback = bool(
        capability_plan.get("_runtime_model_only_fallback")
    )
    if model_only_fallback:
        resumed_planned_arguments = {}
    clarification_tool_arguments: dict = {}
    if (
        capability_plan.get("needs_clarification")
        and capability_plan.get("clarification_fields")
    ):
        clarification_tool_arguments = {
            "title": str(
                capability_plan.get("clarification_title")
                or text("chat.clarification.required_title", response_language)
            ),
            "prompt": str(
                capability_plan.get("clarification_prompt")
                or text("chat.clarification.required_prompt", response_language)
            ),
            "fields": capability_plan.get("clarification_fields") or [],
        }
    nearby_tool_arguments: dict = {}
    route_tool_arguments: dict = {}
    nearby_explicit_anchors = [
        str(value or "").strip()
        for value in [
            capability_plan.get("nearby_anchor_query"),
            *(capability_plan.get("nearby_anchor_queries") or []),
        ]
        if str(value or "").strip()
    ]
    nearby_needs_browser_location = bool(
        capability_plan.get("needs_nearby_places")
        and capability_plan.get("nearby_uses_current_location")
        and not nearby_explicit_anchors
    )
    route_needs_browser_location = bool(
        capability_plan.get("needs_route")
        and capability_plan.get("route_uses_current_location")
    )
    needs_browser_location = bool(
        capability_plan.get("needs_current_location")
        or nearby_needs_browser_location
        or route_needs_browser_location
    )
    if (
        needs_browser_location
        and not browser_current_location
        and not silent_clarification
        and browser_location_request in {"idle", "not_attempted"}
        and not bool(body.get("_location_retry"))
        and not str(capability_plan.get("blocked_skill") or "").strip()
    ):
        # This response ends the first transport so the browser can obtain a
        # fresh location and retry the same logical turn. Close the Maker run
        # before emitting the retry request; otherwise the signed retry sees a
        # stale "running" owner and is rejected with 409.
        await write_chat_run(
            ctx.store,
            conversation_id,
            run_id=run_id,
            status="completed",
        )

        async def request_browser_location():
            yield presenter.browser_location_request(
                "semantic_capability_plan",
            )
            yield presenter.transport_done()

        return ctx.utils.stream_sse(request_browser_location())
    if (
        not browser_current_location
        and not silent_clarification
        and needs_browser_location
        and not str(capability_plan.get("blocked_skill") or "").strip()
    ):
        for key in list(capability_plan):
            if key.startswith("needs_"):
                capability_plan[key] = False
        capability_plan["needs_clarification"] = True
        location_intent = (
            "nearby"
            if nearby_needs_browser_location
            else "route"
            if route_needs_browser_location
            else "current"
        )
        clarification_tool_arguments = location_clarification_arguments(
            location_intent,
            browser_location_request,
            response_language,
        )
    resumed_nearby_arguments = resumed_planned_arguments.get(
        "recommend_nearby_places_on_map"
    )
    if isinstance(resumed_nearby_arguments, dict):
        nearby_tool_arguments = copy.deepcopy(resumed_nearby_arguments)
    elif capability_plan.get("needs_nearby_places"):
        nearby_tool_arguments = {
            "anchor_query": str(
                capability_plan.get("nearby_anchor_query") or ""
            ),
            "anchor_queries": (
                capability_plan.get("nearby_anchor_queries") or []
            ),
            "query": str(capability_plan.get("nearby_query") or ""),
            "use_current_location_as_anchor": bool(
                capability_plan.get("nearby_uses_current_location")
            ),
        }
    resumed_route_arguments = resumed_planned_arguments.get(
        "plan_route_between_places"
    )
    if isinstance(resumed_route_arguments, dict):
        route_tool_arguments = copy.deepcopy(resumed_route_arguments)
    elif capability_plan.get("needs_route") and capability_plan.get("route_stops"):
        route_stops = capability_plan.get("route_stops") or []
        route_tool_arguments = {
            "city": str(capability_plan.get("route_city") or "全国"),
            "route_mode": str(capability_plan.get("route_mode") or "default"),
            "route_strategy": str(
                capability_plan.get("route_strategy") or "default"
            ),
            "use_current_location_as_origin": bool(
                capability_plan.get("route_uses_current_location")
            ),
        }
        if capability_plan.get("route_uses_current_location") and len(route_stops) == 1:
            route_tool_arguments.update({
                "destination_query": str(route_stops[0].get("query") or ""),
                "destination_near_query": str(
                    route_stops[0].get("near_query") or ""
                ),
            })
        else:
            route_tool_arguments["ordered_stops"] = route_stops
    timeout_fallback_names = (
        fallback_tools_for_prompt_topics(
            capability_plan.get("_prompt_topics") or [],
        )
        if planner_timed_out
        else ()
    )
    needs_workspace_state = bool(
        capability_plan.get("needs_calendar_context")
        or capability_plan.get("needs_calendar_action")
        or capability_plan.get("needs_route")
        or {
            "propose_calendar_changes",
            "plan_route_between_places",
        } & set(timeout_fallback_names)
    )
    needs_proactive_state = bool(
        capability_plan.get("needs_workflow_action")
        or capability_plan.get("needs_opportunity_review")
        or "propose_workflow" in timeout_fallback_names
    )
    state_jobs = []
    if needs_workspace_state:
        state_jobs.append(("workspace", asyncio.create_task(load_user_workspace(
            ctx.store.langgraph_store,
            user_id=user_id,
        ))))
    if needs_proactive_state:
        state_jobs.append(("proactive", asyncio.create_task(load_proactive_state(
            ctx.store.langgraph_store, user_id,
        ))))
    workspace_started_at = time.monotonic()
    stage_timings_ms["post_plan_prepare"] = round(
        (workspace_started_at - post_plan_started_at) * 1000
    )
    if state_jobs:
        state_values = await asyncio.gather(*(task for _, task in state_jobs))
        for (state_name, _), state_value in zip(state_jobs, state_values):
            if state_name == "workspace":
                workspace = state_value
            else:
                proactive_state = state_value
    stage_timings_ms["selected_state_load"] = round(
        (time.monotonic() - workspace_started_at) * 1000
    )
    current_calendar_context = calendar_context(workspace)
    current_route_context = latest_route_context(workspace)
    if planner_timed_out:
        logging.warning(
            "chat capability planning unavailable after %.1fs; continuing with a bounded zero-tool recovery surface",
            planner_timeout,
        )
    logging.info("capability plan enabled=%s", [key for key, value in capability_plan.items() if value])

    # Publication-date strictness is a semantic planner decision.  Keyword
    # matching incorrectly treated “截至今天的最新能力” as “published today”
    # and discarded the latest verifiable release from earlier dates.
    queue: asyncio.Queue = asyncio.Queue()
    component_journal = ComponentPublicationJournal()
    search_runner = PlannedSearchRunner(
        ctx=ctx,
        presenter=presenter,
        queue=queue,
        capability_plan=capability_plan,
        identity=identity,
        conversation_id=conversation_id,
        user_id=user_id,
        user_message=message,
        current_date=current_date,
        result_limit=search_result_limit,
        image_limit=search_image_limit,
        parallel_queries=parallel_image_search,
        progressive_media=progressive_media_for_plan(
            capability_plan,
            planner_timed_out=planner_timed_out,
        ),
        runtime_env=runtime_env,
        run_id=run_id,
        stage_timings_ms=stage_timings_ms,
        response_language=response_language,
    )

    def build_all_tools() -> list:
        return build_system_skill_tools(
            model,
            # Only multi-candidate Tencent suggestion sets need semantic review.
            # This fixed-schema pass uses the non-thinking Flash profile; unique
            # Provider results and ordinary turns pay no extra model round.
            place_disambiguation_model=fast_model,
            # The same non-thinking profile may recall exact arXiv identities.
            # It only proposes candidates while official metadata providers verify
            # them, and it runs concurrently with the DBLP identity lookup.
            paper_discovery_model=fast_model,
            store=ctx.store.langgraph_store,
            conversation_id=conversation_id,
            env=runtime_env,
            paper_constraints={
                "author": capability_plan.get("paper_author") or "",
                "institution": capability_plan.get("paper_institution") or "",
                "year": capability_plan.get("paper_year") or 0,
                "year_from": capability_plan.get("paper_year_from") or 0,
                "year_to": capability_plan.get("paper_year_to") or 0,
                "limit": capability_plan.get("paper_limit") or 0,
            },
            temporal_context=search_runner.temporal_context,
            # SearchUseCase owns delivery; keep the trusted Component adapter
            # on the same per-plan progressive-media policy.
            progressive_media=progressive_media_for_plan(
                capability_plan,
                planner_timed_out=planner_timed_out,
            ),
            media_callback=None,
            background_tasks=search_runner.background_tasks,
            user_id=user_id,
            initial_visual_references=reference_images,
            # A recovered semantic plan may still request media. A hard planner
            # failure exposes no search tool, so this flag cannot trigger provider
            # work by itself.
            media_enabled=(
                vision_enabled
                and media_enabled_for_plan(
                    capability_plan,
                    search_image_limit,
                    planner_timed_out=planner_timed_out,
                )
            ),
            planned_media_preferred=bool(capability_plan.get("needs_images")),
            planned_search_query=str(capability_plan.get("search_query") or ""),
            planned_image_query=str(capability_plan.get("image_query") or ""),
            force_search_refresh=True,
            rich_search_operation=search_runner.execute,
            search_result_limit=search_result_limit,
            search_image_limit=search_image_limit,
            parallel_image_search=parallel_image_search,
            enabled_skills=enabled_skills,
            identity=identity,
            planned_route_stops=capability_plan.get("route_stops") or [],
            route_user_message=planning_message,
            planned_route_city=str(capability_plan.get("route_city") or "全国"),
            planned_route_mode=str(capability_plan.get("route_mode") or "default"),
            planned_route_strategy=str(
                capability_plan.get("route_strategy") or "default"
            ),
            planned_route_uses_current_location=bool(capability_plan.get("route_uses_current_location")),
            planned_route_origin_is_departure=bool(capability_plan.get("route_origin_is_departure")),
            planned_route_calendar_hint=str(
                capability_plan.get("route_calendar_hint") or ""
            ),
            planned_reuse_latest_route=bool(
                capability_plan.get("reuse_latest_route")
                or body.get("activity") == "route_calendar_offer_accepted"
            ),
            requested_route_plan_id=str(body.get("route_plan_id") or "")[:80],
            planned_calendar_place_resolution=bool(
                capability_plan.get("needs_calendar_action")
                and capability_plan.get("needs_places")
            ),
            browser_current_location=browser_current_location,
            map_preferences=map_preferences,
            proactive_preferences=proactive_state.get("preferences") or {},
            tracer=getattr(ctx, "tracer", None),
            makers_checkpointer=ctx.store.langgraph_checkpointer,
            request_id=run_id,
            component_journal=component_journal,
            response_language=response_language,
        )
    blocked_skill = str(capability_plan.get("blocked_skill") or "").strip()
    required_tool_names = required_tools_for_plan(capability_plan)
    fallback_tool_names = (
        fallback_tools_for_prompt_topics(
            capability_plan.get("_prompt_topics") or [],
        )
        if planner_timed_out and not required_tool_names
        else ()
    )
    graph_tool_names = required_tool_names or fallback_tool_names
    if blocked_skill:
        logging.info(
            "runtime skill policy blocked turn before graph model skill=%s",
            blocked_skill,
        )
    # Rich search is the single search path. Exposing the platform's plain
    # web_search beside it made semantically identical turns randomly lose the
    # established page-media + vision-review pipeline.
    tool_setup_error = ""
    runtime_now = runtime_datetime_context(current_beijing)
    selected_tool_names = (
        set(graph_tool_names)
    )
    answer_capability_plan = dict(capability_plan)

    graph_model = (
        model
        if model_only_fallback or capability_plan.get("needs_deep_reasoning")
        else fast_model
    )
    def build_answer_graph():
        graph_setup_started_at = time.monotonic()
        tool_system_prompt = dynamic_system_prompt(
            selected_tools=selected_tool_names,
            now=runtime_now,
            response_language_instruction=response_language_instruction,
            capability_plan=answer_capability_plan,
            calendar_context=current_calendar_context,
            reference_image_context=reference_image_context or text("model.chat.none", response_language),
            document_context=document_context or text("model.chat.none", response_language),
            current_location_context=current_location_context,
            current_route_context=current_route_context,
            memory_context=memory_context,
            user_skill_context=private_skill_context,
            public_answer=model_only_fallback,
            full_prompt=False,
            response_language=response_language,
        )
        stage_system_prompts = {
            tool_name: dynamic_system_prompt(
                selected_tools={tool_name},
                now=runtime_now,
                response_language_instruction=response_language_instruction,
                capability_plan=answer_capability_plan,
                calendar_context=current_calendar_context,
                reference_image_context=reference_image_context or text("model.chat.none", response_language),
                document_context=document_context or text("model.chat.none", response_language),
                current_location_context=current_location_context,
                current_route_context=current_route_context,
                memory_context=memory_context,
                user_skill_context=private_skill_context,
                response_language=response_language,
            )
            for tool_name in required_tool_names
        }
        public_system_prompt = dynamic_system_prompt(
            selected_tools=selected_tool_names,
            now=runtime_now,
            response_language_instruction=response_language_instruction,
            capability_plan=answer_capability_plan,
            calendar_context=current_calendar_context,
            reference_image_context=reference_image_context or text("model.chat.none", response_language),
            document_context=document_context or text("model.chat.none", response_language),
            current_location_context=current_location_context,
            current_route_context=current_route_context,
            memory_context=memory_context,
            user_skill_context=private_skill_context,
            public_answer=True,
            response_language=response_language,
        )
        # A complete Skill downgrade is deliberately the raw model surface.
        # Do not construct trusted adapters that the entitlement contract or
        # persisted switches have already removed from this turn.
        all_tools = [] if model_only_fallback else build_all_tools()
        graph_tools = tools_for_capability_stage(
            all_tools,
            graph_tool_names,
            blocked_skill=blocked_skill,
            planner_timed_out=False,
        )
        graph = build_graph(
            graph_model,
            graph_tools,
            tool_system_prompt,
            checkpointer=ctx.store.langgraph_checkpointer,
            store=ctx.store.langgraph_store,
            # Routing remains semantic and model-planned rather than keyword based.
            # Each selected Makers-native capability is required at most once, so
            # the assistant cannot merely describe a map or confirmation action
            # without producing it.
            required_tools=required_tool_names,
            blocked_skill=blocked_skill,
            response_language=response_language,
            # Route facts are compact but safety-sensitive: the final prose must
            # distinguish aggregate Tencent values from per-leg evidence and must
            # not invent service hours or alternatives. Keep Flash for routing and
            # every fixed tool schema, but use the main reasoning profile only for
            # this user-visible synthesis.
            public_answer_model=(
                model
                if model_only_fallback or capability_plan.get("needs_route")
                else fast_model
            ),
            fast_tool_model=fast_model,
            # Tool arguments are an intermediate fixed schema, including calendar
            # proposals. Use Flash without thinking here; the calendar adapter
            # independently validates event completeness, order, time windows,
            # verified place ids, conflicts, and the final confirmation boundary.
            # Public wording and genuinely open-ended reasoning remain separate.
            reasoning_tools=set(),
            stage_system_prompts=stage_system_prompts,
            public_system_prompt=public_system_prompt,
            planned_tool_arguments={
                **resumed_planned_arguments,
                **(
                    {"get_current_location": {}}
                    if capability_plan.get("needs_current_location")
                    else {}
                ),
                **(
                    {"ask_user_clarification": clarification_tool_arguments}
                    if clarification_tool_arguments
                    else {}
                ),
                **(
                    {"recommend_nearby_places_on_map": nearby_tool_arguments}
                    if nearby_tool_arguments
                    else {}
                ),
                **(
                    {"plan_route_between_places": route_tool_arguments}
                    if route_tool_arguments
                    else {}
                ),
                **direct_paper_tool_arguments(capability_plan),
            },
            direct_answer=direct_public_answer,
        )
        return (
            graph,
            graph_tools,
            round((time.monotonic() - graph_setup_started_at) * 1000),
        )
    stage_timings_ms["pre_graph_total"] = round(
        (time.monotonic() - handler_started_at) * 1000
    )
    tracer_event = getattr(getattr(ctx, "tracer", None), "event", None)
    if callable(tracer_event):
        tracer_event("chat.pre_graph_timing", {
            f"chat.timing.{key}": value
            for key, value in stage_timings_ms.items()
        })

    async def gen():
        done = object()
        usage = [0, 0, 0]
        last_cancel_check = [0.0]

        async def cancellation_requested() -> bool:
            now_mono = time.monotonic()
            if now_mono - last_cancel_check[0] < 2:
                return False
            last_cancel_check[0] = now_mono
            latest = await read_chat_run(ctx.store, conversation_id)
            if (
                isinstance(latest, dict)
                and latest.get("run_id")
                and str(latest.get("run_id")) != run_id
            ):
                # A newer send owns this conversation. The detached producer
                # for the old run must stop without touching its state.
                return True
            return run_cancelled(latest)

        async def produce():
            nonlocal answer_capability_plan
            pending_actions: list[dict] = []
            pending_search_results: dict | None = None
            pending_papers: dict | None = None
            pending_ai_content: list[str] = []
            final_answer_parts: list[str] = []
            public_stream = PublicStreamFilter()
            markdown_image_stream = MarkdownImageStreamFilter()
            stream_delta = StreamDeltaNormalizer()
            buffer_public_answer = should_buffer_public_answer(capability_plan)
            run_error = ""
            run_diagnostics: dict = {}
            cancelled = False
            clarification_emitted = False
            synthesis_started = False
            await queue.put(presenter.progress(
                "planning",
                "completed",
            ))
            await queue.put(presenter.progress(
                "retrieval"
                if search_runner.planned_request is not None or graph_tool_names
                else "synthesis",
                "active",
                activity=(
                    "web_search"
                    if search_runner.planned_request is not None
                    else "component_action"
                    if graph_tool_names
                    else "general"
                ),
            ))
            if bool(body.get("_diagnostics")):
                await queue.put(presenter.stage_timing(stage_timings_ms))
            # Optional post-turn jobs are themselves dynamically planned. They
            # use non-thinking Flash and are never started for every message by
            # default. Result turns can suggest useful adjacent questions;
            # clarification and blocked turns must not compete with their card.
            follow_up_task = (
                asyncio.create_task(generate_followups(
                    fast_model,
                    message,
                    plan_context=json.dumps(capability_plan, ensure_ascii=False),
                    response_language=response_language,
                ))
                if should_generate_followups(
                    capability_plan,
                    blocked_skill=blocked_skill,
                )
                else None
            )
            memory_enabled = bool(
                (intelligence.get("memory_preferences") or {}).get("enabled", True)
            )
            memory_task = (
                asyncio.create_task(
                    extract_automatic_memory_candidates(
                        fast_model, message, response_language=response_language,
                    )
                )
                if memory_enabled
                and capability_plan.get("needs_memory_extraction")
                else None
            )
            opportunity_enabled = bool(
                "workflow_action" in enabled_capabilities
                and capability_plan.get("needs_opportunity_review")
            )
            recent_questions_task = (
                asyncio.create_task(
                    _recent_user_questions(ctx.store, conversation_id, message)
                )
                if opportunity_enabled
                else None
            )

            async def reset_public_stream() -> None:
                pending_ai_content.clear()
                final_answer_parts.clear()
                stream_delta.reset()
                markdown_image_stream.reset()
                if public_stream.reset():
                    await queue.put(presenter.reset())

            async def emit_public(content: str) -> None:
                if not content:
                    return
                final_answer_parts.append(content)
                if buffer_public_answer:
                    pending_ai_content.append(content)
                else:
                    await queue.put(presenter.token(content))

            async def persist_answer_extras(follow_ups: list[str] | None = None) -> None:
                """Persist media independently from optional post-answer jobs.

                Follow-up, memory, or opportunity generation may time out after
                the answer and reviewed images are already complete. Media must
                still survive a conversation switch or page reload in that case.
                """
                if (
                    not final_answer
                    or ctx.store.langgraph_store is None
                    or not (
                        follow_ups
                        or search_runner.latest_enriched_media
                        or experience_hints_for_plan(
                            answer_capability_plan,
                            auth_type=str(identity.get("auth_type") or "guest"),
                        )
                    )
                ):
                    return
                await ctx.store.langgraph_store.aput(
                    data_namespace("message_meta", conversation_id),
                    "latest_extras",
                    {
                        "original_content": final_answer,
                        "content": final_answer,
                        "follow_ups": follow_ups or [],
                        "experience_hints": experience_hints_for_plan(
                            answer_capability_plan,
                            auth_type=str(identity.get("auth_type") or "guest"),
                        ),
                        **(
                            {"search_results": search_runner.latest_enriched_media}
                            if search_runner.latest_enriched_media
                            else {}
                        ),
                    },
                )
            if tool_setup_error:
                await queue.put(
                    presenter.error("tool_setup_error", tool_setup_error)
                )
            try:
                graph, graph_tools, graph_setup_ms = build_answer_graph()
                stage_timings_ms["tool_graph_setup"] = graph_setup_ms
                if (
                    not blocked_skill
                    and "propose_image" in required_tool_names
                    and any(
                        getattr(tool, "name", "") == "propose_image"
                        for tool in graph_tools
                    )
                ):
                    await queue.put(
                        presenter.tool_call("image_generation_planning"),
                    )
                config = {
                    "configurable": {"thread_id": conversation_id},
                    "recursion_limit": MAX_GRAPH_RECURSION,
                }
                # Retry the marker after LangGraph has had a chance to create
                # the native conversation; the frontend appends the user row
                # concurrently and may have raced the first metadata update.
                latest_before_graph = await read_chat_run(ctx.store, conversation_id)
                if (
                    isinstance(latest_before_graph, dict)
                    and latest_before_graph.get("run_id")
                    and str(latest_before_graph.get("run_id")) != run_id
                ):
                    cancelled = True
                else:
                    await write_chat_run(
                        ctx.store,
                        conversation_id,
                        run_id=run_id,
                        status="running",
                    )
                if not cancelled:
                    current_user_message = graph_user_message(
                        message,
                        clarification_id,
                        current_clarification_answers,
                    )
                    async for event in graph.astream(
                        {"messages": [current_user_message]},
                        config=config,
                        stream_mode="messages",
                    ):
                        if await cancellation_requested():
                            cancelled = True
                            break

                        streamed_message, _metadata = event
                        stream_tags = {
                            str(tag)
                            for tag in (
                                _metadata.get("tags", [])
                                if isinstance(_metadata, dict) else []
                            )
                        }
                        suppress_decision_prose = "floris:tool-decision" in stream_tags
                        input_tokens, output_tokens, total_tokens = _usage_values(streamed_message)
                        usage[0] = max(usage[0], input_tokens)
                        usage[1] = max(usage[1], output_tokens)
                        usage[2] = max(usage[2], total_tokens)

                        if getattr(streamed_message, "type", "") == "tool":
                            await reset_public_stream()
                            tool_name = getattr(streamed_message, "name", "")
                            tool_content = _text_content(
                                getattr(streamed_message, "content", "")
                            )
                            try:
                                tool_payload = json.loads(tool_content)
                            except (TypeError, json.JSONDecodeError):
                                tool_payload = None
                            tool_error = (
                                tool_payload.get("tool_error")
                                if isinstance(tool_payload, dict)
                                and isinstance(tool_payload.get("tool_error"), dict)
                                else None
                            )
                            if (
                                tool_name == "rich_search"
                                and isinstance(tool_error, dict)
                                and tool_error.get("kind") == "runtime"
                            ):
                                fallback_skills = list(dict.fromkeys([
                                    *(answer_capability_plan.get(
                                        "_runtime_model_fallback_skills",
                                    ) or []),
                                    "web-search",
                                ]))
                                answer_capability_plan[
                                    "_runtime_model_fallback_skills"
                                ] = fallback_skills
                            action = _ui_action(tool_content)
                            action = await hydrate_durable_map_action(
                                ctx.store.langgraph_store, user_id, action,
                            )
                            component_publications = component_journal.drain_public(
                                str(tool_name or ""),
                            )
                            if action and component_publications:
                                action = attach_component_publications(
                                    action,
                                    component_publications,
                                )
                            if action and action.get("ui_action") == "rich_search_results":
                                metadata = action.get("search_results")
                                if isinstance(metadata, dict):
                                    if action.get("component_api"):
                                        metadata = {
                                            **metadata,
                                            "component_api": action["component_api"],
                                        }
                                    if (
                                        isinstance(
                                            search_runner.latest_enriched_media,
                                            dict,
                                        )
                                        and search_runner.latest_enriched_media.get(
                                            "media"
                                        )
                                    ):
                                        metadata = {
                                            **metadata,
                                            **search_runner.latest_enriched_media,
                                        }
                                    search_runner.latest_enriched_media = metadata
                                    pending_search_results = metadata
                                    await queue.put(presenter.sources(metadata))
                                    await queue.put(presenter.progress(
                                        "retrieval",
                                        "completed",
                                        activity="web_search",
                                    ))
                                    if metadata.get("media_pending"):
                                        await queue.put(presenter.progress(
                                            "verification",
                                            "active",
                                            activity="image_review",
                                        ))
                                    pending_search_results = None
                                papers = action.get("papers")
                                if (
                                    "paper_assistant" in enabled_capabilities
                                    and isinstance(papers, list)
                                    and papers
                                ):
                                    pending_papers = {"papers": papers, "topic": metadata.get("query", "") if isinstance(metadata, dict) else ""}
                                    await queue.put(
                                        presenter.papers(pending_papers),
                                    )
                                    pending_papers = None
                                await queue.put(
                                    presenter.tool_result(
                                        getattr(streamed_message, "name", ""),
                                        text("chat.progress.search_ready", response_language),
                                    )
                                )
                                continue
                            if action and action.get("ui_action") == "paper_results":
                                if "paper_assistant" in enabled_capabilities:
                                    pending_papers = action
                                    await queue.put(
                                        presenter.papers(pending_papers),
                                    )
                                    pending_papers = None
                                await queue.put(
                                    presenter.tool_result(
                                        "search_arxiv",
                                        text("chat.progress.papers_ready", response_language),
                                    ),
                                )
                                await queue.put(presenter.tool_progress(
                                    "search_arxiv",
                                    "completed",
                                ))
                                continue
                            if action and action.get("ui_action") == "clarification_action":
                                clarification_emitted = True
                                await queue.put(
                                    presenter.clarification(action),
                                )
                                continue
                            if action and action["ui_action"] in {
                                "map_action", "calendar_action", "side_effect_action",
                            }:
                                pending_actions.append(action)
                                # Actions are already durable in Makers Store. Emit them
                                # immediately so a slow final prose pass cannot hide a
                                # verified map or a safe confirmation card at the
                                # platform's request deadline.
                                await queue.put(presenter.action(action))
                                continue
                            await queue.put(
                                presenter.tool_result(
                                    getattr(streamed_message, "name", ""),
                                    tool_content[:500],
                                )
                            )
                            await queue.put(presenter.tool_progress(
                                getattr(streamed_message, "name", ""),
                                "completed",
                            ))
                            continue

                        tool_calls = getattr(streamed_message, "tool_calls", None) or []
                        if tool_calls:
                            await reset_public_stream()
                            for tool_call in tool_calls:
                                name = (
                                    tool_call.get("name", "")
                                    if isinstance(tool_call, dict)
                                    else ""
                                )
                                await queue.put(presenter.tool_call(name))
                                if name:
                                    await queue.put(
                                        presenter.tool_progress(name, "active"),
                                    )
                            continue

                        content = _text_content(getattr(streamed_message, "content", ""))
                        if content and not suppress_decision_prose:
                            if not synthesis_started:
                                synthesis_started = True
                                await queue.put(presenter.progress(
                                    "synthesis",
                                    "active",
                                ))
                            normalized_content = stream_delta.push(content)
                            if capability_plan.get("needs_image_generation"):
                                normalized_content = markdown_image_stream.push(
                                    normalized_content
                                )
                            delta, reset_required = public_stream.push(normalized_content)
                            if reset_required:
                                pending_ai_content.clear()
                                final_answer_parts.clear()
                                await queue.put(presenter.reset())
                            await emit_public(delta)
                image_tail = (
                    markdown_image_stream.finish()
                    if capability_plan.get("needs_image_generation")
                    else ""
                )
                if image_tail:
                    delta, reset_required = public_stream.push(image_tail)
                    if reset_required:
                        pending_ai_content.clear()
                        final_answer_parts.clear()
                        await queue.put(presenter.reset())
                    await emit_public(delta)
                tail, reset_required = public_stream.finish()
                if reset_required:
                    pending_ai_content.clear()
                    final_answer_parts.clear()
                    await queue.put(presenter.reset())
                await emit_public(tail)
                # Manual AIMessage fallbacks are durable in the Makers
                # checkpoint but are not emitted as LLM token events. Flush
                # the public filter first: short valid answers may still be in
                # its quarantine buffer, while pre-tool prose may already have
                # been retracted. Only the actually emitted result determines
                # whether checkpoint recovery is needed.
                if (
                    not cancelled
                    and checkpoint_recovery_needed(
                        final_answer_parts,
                        stream_finished=True,
                    )
                ):
                    try:
                        final_snapshot = await graph.aget_state(config)
                        recovered_answer = checkpoint_final_answer(final_snapshot)
                        if recovered_answer:
                            await emit_public(recovered_answer)
                    except Exception as exc:
                        logging.warning("final checkpoint answer recovery failed: %s", exc)
                if buffer_public_answer:
                    grounded_route_answer = grounded_route_stream_answer(
                        pending_actions,
                        calendar_required=bool(
                            capability_plan.get("needs_calendar_action")
                        ),
                        clarification_emitted=clarification_emitted,
                        run_error=run_error,
                        response_language=response_language,
                    )
                    if grounded_route_answer:
                        pending_ai_content[:] = [grounded_route_answer]
                        final_answer_parts[:] = [grounded_route_answer]
                    final_content = "".join(pending_ai_content)
                    if any(action.get("action", {}).get("kind") == "image_generate" for action in pending_actions):
                        final_content = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", final_content).strip()
                    if final_content:
                        await queue.put(presenter.token(final_content))
            except Exception as exc:
                logging.exception("chat stream failed conversation=%s", conversation_id)
                run_error = public_error(exc, response_language)
                run_diagnostics = safe_error_diagnostics(
                    exc, stage="graph_stream",
                )
                await queue.put(
                    presenter.error("generation_error", run_error)
                )
                if bool(body.get("_diagnostics")):
                    await queue.put(
                        presenter.diagnostics(run_diagnostics),
                    )
            except asyncio.CancelledError:
                # abortActiveRun is the platform-owned cancellation path.  A
                # browser disconnect does not cancel this detached producer.
                latest_run = await read_chat_run(ctx.store, conversation_id)
                cancelled = run_cancelled(latest_run)
                if not cancelled:
                    run_error = text("chat.run_interrupted", response_language)
            finally:
                final_answer = "".join(final_answer_parts).strip()
                empty_error = empty_generation_error(
                    final_answer,
                    has_actions=bool(pending_actions),
                    clarification_emitted=clarification_emitted,
                    run_error=run_error,
                    cancelled=cancelled,
                    response_language=response_language,
                )
                if empty_error:
                    run_error = empty_error
                    await queue.put(
                        presenter.error("empty_generation", run_error)
                    )
                follow_ups: list[str] = []
                if final_answer:
                    # Stop the visible cursor immediately when answer tokens
                    # finish. The already-running follow-up job may land a
                    # moment later, but it must never create a second pause.
                    await queue.put(presenter.progress(
                        "synthesis",
                        "completed",
                    ))
                    await queue.put(presenter.progress(
                        "finalizing",
                        "completed",
                    ))
                    await queue.put(presenter.progress(
                        "complete",
                        "completed",
                    ))
                    hints = experience_hints_for_plan(
                        answer_capability_plan,
                        auth_type=str(identity.get("auth_type") or "guest"),
                    )
                    if hints:
                        await queue.put(
                            presenter.experience_hints(hints),
                        )
                    await queue.put(presenter.done(run_id))
                    if follow_up_task is not None:
                        if not clarification_emitted and not run_error:
                            try:
                                follow_ups = await asyncio.wait_for(
                                    asyncio.shield(follow_up_task), timeout=3,
                                )
                            except Exception as exc:
                                logging.warning("parallel follow-up generation failed: %s", exc)
                                if not follow_up_task.done():
                                    follow_up_task.cancel()
                        elif not follow_up_task.done():
                            follow_up_task.cancel()
                    if follow_ups:
                        await queue.put(presenter.follow_ups(follow_ups))
                    try:
                        await persist_answer_extras(follow_ups)
                    except Exception as exc:
                        logging.warning("answer follow-up persistence failed: %s", exc)
                else:
                    for task in (follow_up_task, memory_task, recent_questions_task):
                        if task is not None and not task.done():
                            task.cancel()
                if search_runner.background_tasks:
                    try:
                        outcomes = await asyncio.wait_for(
                            asyncio.gather(
                                *search_runner.background_tasks,
                                return_exceptions=True,
                            ),
                            timeout=90,
                        )
                        for outcome in outcomes:
                            if isinstance(outcome, Exception):
                                logging.warning("rich search media task failed: %s", outcome)
                    except asyncio.TimeoutError:
                        logging.warning("rich search media task timed out")
                        for task in search_runner.background_tasks:
                            if not task.done():
                                task.cancel()
                # Reviewed media is already a complete user-visible result.
                # Save it before slower optional post-processing so navigation
                # cannot make the image disappear when one of those jobs fails.
                if final_answer and search_runner.latest_enriched_media:
                    try:
                        await persist_answer_extras()
                    except Exception as exc:
                        logging.warning("answer media persistence failed: %s", exc)
                if final_answer and (memory_task is not None or opportunity_enabled):
                    try:
                        recent_questions = []
                        if recent_questions_task is not None:
                            try:
                                recent_questions = await asyncio.wait_for(
                                    asyncio.shield(recent_questions_task),
                                    timeout=1.5,
                                )
                            except Exception:
                                recent_questions = []
                        opportunity_task = (
                            asyncio.create_task(detect_opportunity(
                                fast_model,
                                user_message=message,
                                answer=final_answer,
                                capability_plan=capability_plan,
                                memory_context=(
                                    memory_context
                                    if capability_plan.get("use_memory_context")
                                    else ""
                                ),
                                recent_questions=recent_questions,
                                has_pending_action=any(
                                    action.get("action", {}).get("status") in {"awaiting_confirmation", "ready"}
                                    for action in pending_actions
                                ),
                                timeout_seconds=float(ctx.env.get("OPPORTUNITY_PLAN_TIMEOUT_SECONDS") or 6),
                                response_language=response_language,
                            ))
                            if opportunity_enabled
                            else None
                        )
                        optional_jobs = [
                            task for task in (memory_task, opportunity_task)
                            if task is not None
                        ]
                        optional_results = await asyncio.wait_for(
                            asyncio.gather(*optional_jobs), timeout=8,
                        )
                        result_index = 0
                        memory_candidates = []
                        opportunity = None
                        if memory_task is not None:
                            memory_candidates = optional_results[result_index]
                            result_index += 1
                        if opportunity_task is not None:
                            opportunity = optional_results[result_index]
                        await persist_answer_extras(follow_ups)
                        if memory_candidates:
                            latest_intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
                            if apply_automatic_memory_candidates(
                                latest_intelligence,
                                memory_candidates,
                                source_message_id=str(body.get("client_message_id") or ""),
                            ):
                                await save_intelligence_state(ctx.store.langgraph_store, latest_intelligence, user_id)
                        if opportunity and ctx.store.langgraph_store is not None:
                            now = int(time.time())
                            proactive_state = await load_proactive_state(ctx.store.langgraph_store, user_id)
                            source_id = str(body.get("client_message_id") or run_id)
                            opportunity_stats = process_schedule_signals(
                                proactive_state,
                                [opportunity_signal(opportunity, source_id=source_id, now=now)],
                                now,
                            )
                            if opportunity_stats.get("notifications_created"):
                                proactive_state.setdefault("checkpoints", {})["semantic_opportunity"] = {
                                    "last_detected_at": now,
                                    "type": opportunity.get("type"),
                                    "source_id": source_id,
                                }
                                proactive_state = await save_proactive_state(
                                    ctx.store.langgraph_store, proactive_state, user_id,
                                )
                                await queue.put(presenter.proactive_update(
                                    public_proactive_state(proactive_state),
                                ))
                    except Exception as exc:
                        logging.warning("answer extras generation failed: %s", exc)
                if pending_search_results is not None:
                    await queue.put(presenter.sources(pending_search_results))
                if pending_papers is not None:
                    await queue.put(presenter.papers(pending_papers))
                latest_run = await read_chat_run(ctx.store, conversation_id)
                owns_run = not (
                    isinstance(latest_run, dict)
                    and latest_run.get("run_id")
                    and str(latest_run.get("run_id")) != run_id
                )
                if owns_run:
                    cancelled = cancelled or run_cancelled(latest_run)
                    await write_chat_run(
                        ctx.store,
                        conversation_id,
                        run_id=run_id,
                        status="cancelled" if cancelled else ("failed" if run_error else "completed"),
                        error=run_error,
                        diagnostics=run_diagnostics,
                    )
                if any(usage):
                    try:
                        latest_intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
                        record_usage(latest_intelligence, usage[0], usage[1], usage[2] or usage[0] + usage[1], "chat")
                        await save_intelligence_state(ctx.store.langgraph_store, latest_intelligence, user_id)
                    except Exception as exc:
                        logging.warning("usage persistence failed: %s", exc)
                    await queue.put(presenter.usage(
                        usage[0],
                        usage[1],
                        usage[2] or usage[0] + usage[1],
                    ))
                await queue.put(done)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield presenter.ping(int(time.time() * 1000))
                    continue
                if frame is done:
                    break
                yield frame
        except GeneratorExit:
            # Closing the SSE subscriber must not close the Makers run. Keep
            # this invocation alive until LangGraph writes its final checkpoint.
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(producer)
            return
        except asyncio.CancelledError:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(producer)
            raise
        finally:
            if producer.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
        yield presenter.transport_done()

    return ctx.utils.stream_sse(gen())
