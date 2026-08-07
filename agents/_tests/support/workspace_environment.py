from __future__ import annotations

import asyncio
import base64
import unittest
import json
import ast
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.chat._capability_plan import (
    CapabilityPlan,
    fallback_tools_for_prompt_topics,
    media_enabled_for_plan,
    parse_capability_plan,
    plan_capabilities,
    plan_capabilities_bounded,
    plan_required_clarification,
    progressive_media_for_plan,
    select_prompt_topics,
    next_required_tool,
    required_tool_for_plan,
    required_tools_for_plan,
)
from agents._application.chat.skill_policy import apply_runtime_skill_policy
from agents.chat._followups import (
    generate_followups,
    parse_followups,
    should_generate_followups,
)
from agents.chat._llm import _model_timeout
from agents.chat._history import (
    bounded_history,
    compact_tool_results_for_model,
    flatten_completed_tools_for_model,
    valid_model_history,
)
from agents.chat._calendar_context import calendar_context, latest_route_context
from agents.chat._graph import action_completion_fallback, tool_failure_fallback, tool_result_fallback
from agents._application.chat.turn_io import (
    checkpoint_dialogue_context,
    checkpoint_final_answer,
    hydrate_durable_map_action,
)
from agents._application.chat.turn_policy import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_SECTIONS,
    SYSTEM_PROMPT_SECTION_ORDER,
    direct_paper_tool_arguments,
    empty_generation_error,
    dynamic_system_prompt,
    runtime_datetime_context,
    should_buffer_public_answer,
    tools_for_capability_stage,
)
from agents._application.chat.turn_protocol import (
    capability_planning_message,
    checkpoint_clarification_answers,
    checkpoint_clarification_state,
    clarification_response_answers,
    clarification_response_id,
    graph_user_message,
    resume_capability_protocol,
    should_persist_user_message,
)
from agents._infrastructure.skills.builtin_operations import build_system_skill_tools
from agents._infrastructure.skills.paper_candidates import (
    _paper_candidate_ids_from_model,
    _paper_candidates_from_searchpro,
)
from agents._infrastructure.skills.route_resolution import (
    preserve_planned_route_stops,
    verify_place_queries_parallel,
)
from agents.chat._protocol import MarkdownImageStreamFilter, PublicStreamFilter, StreamDeltaNormalizer, action_fallback_content, checkpoint_recovery_needed, dsml_tool_calls, public_content, public_error, safe_error_diagnostics
from agents.messages.index import handler as messages_handler
from agents._infrastructure.providers.side_effects import (
    _cloudflare_image_prompt,
    _post_cloudflare_image,
    _post_image_v3,
    _post_tencent_meeting_mcp,
    generate_image,
)
from agents._infrastructure.providers.vision import (
    VisionProvider,
    _post_completion,
    describe_reference_images,
    vision_providers,
)
from agents._infrastructure.makers.identity import require_user, scoped_conversation_id
from agents._infrastructure.makers.data_version import CONVERSATION_PREFIX
from agents._infrastructure.providers.rich_search import (
    _parse_pages,
    _review_image,
    _vision_filter,
    _vision_review_timeout,
    evidence_for_model,
    rich_search as run_rich_search,
)
from agents._domain.search.source_policy import (
    filter_sources_for_target_date,
    rank_source_results,
)
from agents._infrastructure.providers.arxiv import (
    _best_title_match,
    _canonical_arxiv_id,
    _dblp_profile,
    _paper_matches_topic,
    _search_openalex_sync,
    search_arxiv,
)
from agents._infrastructure.providers.tencent_location import (
    decode_polyline,
    place_distance_meters,
    reverse_geocode,
    search_verified_places,
    search_verified_places_nearby,
)
from agents._application.workspace.service import (
    apply_calendar_changes,
    calendar_change_warnings,
    begin_action_execution,
    empty_workspace,
    image_versions,
    load_user_workspace,
    load_workspace,
    meeting_action_payload,
    new_action,
    normalize_schedule,
    put_action,
    save_user_workspace,
    save_workspace,
    finish_provider_call,
    recover_stale_actions,
    start_provider_call,
    verify_action_snapshot,
    validate_calendar_change_window,
)
from agents._application.proactive.service import (
    classify_weather_risk,
    collect_schedule_signals,
    collect_workflow_signals,
    decide_workflow,
    decide_workflow_step,
    empty_proactive_state,
    load_proactive_state,
    mutate_notification,
    process_schedule_signals,
    propose_workflow,
    public_proactive_state,
    run_proactive_tick,
    save_proactive_state,
    update_preferences,
    ingest_workspace_signal,
)
from agents._application.intelligence.service import (
    apply_automatic_memory_candidates,
    confirm_memory,
    confirmed_memory_context,
    empty_intelligence_state,
    load_intelligence_state,
    propose_memory,
    prune_automatic_memories,
    public_intelligence_state,
    record_feedback,
    record_usage,
    rollback_memory,
    save_intelligence_state,
    usage_summary,
)
from agents._application.proactive.memory import infer_memory_reminder
from agents.workspace.index import handler
from agents._tests.auth_helpers import (
    TEST_USER_ID,
    auth_env,
    auth_headers,
    authenticated_namespace,
)


PLACE = {
    "place_id": "poi-1",
    "provider": "tencent",
    "name": "故宫博物院",
    "address": "北京市东城区景山前街4号",
    "latitude": 39.9163,
    "longitude": 116.3972,
}



from agents._tests.support.fakes import (
    FakeCheckpointer,
    FakeContext,
    FakeRequest,
    FakeStore,
    FakeStores,
    FailingStructuredPlannerModel,
    MakersCheckpointMessage,
    RecoveringStructuredPlannerModel,
    StructuredPlannerModel,
)

AGENTS_ROOT = Path(__file__).resolve().parents[2]

__all__ = [name for name in globals() if not name.startswith('__')]
