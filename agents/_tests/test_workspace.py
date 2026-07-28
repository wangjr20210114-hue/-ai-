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
    apply_runtime_skill_policy,
    fallback_tools_for_prompt_topics,
    media_enabled_for_plan,
    parse_capability_plan,
    plan_capabilities,
    plan_capabilities_bounded,
    plan_required_clarification,
    select_prompt_topics,
    next_required_tool,
    required_tool_for_plan,
    required_tools_for_plan,
)
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
from agents.chat.index import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_SECTIONS,
    SYSTEM_PROMPT_SECTION_ORDER,
    capability_planning_message,
    checkpoint_clarification_answers,
    checkpoint_clarification_state,
    checkpoint_dialogue_context,
    checkpoint_final_answer,
    clarification_response_answers,
    clarification_response_id,
    direct_paper_tool_arguments,
    empty_generation_error,
    graph_user_message,
    dynamic_system_prompt,
    runtime_datetime_context,
    resume_capability_protocol,
    should_buffer_public_answer,
    should_persist_user_message,
    tools_for_capability_stage,
)
from agents.chat._ui_tools import (
    _paper_candidate_ids_from_model,
    _paper_candidates_from_searchpro,
    build_production_tools,
    preserve_planned_route_stops,
    verify_place_queries_parallel,
)
from agents.chat._protocol import PublicStreamFilter, StreamDeltaNormalizer, action_fallback_content, checkpoint_recovery_needed, dsml_tool_calls, public_content, public_error, safe_error_diagnostics
from agents.messages.index import handler as messages_handler
from agents._shared.side_effects import (
    _cloudflare_image_prompt,
    _post_cloudflare_image,
    _post_image_v3,
    _post_tencent_meeting_mcp,
    generate_image,
)
from agents._shared.vision import (
    VisionProvider,
    _post_completion,
    describe_reference_images,
    vision_providers,
)
from agents._shared.auth import require_user, scoped_conversation_id
from agents._shared.data_version import CONVERSATION_PREFIX
from agents._shared.rich_search import (
    _filter_for_target_date,
    _parse_pages,
    _review_image,
    _vision_filter,
    _vision_review_timeout,
    evidence_for_model,
    rich_search as run_rich_search,
)
from agents._shared.arxiv import (
    _best_title_match,
    _canonical_arxiv_id,
    _dblp_profile,
    _search_openalex_sync,
    search_arxiv,
)
from agents._shared.tencent_location import (
    decode_polyline,
    place_distance_meters,
    reverse_geocode,
    search_verified_places,
    search_verified_places_nearby,
)
from agents._shared.workspace import (
    USER_WORKSPACE_ID,
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
from agents._shared.proactive import (
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
from agents._shared.intelligence import (
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
from agents._shared.proactive_memory import infer_memory_reminder
from agents.workspace.index import handler


PLACE = {
    "place_id": "poi-1",
    "provider": "tencent",
    "name": "故宫博物院",
    "address": "北京市东城区景山前街4号",
    "latitude": 39.9163,
    "longitude": 116.3972,
}


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeCheckpointer:
    def __init__(self, messages):
        self.messages = messages

    async def aget_tuple(self, _config):
        return {"checkpoint": {"channel_values": {"messages": self.messages}}}


class MakersCheckpointMessage:
    """Mimic Makers' field proxy, which raises KeyError for missing fields."""

    def __init__(self, **values):
        self.values = values

    def __getattr__(self, key):
        if key in self.values:
            return self.values[key]
        raise KeyError(key)


class StructuredPlannerModel:
    def __init__(
        self,
        args=None,
        delay=0,
        topic_args=None,
        clarification_args=None,
        preflight_args=None,
    ):
        self.calls = 0
        self.args = args or {
            "needs_web_search": True,
            "needs_images": True,
            "search_query": "故宫历史",
            "image_query": "故宫建筑",
        }
        self.delay = delay
        self.topic_args = topic_args or {"topics": []}
        self.clarification_args = clarification_args or {
            "needs_clarification": False,
        }
        self.preflight_args = preflight_args or {
            **self.clarification_args,
            "topics": list(self.topic_args.get("topics") or []),
        }
        self.messages = []
        self.tool_choice = ""
        self.tools = []
        self.schema = None
        self.method = ""
        self.include_raw = False

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        self.method = kwargs.get("method", "")
        self.include_raw = bool(kwargs.get("include_raw"))
        return self

    async def ainvoke(self, messages):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls += 1
        self.messages = messages
        values = (
            self.preflight_args
            if self.schema.__name__ == "SemanticPreflight"
            else self.topic_args
            if self.schema.__name__ == "PromptTopicSelection"
            else self.args
        )
        if self.schema.__name__ == "CapabilityPlan":
            values = {"capabilities": [], **values}
        return {
            "parsed": self.schema(**values),
            "raw": SimpleNamespace(content=""),
            "parsing_error": None,
        }


class FailingStructuredPlannerModel(StructuredPlannerModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages = messages
        raise RuntimeError("structured planner rejected the request")


class RecoveringStructuredPlannerModel(StructuredPlannerModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages = messages
        if self.schema.__name__ == "CapabilityPlan":
            raise RuntimeError(
                "Error code: 400 - invalid_request: request envelope rejected"
            )
        values = {
            "needs_clarification": False,
            "topics": ["web"],
            "capabilities": ["web_search"],
            "needs_web_search": True,
            "strict_today_only": True,
            "search_query": "2026-07-29 AI 新闻",
            "needs_images": False,
        }
        return {
            "parsed": self.schema(**values),
            "raw": SimpleNamespace(content=""),
            "parsing_error": None,
        }


class FakeRequest:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}


class FakeStores:
    def __init__(self, store):
        self.langgraph_store = store


class FakeContext:
    def __init__(self, store, body):
        self.conversation_id = "conversation-1"
        self.store = FakeStores(store)
        self.request = FakeRequest(body)
        self.env = {}


class WorkspaceUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_datetime_context_includes_authoritative_weekday(self):
        value = datetime(
            2026, 7, 25, 15, 30,
            tzinfo=timezone(timedelta(hours=8)),
        )
        context = runtime_datetime_context(value)
        self.assertIn("2026-07-25 15:30:00 UTC+08:00", context)
        self.assertIn("weekday=Saturday（周六）", context)
        self.assertIn("禁止自行重新推算", SYSTEM_PROMPT)

    def test_model_timeout_is_bounded_for_fast_failover(self):
        self.assertEqual(_model_timeout({}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 12)
        self.assertEqual(_model_timeout({"AI_GATEWAY_TIMEOUT_SECONDS": "999"}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 30)
        self.assertEqual(_model_timeout({"AI_GATEWAY_TIMEOUT_SECONDS": "1"}, "AI_GATEWAY_TIMEOUT_SECONDS", 12), 5)

    def test_generic_provider_400_is_not_misreported_as_bad_configuration(self):
        message = public_error("Error code: 400 - invalid_request: malformed conversation history")
        self.assertIn("本轮上下文", message)
        self.assertNotIn("配置异常", message)

    def test_personal_runtime_uses_one_fixed_owner_and_versioned_conversation_id(self):
        ctx = SimpleNamespace(request=FakeRequest({}), conversation_id="conversation-personal")
        self.assertEqual(require_user(ctx)["user_id"], USER_WORKSPACE_ID)
        self.assertEqual(require_user(ctx)["roles"], ["owner"])
        self.assertTrue(scoped_conversation_id(ctx, USER_WORKSPACE_ID).endswith("conversation-personal"))
        self.assertTrue(scoped_conversation_id(ctx, USER_WORKSPACE_ID).startswith(CONVERSATION_PREFIX))
        self.assertLessEqual(len(scoped_conversation_id(ctx, USER_WORKSPACE_ID)), 36)

    def test_long_history_is_trimmed_at_human_boundary(self):
        messages = [SimpleNamespace(type="human", content=f"q{index}") if index % 3 == 0
                    else SimpleNamespace(type="ai", content=f"a{index}") for index in range(60)]
        trimmed = bounded_history(messages, limit=20)
        self.assertLessEqual(len(trimmed), 20)
        self.assertEqual(trimmed[0].type, "human")
        self.assertEqual(trimmed[-1].content, "a59")

    def test_interrupted_tool_protocol_is_removed_before_next_model_call(self):
        messages = [
            {"role": "user", "content": "规划路线"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "route-1", "name": "plan_route_between_places", "args": {}},
            ]},
            # The browser stopped before ToolNode wrote route-1.
            {"role": "user", "content": "改成写入明天日程"},
        ]
        self.assertEqual(valid_model_history(messages), [
            {"role": "user", "content": "规划路线"},
            {"role": "user", "content": "改成写入明天日程"},
        ])

    def test_complete_tool_protocol_is_preserved_for_model_context(self):
        messages = [
            {"role": "user", "content": "规划路线"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "route-1", "name": "plan_route_between_places", "args": {}},
            ]},
            {"role": "tool", "content": "路线完成", "tool_call_id": "route-1"},
            {"role": "assistant", "content": "路线如下"},
        ]
        self.assertEqual(valid_model_history(messages), messages)

    def test_route_action_is_compacted_only_for_the_next_model_input(self):
        original = ToolMessage(
            name="plan_route_between_places",
            tool_call_id="route-1",
            content=json.dumps({
                "ui_action": "map_action",
                "route_plan_id": "route-plan-1",
                "ordered_stops": [{
                    "place_id": "poi-1",
                    "name": "北京站",
                    "address": "一段无需传给日程模型的详细地址",
                    "latitude": 39.9,
                    "longitude": 116.4,
                }],
                "route": {"duration_minutes": 30},
                "evidence_contract": {
                    "strict": True,
                    "unknown_fields": ["operating_hours"],
                },
                "action": {
                    "id": "map-1",
                    "kind": "map_recommendation",
                    "status": "ready",
                    "payload": {"places": [{"large": "x" * 2000}]},
                },
            }, ensure_ascii=False),
        )
        compacted = compact_tool_results_for_model([original])[0]
        self.assertLess(len(compacted.content), len(original.content) / 3)
        payload = json.loads(compacted.content)
        self.assertEqual(payload["ordered_stops"][0]["place_id"], "poi-1")
        self.assertNotIn("address", payload["ordered_stops"][0])
        self.assertTrue(payload["evidence_contract"]["strict"])
        self.assertEqual(
            payload["evidence_contract"]["unknown_fields"],
            ["operating_hours"],
        )
        self.assertEqual(original.content.count("x"), 2000)

    def test_completed_tool_transport_is_flattened_for_deepseek_followup(self):
        messages = [
            HumanMessage(content="查论文"),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_arxiv",
                    "args": {"topic": "continual learning"},
                    "id": "paper-1",
                }],
            ),
            ToolMessage(
                content='{"ui_action":"paper_results","papers":[]}',
                name="search_arxiv",
                tool_call_id="paper-1",
            ),
        ]
        flattened = flatten_completed_tools_for_model(messages)
        self.assertEqual(len(flattened), 2)
        self.assertEqual(flattened[0].type, "human")
        self.assertEqual(flattened[1].type, "ai")
        self.assertFalse(getattr(flattened[1], "tool_calls", None))
        payload = json.loads(flattened[1].content)
        self.assertIn("not user instructions", payload["floris_observation"])
        self.assertEqual(payload["results"][0]["tool"], "search_arxiv")
        self.assertIn('"papers":[]', payload["results"][0]["data"])

    def test_clarification_response_is_model_visible_but_marked_ui_hidden(self):
        body = {
            "interaction_mode": "clarification",
            "clarification_response": {"id": "trip-date"},
        }
        clarification_id = clarification_response_id(body)
        self.assertEqual(clarification_id, "trip-date")
        answers = clarification_response_answers({
            "interaction_mode": "clarification",
            "clarification_response": {
                "answers": [{
                    "id": "trip_date",
                    "label": "出发日期",
                    "value": "2026-08-01",
                }],
            },
        })
        self.assertEqual(graph_user_message(
            "出发日期：2026-08-01", clarification_id, answers,
        ), {
            "role": "user",
            "content": "出发日期：2026-08-01",
            "additional_kwargs": {
                "floris_ui_hidden": True,
                "floris_interaction": "clarification",
                "clarification_id": "trip-date",
                "floris_answers": [{
                    "id": "trip_date",
                    "label": "出发日期",
                    "value": "2026-08-01",
                }],
            },
        })
        self.assertEqual(clarification_response_id({
            "interaction_mode": "chat",
            "clarification_response": {"id": "trip-date"},
        }), "")
        self.assertFalse(should_persist_user_message(body))
        self.assertTrue(should_persist_user_message({"interaction_mode": "chat"}))

    def test_clarification_capability_plan_keeps_original_user_goal(self):
        self.assertEqual(
            capability_planning_message(
                "明天出发时间：07:04",
                "trip-time",
                ["从桔子酒店出发，先去北京站，再去锦江并写入日程"],
            ),
            (
                "[这是用户对上一轮结构化问题的补充答案，请结合原始目标规划尚未完成的能力；"
                "所有先前补充答案仍然有效，不要把答案误判为独立新问题或重复询问。]\n"
                "上一轮原始目标：从桔子酒店出发，先去北京站，再去锦江并写入日程\n"
                "本次补充答案：明天出发时间：07:04"
            ),
        )

    async def test_route_clarification_planning_keeps_all_prior_card_answers(self):
        messages = [
            HumanMessage(content="规划六站路线"),
            AIMessage(content=""),
            HumanMessage(
                content="第 4 站：北京通州万达广场",
                additional_kwargs={
                    "floris_interaction": "clarification",
                    "clarification_id": "route-stop-4",
                },
            ),
            AIMessage(content=""),
            HumanMessage(
                content="终点：北京西站",
                additional_kwargs={
                    "floris_interaction": "clarification",
                    "clarification_id": "route-stop-6",
                },
            ),
            AIMessage(content=""),
        ]
        answers = await checkpoint_clarification_answers(
            FakeCheckpointer(messages),
            "route-clarification-context",
        )
        self.assertEqual(
            answers,
            ["第 4 站：北京通州万达广场", "终点：北京西站"],
        )
        planning = capability_planning_message(
            "第 5 站：中国人民解放军总医院第一医学中心",
            "route-stop-5",
            ["规划六站路线"],
            answers,
        )
        self.assertIn("北京通州万达广场", planning)
        self.assertIn("北京西站", planning)
        self.assertIn("中国人民解放军总医院第一医学中心", planning)

    async def test_capability_planning_resolves_ordinal_from_bounded_dialogue(self):
        messages = [
            HumanMessage(content="给我推荐六个小众景点"),
            AIMessage(content=(
                "1. 圆明园遗址公园\n2. 西山国家森林公园\n"
                "3. 凤凰岭自然风景区\n4. 百望山森林公园\n"
                "5. 鹫峰国家森林公园\n6. 翠湖国家城市湿地公园"
            )),
        ]
        dialogue = await checkpoint_dialogue_context(
            FakeCheckpointer(messages),
            "ordinal-reference",
            "我想去第四个",
        )
        planning = capability_planning_message(
            "我想去第四个",
            recent_dialogue=dialogue,
        )
        self.assertIn("4. 百望山森林公园", planning)
        self.assertIn("不要把“第几个/那个/它”当作地点名称", planning)
        self.assertTrue(planning.endswith("我想去第四个"))

    async def test_checkpoint_recovers_structured_answers_and_resume_protocol_once(self):
        messages = [
            HumanMessage(content="规划六站路线并写入日程"),
            AIMessage(
                content="",
                additional_kwargs={"floris_resume": {
                    "version": 1,
                    "required_tools": [
                        "plan_route_between_places",
                        "propose_calendar_changes",
                    ],
                    "planned_tool_arguments": {
                        "plan_route_between_places": {
                            "ordered_stops": [
                                {"query": "北京站", "near_query": ""},
                                {"query": "万达广场", "near_query": ""},
                                {"query": "咕咕塔XYZ", "near_query": ""},
                            ],
                            "route_strategy": "default",
                        },
                    },
                }},
            ),
            HumanMessage(
                content="第 2 站：通州万达广场",
                additional_kwargs={
                    "floris_interaction": "clarification",
                    "clarification_id": "route-stop-2",
                    "floris_answers": [{
                        "id": "route_stop_2",
                        "label": "第 2 站",
                        "value": "北京通州万达广场｜北京市通州区",
                    }],
                },
            ),
            AIMessage(
                content="",
                additional_kwargs={"floris_resume": {
                    "version": 1,
                    "required_tools": [
                        "plan_route_between_places",
                        "propose_calendar_changes",
                    ],
                    "planned_tool_arguments": {
                        "plan_route_between_places": {
                            "ordered_stops": [
                                {"query": "北京站", "near_query": ""},
                                {"query": "北京通州万达广场｜北京市通州区", "near_query": ""},
                                {"query": "咕咕塔XYZ", "near_query": ""},
                            ],
                            "route_strategy": "default",
                        },
                    },
                }},
            ),
        ]
        state = await checkpoint_clarification_state(
            FakeCheckpointer(messages),
            "route-clarification-protocol",
        )
        self.assertEqual(state["answer_texts"], ["第 2 站：通州万达广场"])
        self.assertEqual(state["answers"][0]["id"], "route_stop_2")
        self.assertEqual(
            state["resume"]["required_tools"],
            ["plan_route_between_places", "propose_calendar_changes"],
        )

    def test_resume_protocol_preserves_chain_and_applies_route_field_ids(self):
        plan, arguments = resume_capability_protocol(
            {
                "needs_route": False,
                "needs_calendar_action": False,
                "route_strategy": "least_time",
            },
            {
                "version": 1,
                "required_tools": [
                    "plan_route_between_places",
                    "propose_calendar_changes",
                ],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "city": "北京",
                        "route_mode": "transit",
                        "route_strategy": "default",
                        "ordered_stops": [
                            {"query": "北京站", "near_query": ""},
                            {"query": "万达广场", "near_query": ""},
                            {"query": "咕咕塔XYZ", "near_query": ""},
                            {"query": "北京西站", "near_query": ""},
                        ],
                    },
                },
            },
            [
                {
                    "id": "route_stop_2",
                    "value": "北京通州万达广场｜北京市通州区",
                },
                {
                    "id": "route_stop_3_a1b2c3",
                    "value": "中国人民革命军事博物馆",
                },
            ],
        )
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_context"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(plan["route_strategy"], "default")
        self.assertEqual(
            [stop["query"] for stop in plan["route_stops"]],
            [
                "北京站",
                "北京通州万达广场｜北京市通州区",
                "中国人民革命军事博物馆",
                "北京西站",
            ],
        )
        self.assertEqual(
            arguments["plan_route_between_places"]["ordered_stops"],
            plan["route_stops"],
        )

    def test_resume_protocol_applies_nearby_anchor_choice(self):
        plan, arguments = resume_capability_protocol(
            {"needs_nearby_places": False},
            {
                "version": 1,
                "required_tools": ["recommend_nearby_places_on_map"],
                "planned_tool_arguments": {
                    "recommend_nearby_places_on_map": {
                        "anchor_query": "北京天安门",
                        "anchor_queries": [],
                        "query": "景点",
                        "use_current_location_as_anchor": False,
                    },
                },
            },
            [{
                "id": "anchor_0",
                "value": "天安门广场｜北京市东城区东长安街",
            }],
        )
        expected_anchor = "天安门广场｜北京市东城区东长安街"
        self.assertTrue(plan["needs_nearby_places"])
        self.assertEqual(plan["nearby_anchor_query"], expected_anchor)
        self.assertEqual(plan["nearby_query"], "景点")
        self.assertEqual(
            arguments["recommend_nearby_places_on_map"]["anchor_query"],
            expected_anchor,
        )

    def test_resume_protocol_turns_manual_location_into_nearby_anchor(self):
        plan, arguments = resume_capability_protocol(
            {"needs_nearby_places": False},
            {
                "version": 1,
                "required_tools": ["recommend_nearby_places_on_map"],
                "planned_tool_arguments": {
                    "recommend_nearby_places_on_map": {
                        "anchor_query": "",
                        "anchor_queries": [],
                        "query": "公园",
                        "use_current_location_as_anchor": True,
                    },
                },
            },
            [{
                "id": "nearby_anchor",
                "value": "北京市海淀区中关村",
            }],
        )
        nearby = arguments["recommend_nearby_places_on_map"]
        self.assertEqual(nearby["anchor_query"], "北京市海淀区中关村")
        self.assertFalse(nearby["use_current_location_as_anchor"])
        self.assertFalse(plan["nearby_uses_current_location"])

    async def test_capability_planner_uses_langchain_structured_output(self):
        model = StructuredPlannerModel()
        plan = await plan_capabilities(model, "能给我讲讲故宫的历史吗")
        self.assertEqual(model.calls, 1)
        self.assertEqual(model.schema.__name__, "CapabilityPlan")
        self.assertEqual(model.method, "function_calling")
        self.assertTrue(model.include_raw)
        self.assertTrue(plan["needs_web_search"])
        self.assertTrue(plan["needs_images"])
        self.assertEqual(plan["image_query"], "故宫建筑")

    async def test_capability_planner_receives_filtered_memory_context(self):
        model = StructuredPlannerModel({"needs_web_search": False})
        await plan_capabilities(model, "帮我规划旅行", "- preference.travel: 喜欢安静的博物馆")
        system_prompt = model.messages[0]["content"]
        self.assertIn("喜欢安静的博物馆", system_prompt)
        self.assertIn("不得把姓名、联系方式", system_prompt)

    async def test_prompt_sections_are_selected_by_structured_semantics(self):
        model = StructuredPlannerModel(topic_args={"topics": ["maps", "calendar"]})
        topics = await select_prompt_topics(
            model,
            "请处理这个跨领域目标",
        )
        self.assertEqual(topics, ("maps", "calendar"))
        self.assertEqual(model.schema.__name__, "PromptTopicSelection")
        self.assertEqual(model.method, "function_calling")
        self.assertNotIn("关键词", model.messages[0]["content"])
        self.assertEqual(
            fallback_tools_for_prompt_topics(("paper",)),
            ("search_arxiv",),
        )

    async def test_missing_source_content_is_planned_as_structured_card(self):
        model = StructuredPlannerModel({
            "needs_clarification": True,
            "clarification_title": "请提供需要处理的内容",
            "clarification_prompt": "本轮没有收到原文。",
            "clarification_fields": [{
                "id": "source_content",
                "label": "需要处理的原文",
                "type": "text",
                "required": True,
                "placeholder": "请粘贴文字内容",
            }],
        })
        plan = await plan_capabilities(
            model,
            "把下面这段文字翻译成英文",
            prompt_topics=(),
        )
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(
            plan["clarification_fields"][0]["id"],
            "source_content",
        )

    async def test_single_semantic_plan_returns_all_blocking_fields_once(self):
        model = StructuredPlannerModel(args={
            "needs_clarification": True,
            "clarification_title": "请提供需要处理的内容",
            "clarification_prompt": "本轮没有收到原文。",
            "clarification_fields": [{
                "id": "source_content",
                "label": "需要处理的原文",
                "type": "text",
                "required": True,
            }],
        })
        timings = {}
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "一种没有固定短语的新表达",
            timeout_seconds=1,
            timings_ms=timings,
        )
        self.assertFalse(timed_out)
        self.assertEqual(model.calls, 1)
        self.assertIn("semantic_plan", timings)
        self.assertIn("capability_planning_total", timings)
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(plan["clarification_fields"][0]["id"], "source_content")

    async def test_single_semantic_plan_omits_invented_optional_clarification(self):
        model = StructuredPlannerModel(
            args={
                "needs_route": True,
                "needs_calendar_action": True,
                "route_stops": [{"query": "颐和园"}],
                "route_uses_current_location": True,
            },
        )
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "从本轮浏览器位置去颐和园并生成日程提案",
            location_context="浏览器位置已授权且新鲜，可作为本轮起点",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(model.calls, 1)

    async def test_single_plan_preserves_dependent_route_calendar_chain(self):
        model = StructuredPlannerModel(
            args={
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "route_stops": [
                    {"query": "北京站"},
                    {"query": "北京西站"},
                ],
                "prompt_topics": ["maps", "calendar"],
            },
        )
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "一种没有固定短语的跨能力行程请求",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_context"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places", "propose_calendar_changes"),
        )

    async def test_paper_capability_checksum_prevents_plain_answer_bypass(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            # Reproduce the observed gateway inconsistency: the semantic
            # capability is present while its detailed boolean was omitted.
            "needs_papers": False,
            "paper_topic": "",
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_identity_evidence_supplied": True,
            "paper_year_from": 2025,
            "paper_year_to": 2026,
            "paper_limit": 2,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "给我找两篇复旦大学彭鑫老师近2年的论文",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_papers"])
        self.assertEqual(plan["_capabilities"], ["papers"])
        self.assertEqual(required_tools_for_plan(plan), ("search_arxiv",))
        self.assertEqual(
            direct_paper_tool_arguments(plan)["search_arxiv"]["limit"],
            2,
        )
        self.assertEqual(
            direct_paper_tool_arguments(plan)["search_arxiv"]["topic"],
            "",
        )

    async def test_ambiguous_paper_author_is_stopped_before_search(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            "needs_papers": True,
            "paper_author": "Xin Peng",
            "paper_limit": 2,
            "paper_identity_evidence_supplied": False,
            "paper_identity_globally_unambiguous": False,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "Find two papers by the professor I named.",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_clarification"])
        self.assertFalse(plan["needs_papers"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(
            plan["clarification_fields"][0]["id"],
            "paper-author-identity",
        )

    async def test_user_supplied_paper_identity_reaches_search(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            "needs_papers": True,
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_identity_evidence_supplied": True,
            "paper_identity_globally_unambiguous": False,
            "paper_limit": 2,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "Find two papers by the identified professor.",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_papers"])
        self.assertEqual(required_tools_for_plan(plan), ("search_arxiv",))

    def test_prompt_topic_does_not_execute_paper_without_capability(self):
        plan = parse_capability_plan({
            "capabilities": [],
            "prompt_topics": ["paper"],
            "needs_papers": False,
            "paper_author": "Xin Peng",
            "paper_identity_globally_unambiguous": True,
        })
        self.assertFalse(plan["needs_papers"])
        self.assertEqual(plan["_capabilities"], [])
        self.assertEqual(required_tools_for_plan(plan), ())

    def test_news_may_load_paper_boundary_without_running_paper_search(self):
        plan = parse_capability_plan({
            "capabilities": ["web_search"],
            "prompt_topics": ["web", "paper"],
            "needs_web_search": True,
            "needs_images": True,
            "needs_papers": False,
            "search_query": "今天 AI 新闻",
            "image_query": "今天 AI 新闻事件现场",
        })
        self.assertEqual(plan["_capabilities"], ["web_search"])
        self.assertEqual(required_tools_for_plan(plan), ("rich_search",))

    async def test_required_input_gate_receives_request_location_context(self):
        model = StructuredPlannerModel()
        result = await plan_required_clarification(
            model,
            "用我本轮的位置继续完成请求",
            location_context="浏览器位置已授权且新鲜，可作为本轮起点",
        )
        self.assertFalse(result["needs_clarification"])
        self.assertIn(
            "浏览器位置已授权且新鲜",
            model.messages[0]["content"],
        )

    async def test_weather_risk_is_decided_by_structured_semantics(self):
        model = StructuredPlannerModel({
            "actionable": True,
            "priority": "high",
        })
        risk = await classify_weather_risk(
            model,
            {"weather": "provider-specific condition", "temperature": 3},
            schedule={"title": "户外活动"},
        )
        self.assertEqual(risk, {"actionable": True, "priority": "high"})
        self.assertEqual(model.schema.__name__, "WeatherRiskDecision")

    async def test_capability_planner_never_receives_skill_switches(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "route_stops": [
                {"query": "海淀百旺公园"},
                {"query": "百望山森林公园"},
            ],
        })
        plan = await plan_capabilities(model, "规划这两个地点的路线")
        system_prompt = model.messages[0]["content"]
        self.assertNotIn("enabled", system_prompt)
        self.assertNotIn("disabled", system_prompt)
        self.assertNotIn("blocked_skill", CapabilityPlan.model_json_schema()["properties"])
        self.assertTrue(plan["needs_route"])

    def test_runtime_skill_policy_runs_after_planning(self):
        enabled_plan = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "route_stops": [
                    {"query": "海淀百旺公园"},
                    {"query": "百望山森林公园"},
                ],
            },
            disabled_skills={"vision"},
        )
        self.assertEqual(enabled_plan["blocked_skill"], "")
        self.assertEqual(
            required_tools_for_plan(enabled_plan),
            ("plan_route_between_places",),
        )

        route_without_calendar = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "_capabilities": [
                    "route",
                    "calendar_context",
                    "calendar_action",
                ],
                "optional_capabilities": [
                    "calendar_context",
                    "calendar_action",
                ],
            },
            disabled_skills={"calendar"},
        )
        self.assertEqual(route_without_calendar["blocked_skill"], "")
        self.assertFalse(route_without_calendar["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(route_without_calendar),
            ("plan_route_between_places",),
        )

        disabled_plan = apply_runtime_skill_policy(
            {
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "_capabilities": ["calendar_context", "calendar_action"],
            },
            disabled_skills={"calendar"},
        )
        self.assertEqual(disabled_plan["blocked_skill"], "calendar")
        self.assertEqual(required_tools_for_plan(disabled_plan), ())

        reused_route = apply_runtime_skill_policy(
            {
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "reuse_latest_route": True,
                "route_stops": [
                    {"query": "不应重新搜索的历史地点"},
                ],
                "_capabilities": [
                    "route",
                    "calendar_context",
                    "calendar_action",
                ],
            },
            disabled_skills=set(),
        )
        self.assertFalse(reused_route["needs_route"])
        self.assertEqual(reused_route["route_stops"], [])
        self.assertEqual(
            required_tools_for_plan(reused_route),
            ("propose_calendar_changes",),
        )

    async def test_capability_planner_preserves_every_ordered_route_stop(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "route_city": "北京",
            "route_stops": [
                {"query": "腾讯北京总部"},
                {"query": "锦江之星", "near_query": "北京301医院"},
                {"query": "王府井那个店"},
                {"query": "桔子酒店"},
            ],
        })
        plan = await plan_capabilities(
            model,
            "今晚从腾讯北京总部出发，先去301医院附近的锦江之星，再去王府井那个店，最后回桔子酒店",
        )
        self.assertEqual(plan["route_city"], "北京")
        self.assertEqual(
            [item["query"] for item in plan["route_stops"]],
            ["腾讯北京总部", "锦江之星", "王府井那个店", "桔子酒店"],
        )
        self.assertEqual(plan["route_stops"][1]["near_query"], "北京301医院")

    async def test_capability_plan_is_not_mutated_by_phrase_rules(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "needs_calendar_action": False,
            "route_stops": [
                {"query": "北京站"},
                {"query": "北京西站"},
            ],
        })
        plan = await plan_capabilities(
            model,
            "请规划北京站到北京西站的路线，并生成待确认的日程提案",
        )
        self.assertTrue(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places",),
        )

    async def test_route_planning_does_not_imply_calendar_side_effect(self):
        model = StructuredPlannerModel({
            "needs_route": True,
            "needs_calendar_action": False,
        })
        plan = await plan_capabilities(model, "请帮我规划明天的六站行程")
        self.assertFalse(plan["needs_calendar_action"])

    async def test_failed_structured_planner_does_not_guess_from_phrases(self):
        model = FailingStructuredPlannerModel()
        plan = await plan_capabilities(
            model,
            "请规划北京六个地点的路线，并生成待确认的日程提案",
        )
        self.assertEqual(model.calls, 1)
        self.assertFalse(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(required_tools_for_plan(plan), ())
        self.assertEqual(plan["_prompt_topics"], [])

    async def test_failed_structured_planner_has_no_keyword_fallback(self):
        model = FailingStructuredPlannerModel()
        plan = await plan_capabilities(
            model,
            "只要日程提案，不需要规划路线",
        )
        self.assertFalse(plan["needs_route"])
        self.assertFalse(plan["needs_calendar_action"])
        self.assertEqual(required_tools_for_plan(plan), ())

    async def test_failed_full_plan_uses_one_bounded_semantic_recovery(self):
        model = RecoveringStructuredPlannerModel()
        timings = {}
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "今天 AI 有什么新消息？",
            timeout_seconds=2,
            timings_ms=timings,
        )
        self.assertFalse(timed_out)
        self.assertEqual(model.calls, 2)
        self.assertTrue(timings["semantic_plan_recovered"])
        self.assertTrue(plan["strict_today_only"])
        self.assertEqual(plan["_prompt_topics"], ["web"])
        self.assertEqual(required_tools_for_plan(plan), ("rich_search",))

    def test_capability_plan_rejects_unknown_blocked_skill(self):
        plan = parse_capability_plan(json.dumps({
            "blocked_skill": "fake-business-rule",
            "needs_calendar_action": True,
        }))
        self.assertEqual(plan["blocked_skill"], "")
        self.assertEqual(required_tools_for_plan(plan), ("propose_calendar_changes",))

    async def test_capability_planner_timeout_keeps_main_semantic_routing_available(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "推荐北京三里屯附近的餐馆",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertFalse(any(plan[key] for key in plan if key.startswith("needs_")))

    async def test_capability_planner_timeout_never_uses_location_phrases(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "我现在在哪",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertEqual(required_tools_for_plan(plan), ())

    async def test_capability_planner_timeout_never_infers_nearby_category(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "这附近有什么好吃的？",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertEqual(required_tools_for_plan(plan), ())
        self.assertEqual(plan["nearby_query"], "")

    def test_chat_entry_never_branches_on_user_phrase_literals(self):
        """Keep natural-language intent in structured models, not source-code phrases."""
        chat_dir = Path(__file__).parents[1] / "chat"
        user_text_names = {"message", "user_message", "planning_message"}
        violations: list[str] = []

        def references_user_text(node: ast.AST) -> bool:
            return any(
                isinstance(item, ast.Name) and item.id in user_text_names
                for item in ast.walk(node)
            )

        def has_string_literal(node: ast.AST) -> bool:
            return any(
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and bool(item.value)
                for item in ast.walk(node)
            )

        def is_message_role_protocol(node: ast.AST) -> bool:
            values = {
                item.value
                for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            return bool(values) and values <= {
                "", "type", "human", "user", "ai", "assistant",
            }

        for filename in ("index.py", "_capability_plan.py"):
            source = (chat_dir / filename).read_text(encoding="utf-8")
            module = ast.parse(source)
            for condition in (
                item.test
                for item in ast.walk(module)
                if isinstance(item, (ast.If, ast.IfExp, ast.While))
            ):
                for comparison in (
                    item for item in ast.walk(condition)
                    if isinstance(item, ast.Compare)
                ):
                    operands = [comparison.left, *comparison.comparators]
                    if (
                        references_user_text(comparison)
                        and any(has_string_literal(operand) for operand in operands)
                        and not is_message_role_protocol(comparison)
                    ):
                        violations.append(
                            f"{filename}:{comparison.lineno}:"
                            f"{ast.get_source_segment(source, comparison)}"
                        )
                for call in (
                    item for item in ast.walk(condition)
                    if isinstance(item, ast.Call)
                ):
                    method_name = (
                        call.func.attr
                        if isinstance(call.func, ast.Attribute)
                        else call.func.id
                        if isinstance(call.func, ast.Name)
                        else ""
                    )
                    if (
                        method_name in {
                            "search", "match", "fullmatch",
                            "startswith", "endswith",
                        }
                        and references_user_text(call)
                        and has_string_literal(call)
                    ):
                        violations.append(
                            f"{filename}:{call.lineno}:"
                            f"{ast.get_source_segment(source, call)}"
                        )

        self.assertEqual(
            violations,
            [],
            "用户意图必须由 LangChain 结构化语义链决定，不能新增短语、正则或同义词分支",
        )

    async def test_location_guard_does_not_hijack_non_location_question(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "我现在在哪个步骤可以修改论文标题？",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertFalse(plan["needs_current_location"])
        self.assertFalse(plan["needs_nearby_places"])

    async def test_message_restore_keeps_rich_search_metadata(self):
        metadata = {"total": 1, "results": [{"title": "故宫", "url": "https://example.com"}], "media": []}
        messages = [
            {"type": "human", "content": "故宫历史", "id": "u1"},
            {"type": "tool", "content": json.dumps({"ui_action": "rich_search_results", "search_results": metadata})},
            {"type": "ai", "content": "## 故宫历史", "id": "a1"},
        ]
        langgraph_store = FakeStore()
        from agents._shared.data_version import namespace as data_namespace
        from agents._shared.data_version import scoped_conversation
        await langgraph_store.aput(
            data_namespace("message_meta", scoped_conversation("restore-rich")),
            "latest_extras",
            {
                "original_content": "## 故宫历史",
                "content": "## 故宫历史\n\n![太和殿](https://example.com/palace.jpg)",
                "follow_ups": ["太和殿是做什么的？"],
                "search_results": {**metadata, "media": [{"id": "media-1"}]},
            },
        )
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=langgraph_store,
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-rich", store=store))
        ai_message = next(item for item in response["messages"] if item["role"] == "ai")
        self.assertEqual(ai_message["searchResults"]["media"], [{"id": "media-1"}])
        self.assertIn("palace.jpg", ai_message["content"])
        self.assertEqual(ai_message["followUps"], ["太和殿是做什么的？"])
        self.assertNotIn("workspace_actions", response)

    async def test_message_restore_accepts_makers_proxy_without_optional_role(self):
        messages = [
            MakersCheckpointMessage(type="human", content="最近AI有什么新进展", id="u-role"),
            MakersCheckpointMessage(type="ai", content="这是恢复后的回答", id="a-role"),
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-role", store=store))
        self.assertEqual(
            [(item["role"], item["content"]) for item in response["messages"]],
            [("user", "最近AI有什么新进展"), ("ai", "这是恢复后的回答")],
        )

    async def test_message_restore_keeps_clarification_between_original_and_answer(self):
        clarification = {
            "id": "trip-date",
            "title": "还需要出发日期",
            "prompt": "请选择日期后继续。",
            "fields": [{"id": "date", "label": "出发日期", "type": "date", "required": True}],
        }
        messages = [
            {"type": "human", "content": "帮我安排旅行", "id": "u-trip"},
            {"type": "tool", "content": json.dumps({
                "ui_action": "clarification_action",
                "clarification": clarification,
            })},
            {"type": "ai", "content": "", "id": "a-question"},
            {"type": "human", "content": "补充信息：\\n- 出发日期：2026-08-01", "id": "u-date"},
            {"type": "ai", "content": "我会按这个日期安排。", "id": "a-plan"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-clarification", store=store))
        restored = response["messages"]
        self.assertEqual([item["role"] for item in restored], ["user", "ai", "user", "ai"])
        self.assertEqual(restored[0]["content"], "帮我安排旅行")
        self.assertEqual(restored[1]["clarification"], clarification)
        self.assertEqual(restored[2]["content"], "补充信息：\\n- 出发日期：2026-08-01")

    async def test_message_restore_hides_submitted_clarification_answer(self):
        clarification = {
            "id": "trip-date",
            "title": "还需要出发日期",
            "prompt": "请选择日期后继续。",
            "fields": [{"id": "date", "label": "出发日期", "type": "date", "required": True}],
        }
        messages = [
            {"type": "human", "content": "帮我安排旅行", "id": "u-trip"},
            {"type": "tool", "content": json.dumps({
                "ui_action": "clarification_action",
                "clarification": clarification,
            })},
            {"type": "ai", "content": "", "id": "a-question"},
            {
                "type": "human",
                "content": "补充必要信息：\\n出发日期：2026-08-01",
                "id": "u-date",
                "additional_kwargs": {
                    "floris_ui_hidden": True,
                    "floris_interaction": "clarification",
                    "clarification_id": "trip-date",
                },
            },
            {"type": "ai", "content": "我会按这个日期安排。", "id": "a-plan"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-silent-clarification", store=store))
        restored = response["messages"]
        self.assertEqual([item["role"] for item in restored], ["user", "ai", "ai"])
        self.assertEqual(restored[1]["clarification"], clarification)
        self.assertTrue(restored[1]["clarificationAnswered"])
        self.assertNotIn("补充必要信息", [item["content"] for item in restored])
        self.assertEqual(restored[2]["content"], "我会按这个日期安排。")

    async def test_message_restore_keeps_action_when_final_model_prose_is_empty(self):
        action = new_action(
            "map_recommendation", {"title": "故宫", "places": [PLACE]},
            requires_confirmation=False,
        )
        messages = [
            {"type": "human", "content": "故宫在哪里", "id": "u-map-empty"},
            {"type": "tool", "content": json.dumps({"ui_action": "map_action", "action": action})},
            {"type": "ai", "content": "", "id": "a-map-empty"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-map-empty", store=store))
        restored = next(item for item in response["messages"] if item["role"] == "ai")
        self.assertIn("点击", restored["content"])
        self.assertEqual(restored["workspaceActions"][0]["id"], action["id"])

    async def test_message_restore_coalesces_model_prose_and_action_fallback(self):
        action = new_action(
            "image_generate", {"prompt": "蓝围巾橘猫", "group_id": "cat-duplicate"},
            requires_confirmation=False,
        )
        action["status"] = "succeeded"
        action["result"] = {"ok": True, "image_url": "https://example.com/cat.png"}
        wire = json.dumps({"ui_action": "side_effect_action", "action": action})
        messages = [
            {"type": "human", "content": "画一只猫", "id": "u-image-duplicate"},
            {"type": "tool", "content": wire},
            {"type": "ai", "content": "图片已经生成，可以继续修改围巾颜色。", "id": "a-image-rich"},
            {"type": "tool", "content": wire},
            {"type": "ai", "content": action_fallback_content([action]), "id": "a-image-fallback"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-image-duplicate", store=store))
        restored = [item for item in response["messages"] if item["role"] == "ai"]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["content"], "图片已经生成，可以继续修改围巾颜色。")
        self.assertEqual([item["id"] for item in restored[0]["workspaceActions"]], [action["id"]])

    async def test_message_restore_rehydrates_image_versions_from_current_workspace(self):
        workspace = empty_workspace()
        first = new_action(
            "image_generate", {"prompt": "黄围巾", "group_id": "cat-group"},
            requires_confirmation=False,
        )
        second = new_action(
            "image_generate",
            {"prompt": "红围巾", "group_id": "cat-group", "parent_action_id": first["id"]},
            requires_confirmation=False,
        )
        for created_at, action, url in (
            (1, first, "https://example.com/yellow.png"),
            (2, second, "https://example.com/red.png"),
        ):
            action["created_at"] = created_at
            action["status"] = "succeeded"
            action["result"] = {"ok": True, "image_url": url}
            put_action(workspace, action)
        store_data = FakeStore()
        await save_workspace(store_data, USER_WORKSPACE_ID, workspace)
        checkpoint_action = {**first, "result": {**first["result"], "versions": image_versions(workspace, "cat-group")[:1]}}
        messages = [
            {"type": "human", "content": "画一只猫", "id": "u-image"},
            {"type": "tool", "content": json.dumps({"ui_action": "side_effect_action", "action": checkpoint_action})},
            {"type": "ai", "content": "图片已经生成", "id": "a-image"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=store_data,
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-image", store=store))
        action = next(item for item in response["messages"] if item["role"] == "ai")["workspaceActions"][0]
        self.assertEqual(
            [item["image_url"] for item in action["result"]["versions"]],
            ["https://example.com/yellow.png", "https://example.com/red.png"],
        )

    async def test_message_restore_hides_legacy_unanswered_failure_prompts(self):
        messages = [
            MakersCheckpointMessage(type="human", content="失败测试一", id="u-failed-1"),
            MakersCheckpointMessage(type="human", content="失败测试二", id="u-failed-2"),
            MakersCheckpointMessage(type="human", content="恢复测试", id="u-success"),
            MakersCheckpointMessage(type="ai", content="恢复成功", id="a-success"),
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-failed", store=store))
        self.assertEqual(
            [(item["role"], item["content"]) for item in response["messages"]],
            [("user", "恢复测试"), ("ai", "恢复成功")],
        )

    def test_system_prompt_formats_without_accidental_placeholders(self):
        rendered = SYSTEM_PROMPT.format(
            now="2026-07-15 12:00:00 UTC+08:00",
            response_language_instruction="使用简体中文。",
            capability_plan='{"needs_places": true}',
            calendar_context='[{"id":"cal-live"}]',
            reference_image_context="无",
            document_context="无",
        )
        self.assertIn("2026-07-15", rendered)

    def test_system_prompt_sections_are_named_complete_and_ordered(self):
        self.assertEqual(
            tuple(SYSTEM_PROMPT_SECTIONS),
            SYSTEM_PROMPT_SECTION_ORDER,
        )
        self.assertEqual(
            SYSTEM_PROMPT,
            "\n".join(SYSTEM_PROMPT_SECTIONS.values()),
        )
        self.assertEqual(len(SYSTEM_PROMPT_SECTIONS), 32)
        self.assertIn(
            "plan_route_between_places",
            SYSTEM_PROMPT_SECTIONS["route"],
        )
        self.assertIn(
            "propose_calendar_changes",
            SYSTEM_PROMPT_SECTIONS["calendar"],
        )

    def test_paper_chain_skips_only_redundant_argument_model_rounds(self):
        direct = direct_paper_tool_arguments({
            "needs_papers": True,
            "needs_web_search": False,
            "paper_topic": "retrieval augmented generation",
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_year_from": 2025,
            "paper_year_to": 2026,
            "paper_limit": 6,
        })
        self.assertEqual(
            direct["search_arxiv"]["topic"],
            "retrieval augmented generation",
        )
        self.assertEqual(direct["search_arxiv"]["limit"], 6)
        self.assertEqual(direct["search_arxiv"]["author"], "Xin Peng")
        self.assertEqual(direct["search_arxiv"]["institution"], "Fudan University")
        self.assertEqual(direct["search_arxiv"]["year_from"], 2025)
        self.assertEqual(direct["search_arxiv"]["year_to"], 2026)
        self.assertEqual(
            direct_paper_tool_arguments({
                "needs_papers": True,
                "needs_web_search": True,
                "paper_topic": "retrieval augmented generation",
            }),
            {},
        )

    def test_structured_actions_keep_public_answer_streaming_except_images(self):
        self.assertFalse(should_buffer_public_answer({"needs_route": True}))
        self.assertFalse(should_buffer_public_answer({
            "needs_route": False,
            "needs_calendar_action": True,
        }))
        self.assertTrue(should_buffer_public_answer({
            "needs_image_generation": True,
        }))
        self.assertFalse(should_buffer_public_answer({
            "needs_route": False,
            "needs_calendar_action": False,
            "needs_image_generation": False,
        }))

    def test_dynamic_prompt_injects_only_the_current_skill_policy(self):
        common = {
            "now": "2026-07-26 12:00:00 UTC+08:00",
            "response_language_instruction": "使用简体中文。",
            "capability_plan": {"needs_route": True},
            "calendar_context": '[{"id":"should-not-leak"}]',
            "reference_image_context": "无",
            "document_context": "无",
            "current_location_context": "不可用",
            "current_route_context": "无",
            "memory_context": "",
        }
        route_prompt = dynamic_system_prompt(
            selected_tools={"plan_route_between_places"},
            **common,
        )
        self.assertIn("plan_route_between_places", route_prompt)
        self.assertNotIn("rich_search 始终是可用能力", route_prompt)
        self.assertNotIn("用户询问某个已知地点、当前位置或日程地点附近", route_prompt)
        self.assertNotIn("should-not-leak", route_prompt)
        self.assertLess(len(route_prompt), len(SYSTEM_PROMPT) * 0.7)

        public_route_prompt = dynamic_system_prompt(
            selected_tools={"plan_route_between_places"},
            public_answer=True,
            **common,
        )
        self.assertIn(
            "transit.walking_distance_meters 是全程所有接驳步行的合计",
            public_route_prompt,
        )
        self.assertIn("线路运营时段", public_route_prompt)
        self.assertIn("一律不得用模型常识补写", public_route_prompt)

        calendar_prompt = dynamic_system_prompt(
            selected_tools={"propose_calendar_changes"},
            **common,
        )
        self.assertIn("propose_calendar_changes", calendar_prompt)
        self.assertIn("should-not-leak", calendar_prompt)
        self.assertNotIn("rich_search 始终是可用能力", calendar_prompt)

        plain_prompt = dynamic_system_prompt(
            selected_tools=set(),
            **common,
        )
        self.assertIn("浏览器当前位置状态：不可用", plain_prompt)
        self.assertIn("禁止声称已授权、已定位或已搜索当前位置附近", plain_prompt)

    def test_successful_capability_plan_hides_unrelated_tool_schemas(self):
        tools = [
            SimpleNamespace(name="rich_search"),
            SimpleNamespace(name="plan_route_between_places"),
            SimpleNamespace(name="propose_calendar_changes"),
            SimpleNamespace(name="ask_user_clarification"),
        ]
        selected = tools_for_capability_stage(
            tools, ("plan_route_between_places",),
        )
        self.assertEqual(
            [tool.name for tool in selected],
            ["plan_route_between_places", "ask_user_clarification"],
        )
        self.assertEqual(
            [tool.name for tool in tools_for_capability_stage(tools, ())],
            ["ask_user_clarification"],
        )
        self.assertEqual(
            tools_for_capability_stage(
                tools, (), planner_timed_out=True,
            ),
            tools,
        )

    def test_provider_errors_are_safe_and_actionable(self):
        raw = "Error code: 400 - Model ID must include provider prefix; type=invalid_request"
        message = public_error(raw)
        self.assertIn("模型配置", message)
        self.assertNotIn("provider prefix", message)
        self.assertNotIn("invalid_request", message)

    def test_run_diagnostics_keep_only_safe_failure_fields(self):
        diagnostics = safe_error_diagnostics(
            "Error code: 400 - invalid_request; request_id=req-abc123; api_key=secret",
            stage="graph_stream",
        )
        self.assertEqual(diagnostics["stage"], "graph_stream")
        self.assertEqual(diagnostics["status_code"], 400)
        self.assertEqual(diagnostics["request_id"], "req-abc123")
        self.assertNotIn("secret", json.dumps(diagnostics))

    def test_capability_plan_parser_is_bounded_to_known_booleans(self):
        plan = parse_capability_plan('```json\n{"needs_places": true, "needs_map_action": 1, "strict_today_only": true, "search_query": "北京旅行", "image_query": "故宫建筑", "unknown": true}\n```')
        self.assertTrue(plan["needs_places"])
        self.assertTrue(plan["needs_map_action"])
        self.assertTrue(plan["strict_today_only"])
        self.assertEqual(plan["search_query"], "北京旅行")
        self.assertEqual(plan["image_query"], "故宫建筑")
        self.assertNotIn("unknown", plan)

    def test_semantic_search_plan_requires_one_rich_search_first_step(self):
        self.assertEqual(required_tool_for_plan({"needs_web_search": True}), "rich_search")
        self.assertEqual(required_tool_for_plan({"needs_web_search": False}), "")

    def test_missing_critical_information_requires_only_structured_clarification(self):
        plan = {
            "needs_clarification": True,
            "needs_web_search": True,
            "needs_calendar_action": True,
        }
        self.assertEqual(required_tools_for_plan(plan), ("ask_user_clarification",))

    def test_optional_or_undecided_preferences_produce_scenarios_not_questionnaires(self):
        self.assertIn("阻断所有安全且有用的回答", SYSTEM_PROMPT)
        self.assertIn("2–3 套可独立采用的方案", SYSTEM_PROMPT)
        self.assertIn("没决定、都可以、先看看", SYSTEM_PROMPT)
        self.assertIn("用户不需要再点发送", SYSTEM_PROMPT)
        self.assertNotIn("不同选择会明显改变后续结果时，应先用 ask_user_clarification", SYSTEM_PROMPT)

    def test_every_qa_scene_keeps_full_history_clarification_available(self):
        source = (Path(__file__).parents[1] / "chat" / "index.py").read_text(encoding="utf-8")
        graph_source = (Path(__file__).parents[1] / "chat" / "_graph.py").read_text(encoding="utf-8")
        self.assertNotIn("if not clarification_tool_available", source)
        self.assertIn('required_name and "ask_user_clarification" in allowed_tool_names', graph_source)
        self.assertIn("required_or_question_tools", graph_source)
        self.assertIn("你在此前回答里自行建议、假设或补出的时间", SYSTEM_PROMPT)

    def test_semantic_web_search_makes_media_available_without_keyword_rules(self):
        self.assertTrue(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": False,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_images": True,
        }, 0))
        self.assertTrue(media_enabled_for_plan({
            "needs_web_search": False,
            "needs_images": False,
        }, 2, planner_timed_out=True))

    def test_searchpro_html_passage_exposes_provider_article_image(self):
        pages = _parse_pages({"Response": {"Pages": [{
            "url": "https://news.example/item",
            "title": "大会新闻",
            "passage": "<p>正文</p><img src='http://qqpublic.qpic.cn/news.jpg' width='700'>",
        }]}}, 8)
        self.assertEqual(pages[0]["image"], "https://qqpublic.qpic.cn/news.jpg")

    def test_temporal_policy_is_derived_after_capability_planning(self):
        source = (Path(__file__).parents[1] / "chat" / "index.py").read_text(encoding="utf-8")
        planned = source.index("capability_plan, planner_timed_out = await plan_capabilities_bounded")
        strict_date = source.index('explicit_today = bool(capability_plan.get("strict_today_only"))')
        self.assertLess(planned, strict_date)

    def test_semantic_plan_builds_short_native_action_chain(self):
        plan = {
            "needs_web_search": True,
            "needs_places": True,
            "needs_map_action": True,
            "needs_calendar_action": True,
        }
        self.assertEqual(
            required_tools_for_plan(plan),
            ("rich_search", "recommend_places_on_map", "propose_calendar_changes"),
        )
        allowed = {"rich_search", "recommend_places_on_map", "propose_calendar_changes"}
        self.assertEqual(next_required_tool(required_tools_for_plan(plan), [], allowed), "rich_search")
        self.assertEqual(
            next_required_tool(required_tools_for_plan(plan), ["rich_search"], allowed),
            "recommend_places_on_map",
        )
        self.assertEqual(
            next_required_tool(required_tools_for_plan(plan), ["rich_search", "recommend_places_on_map"], allowed),
            "propose_calendar_changes",
        )

    def test_calendar_place_plan_looks_up_place_before_proposal(self):
        self.assertEqual(
            required_tools_for_plan({"needs_places": True, "needs_calendar_action": True}),
            ("search_places", "propose_calendar_changes"),
        )

    def test_paper_plan_uses_arxiv_without_requiring_web_search(self):
        self.assertEqual(
            required_tools_for_plan({"needs_papers": True}),
            ("search_arxiv",),
        )
        self.assertEqual(
            required_tools_for_plan({"needs_papers": True, "needs_web_search": True}),
            ("rich_search", "search_arxiv"),
        )

    def test_persistent_active_workflow_has_its_own_capability_route(self):
        self.assertEqual(
            required_tools_for_plan({"needs_workflow_action": True}),
            ("propose_workflow",),
        )

    def test_route_plan_uses_verified_route_tool_without_web_estimate(self):
        self.assertEqual(
            required_tools_for_plan({"needs_route": True}),
            ("plan_route_between_places",),
        )
        self.assertEqual(
            required_tools_for_plan({
                "needs_route": True,
                "needs_calendar_action": True,
            }),
            ("plan_route_between_places", "propose_calendar_changes"),
        )
        self.assertIn("一个/多个依次停靠点", SYSTEM_PROMPT)
        self.assertIn("ordered_stops", SYSTEM_PROMPT)
        self.assertIn("不要再问用户“是否需要写入日程”", SYSTEM_PROMPT)
        self.assertIn("source_route_plan_id", SYSTEM_PROMPT)

    def test_current_location_plan_uses_tencent_reverse_geocode_tool(self):
        self.assertEqual(
            required_tools_for_plan({"needs_current_location": True}),
            ("get_current_location",),
        )

    def test_nearby_plan_uses_one_native_location_composite(self):
        self.assertEqual(
            required_tools_for_plan({
                "needs_nearby_places": True,
                "needs_places": True,
                "needs_map_action": True,
            }),
            ("recommend_nearby_places_on_map",),
        )

    def test_empty_generation_is_terminal_unless_a_card_or_action_was_emitted(self):
        self.assertIn("未返回有效回答", empty_generation_error(
            "", has_actions=False, clarification_emitted=False, run_error="", cancelled=False,
        ))
        self.assertEqual(empty_generation_error(
            "", has_actions=False, clarification_emitted=True, run_error="", cancelled=False,
        ), "")
        self.assertEqual(empty_generation_error(
            "", has_actions=True, clarification_emitted=False, run_error="", cancelled=False,
        ), "")

    def test_manual_graph_fallback_is_recovered_from_final_checkpoint(self):
        snapshot = SimpleNamespace(values={"messages": [
            SimpleNamespace(type="human", content="附近有早餐店吗"),
            SimpleNamespace(type="ai", content="地点服务没有核实到结果，请扩大范围。"),
        ]})
        self.assertEqual(
            checkpoint_final_answer(snapshot),
            "地点服务没有核实到结果，请扩大范围。",
        )
        no_current_answer = SimpleNamespace(values={"messages": [
            SimpleNamespace(type="human", content="上一题"),
            SimpleNamespace(type="ai", content="上一题回答"),
            SimpleNamespace(type="human", content="这一题"),
        ]})
        self.assertEqual(checkpoint_final_answer(no_current_answer), "")

    def test_follow_up_parser_accepts_only_three_unique_questions(self):
        self.assertEqual(
            parse_followups('```json\n["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？", "多余问题？"]\n```'),
            ["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？"],
        )
        self.assertEqual(parse_followups("不是 JSON"), [])

    def test_follow_up_generation_uses_semantic_result_state(self):
        self.assertTrue(should_generate_followups({
            "needs_nearby_places": True,
            "needs_followups": False,
        }))
        self.assertTrue(should_generate_followups({
            "needs_followups": True,
        }))
        self.assertFalse(should_generate_followups({
            "needs_clarification": True,
            "needs_nearby_places": True,
        }))
        self.assertFalse(should_generate_followups(
            {"needs_nearby_places": True},
            blocked_skill="maps",
        ))
        self.assertFalse(should_generate_followups({}))

    async def test_follow_up_generator_uses_the_selected_output_language(self):
        model = SimpleNamespace(ainvoke=AsyncMock(
            return_value=SimpleNamespace(content='["What changed most?"]')
        ))
        result = await generate_followups(
            model,
            "What is new in artificial intelligence this week?",
            plan_context='{"needs_web_search": true}',
            response_language="en",
        )
        self.assertEqual(result, ["What changed most?"])
        system_prompt = model.ainvoke.await_args.args[0][0]["content"]
        self.assertIn("Write every question in clear, concise English.", system_prompt)


    def test_rich_search_handoff_uses_standard_markdown(self):
        metadata = {
            "results": [{"source": "wsa", "title": "故宫", "snippet": "明清宫殿", "url": "https://example.com/palace"}],
            "media": [{"caption": "故宫太和殿建筑", "url": "https://cdn.example.com/palace.jpg"}],
        }
        evidence = evidence_for_model(metadata)
        self.assertIn("![故宫太和殿建筑](https://cdn.example.com/palace.jpg)", evidence)
        self.assertNotIn("[[image:", evidence)
        self.assertNotIn("[[card:", evidence)

    def test_planner_preferred_media_is_required_when_reviewed(self):
        metadata = {
            "results": [],
            "media_pending": False,
            "media": [{
                "caption": "发布会现场",
                "url": "https://cdn.example.com/launch.jpg",
            }],
        }
        evidence = evidence_for_model(metadata, require_relevant_image=True)
        self.assertIn("必须至少选择一张最相关图片", evidence)

    def test_empty_paper_result_cannot_override_successful_web_search(self):
        web = ToolMessage(
            name="rich_search",
            tool_call_id="web-1",
            content=json.dumps({
                "ui_action": "rich_search_results",
                "search_results": {
                    "results": [{
                        "title": "AI 新闻",
                        "url": "https://news.example.com/ai",
                    }],
                },
            }, ensure_ascii=False),
        )
        paper = ToolMessage(
            name="search_arxiv",
            tool_call_id="paper-1",
            content=json.dumps({
                "ui_action": "paper_results",
                "papers": [],
            }, ensure_ascii=False),
        )
        answer = tool_result_fallback([web, paper])
        self.assertIn("[AI 新闻](https://news.example.com/ai)", answer)
        self.assertNotIn("没有核实到符合作者", answer)

    async def test_workspace_round_trip_increments_revision(self):
        store = FakeStore()
        state = empty_workspace()
        saved = await save_workspace(store, "c1", state)
        restored = await load_workspace(store, "c1")
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(restored["revision"], 1)

    def test_schedule_collector_emits_deterministic_opportunities(self):
        now = 1_800_000_000
        schedules = [
            {"id": "a", "title": "会议", "start_time": now + 600, "duration_minutes": 60, "location": "国贸"},
            {"id": "b", "title": "晚餐", "start_time": now + 1800, "duration_minutes": 60, "location": "望京"},
        ]
        signals = collect_schedule_signals(schedules, now)
        self.assertEqual([item["type"] for item in signals].count("schedule_upcoming"), 2)
        self.assertEqual([item["type"] for item in signals].count("schedule_conflict"), 1)
        self.assertEqual(len({item["dedup_key"] for item in signals}), len(signals))

    def test_schedule_collector_detects_conflict_with_an_ongoing_event(self):
        now = 1_800_000_000
        schedules = [
            {"id": "ongoing", "title": "ongoing", "start_time": now - 600, "duration_minutes": 30},
            {"id": "next", "title": "next", "start_time": now + 300, "duration_minutes": 30},
        ]
        signals = collect_schedule_signals(schedules, now)
        self.assertEqual([item["type"] for item in signals].count("schedule_conflict"), 1)
        self.assertEqual([item["type"] for item in signals].count("schedule_upcoming"), 1)

    def test_proactive_policy_deduplicates_and_respects_daily_limit(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 1,
            "quiet_hours": {"enabled": False},
        })
        signals = [
            {"type": "schedule_upcoming", "dedup_key": "one", "priority": "normal", "title": "一", "detail": "一", "action": "一", "occurred_at": now},
            {"type": "schedule_upcoming", "dedup_key": "two", "priority": "normal", "title": "二", "detail": "二", "action": "二", "occurred_at": now},
        ]
        first = process_schedule_signals(state, signals, now)
        second = process_schedule_signals(state, signals, now)
        self.assertEqual(first["notifications_created"], 1)
        self.assertEqual(len(state["notifications"]), 1)
        self.assertEqual(second["notifications_created"], 0)
        self.assertTrue(any(run["reason"] == "daily_limit_reached" for run in state["runs"].values()))

    def test_high_priority_conflict_bypasses_normal_daily_quota(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 0,
            "quiet_hours": {"enabled": False},
        })
        stats = process_schedule_signals(state, [{
            "type": "schedule_conflict",
            "dedup_key": "conflict:urgent",
            "priority": "high",
            "title": "conflict",
            "detail": "overlap",
            "action": "resolve",
            "occurred_at": now,
        }], now)
        self.assertEqual(stats["notifications_created"], 1)

    def test_proactive_fallback_mottos_are_sanitized_and_bounded(self):
        state = empty_proactive_state()
        update_preferences(state, {
            "fallback_mottos": [
                "  星光会找到夜路。  ", "", "星光会找到夜路。",
                "二", "三", "四", "五", "六",
            ],
        })
        self.assertEqual(
            state["preferences"]["fallback_mottos"],
            ["星光会找到夜路。", "二", "三", "四", "五", "六"],
        )

    def test_observe_only_persists_event_and_run_without_notification(self):
        state = empty_proactive_state()
        update_preferences(state, {"autonomy_mode": "observe", "quiet_hours": {"enabled": False}})
        signal = {
            "type": "schedule_upcoming", "source": "schedule_collector", "dedup_key": "observe:test",
            "priority": "normal", "title": "即将开始", "detail": "只记录不提醒", "action": "", "occurred_at": 100,
        }
        stats = process_schedule_signals(state, [signal], 100)
        self.assertEqual(stats["events_created"], 1)
        self.assertEqual(stats["notifications_created"], 0)
        self.assertEqual(next(iter(state["runs"].values()))["reason"], "observe_only")

    def test_proactive_window_queues_by_fcfs_without_replacement(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 50,
            "window_limit": 4,
            "quiet_hours": {"enabled": False},
        })
        for index in range(5):
            stats = process_schedule_signals(state, [{
                "type": "schedule_upcoming",
                "dedup_key": f"operation:{index}",
                "title": f"操作提醒{index}",
                "detail": "来自用户操作",
                "action": "继续处理",
                "occurred_at": now + index,
            }], now + index)
        public = public_proactive_state(state, now + 10)
        self.assertEqual(len(public["notifications"]), 4)
        self.assertEqual(stats["window_replaced"], 0)
        self.assertEqual(stats["window_queued"], 1)
        self.assertEqual(
            [item["title"] for item in public["notifications"]],
            ["操作提醒0", "操作提醒1", "操作提醒2", "操作提醒3"],
        )

    def test_memory_refresh_queues_behind_existing_fcfs_window(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 50,
            "window_limit": 4,
            "quiet_hours": {"enabled": False},
        })
        operation_signals = [{
            "type": "schedule_upcoming",
            "dedup_key": f"operation:{index}",
            "title": f"操作{index}",
            "detail": "操作提醒",
            "action": "处理",
            "occurred_at": now,
        } for index in range(4)]
        process_schedule_signals(state, operation_signals, now)
        for index in range(5):
            stats = process_schedule_signals(state, [{
                "type": "memory_context_reminder",
                "source": "memory_window",
                "window_policy": "memory_refresh",
                "dedup_key": f"memory:{index}",
                "title": f"记忆{index}",
                "detail": "记忆推导",
                "action": "继续",
                "occurred_at": now + index + 1,
            }], now + index + 1)
        public = public_proactive_state(state, now + 20)
        self.assertEqual(len(public["notifications"]), 4)
        self.assertTrue(all(item["window_origin"] == "operation" for item in public["notifications"]))
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(stats["window_queued"], 1)
        self.assertEqual(stats["skipped"], 0)

    def test_read_notification_leaves_the_display_window(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {"quiet_hours": {"enabled": False}})
        process_schedule_signals(state, [{
            "type": "schedule_upcoming",
            "dedup_key": "read-me",
            "title": "待读提醒",
            "detail": "测试",
            "action": "测试",
            "occurred_at": now,
        }], now)
        notification_id = public_proactive_state(state, now)["notifications"][0]["id"]
        mutate_notification(state, notification_id, "mark_read", now + 1)
        self.assertEqual(public_proactive_state(state, now + 1)["notifications"], [])

    async def test_memory_reminder_requires_safe_memory_and_returns_one_bounded_signal(self):
        model = AsyncMock()
        model.ainvoke.return_value = SimpleNamespace(content=json.dumps({
            "should_remind": True,
            "title": "带上雨具",
            "detail": "你常在下班后散步，海淀今天有雷阵雨，出门记得带伞。",
            "action": "需要我结合今天的日程看看什么时候出门更合适吗？",
            "priority": "normal",
        }, ensure_ascii=False))
        intelligence = empty_intelligence_state()
        self.assertIsNone(await infer_memory_reminder(
            model, intelligence, location_context={}, existing_reminders=[], now=1_800_000_000,
        ))
        apply_automatic_memory_candidates(
            intelligence,
            [{"key": "habit.walk", "value": "经常下班后散步", "confidence": 0.9, "ttl_days": 90}],
            now=1_800_000_000,
        )
        signal = await infer_memory_reminder(
            model,
            intelligence,
            location_context={"district": "海淀区", "weather": "雷阵雨", "expires_at": 1_900_000_000},
            existing_reminders=[],
            now=1_800_000_000,
        )
        self.assertEqual(signal["window_policy"], "memory_refresh")
        self.assertEqual(signal["title"], "带上雨具")
        self.assertEqual(signal["evidence"], {"basis": "safe_memory", "location_used": True})

    async def test_scheduled_tick_runs_without_chat_and_persists_inbox(self):
        store = FakeStore()
        now = 1_800_000_000
        workspace = empty_workspace()
        workspace["schedules"]["next"] = {
            "id": "next", "title": "参观故宫", "start_time": now + 3600,
            "duration_minutes": 120, "location": "故宫", "done": False,
        }
        await save_workspace(store, "local-user", workspace)
        state, stats = await run_proactive_tick(store, now)
        repeated, repeated_stats = await run_proactive_tick(store, now + 60)
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(repeated_stats["notifications_created"], 0)
        public = public_proactive_state(repeated, now)
        self.assertEqual(public["notifications"][0]["title"], "即将开始")
        self.assertEqual(public["checkpoints"]["schedule_collector"]["schedule_count"], 1)

    async def test_notification_controls_and_preferences_are_persistent(self):
        store = FakeStore()
        state = empty_proactive_state()
        state["notifications"]["ntf-1"] = {
            "id": "ntf-1", "status": "unread", "priority": "normal",
            "created_at": 100, "updated_at": 100, "version": 1,
        }
        update_preferences(state, {"enabled": False, "daily_limit": 2})
        mutate_notification(state, "ntf-1", "snooze", 100, 500)
        await save_proactive_state(store, state)
        restored = await load_proactive_state(store)
        self.assertTrue(restored["preferences"]["enabled"])
        self.assertEqual(restored["preferences"]["daily_limit"], 2)
        self.assertEqual(restored["notifications"]["ntf-1"]["status"], "snoozed")

    def test_workspace_signals_are_persistent_and_deduplicated(self):
        state = empty_proactive_state()
        first, created = ingest_workspace_signal(
            state, signal_type="file_uploaded", dedup_key="blob-1", payload={"filename": "paper.pdf"}, now=100,
        )
        repeated, created_again = ingest_workspace_signal(
            state, signal_type="file_uploaded", dedup_key="blob-1", payload={"filename": "paper.pdf"}, now=101,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], repeated["id"])
        self.assertEqual(len(state["runs"]), 1)

        route, route_created = ingest_workspace_signal(
            state, signal_type="route_changed", dedup_key="route-1", payload={"source": "map"}, now=102,
        )
        self.assertTrue(route_created)
        self.assertEqual(route["type"], "route_changed")

        location, location_created = ingest_workspace_signal(
            state,
            signal_type="browser_location_weather",
            dedup_key="2026-07-23:39.90:116.40",
            payload={"source": "browser_permission", "precision": "city"},
            now=103,
        )
        self.assertTrue(location_created)
        self.assertEqual(location["type"], "browser_location_weather")
        self.assertNotIn("latitude", location["payload"])
        self.assertNotIn("longitude", location["payload"])

    def test_workflow_requires_confirmation_and_emits_due_steps_once(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="出发准备",
            reason="按阶段提醒",
            steps=[
                {"offset_minutes": 0, "title": "检查证件", "body": "确认身份证", "action_prompt": "帮我列清单"},
                {"offset_minutes": 60, "title": "准备出门", "body": "检查路线"},
            ],
            now=100,
        )
        self.assertEqual(workflow["status"], "awaiting_confirmation")
        self.assertEqual(collect_workflow_signals(state, 100), [])
        accepted = decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        self.assertEqual(accepted["status"], "active")
        due = collect_workflow_signals(state, 100)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["source"], "workflow_scheduler")
        self.assertEqual(collect_workflow_signals(state, 100), [])
        decide_workflow_step(state, workflow["id"], "step_1", "complete", 200)
        later = collect_workflow_signals(state, 3700)
        self.assertEqual(len(later), 1)
        self.assertEqual(state["workflows"][workflow["id"]]["status"], "active")
        decide_workflow_step(state, workflow["id"], "step_2", "complete", 3800)
        self.assertEqual(state["workflows"][workflow["id"]]["status"], "completed")

    def test_pending_workflow_title_is_idempotent_across_model_variations(self):
        state = empty_proactive_state()
        first = propose_workflow(
            state,
            title="TEST-WORKFLOW",
            reason="第一次模型表述",
            steps=[{"offset_minutes": 0, "title": "核对测试", "body": "检查状态"}],
            now=100,
        )
        repeated = propose_workflow(
            state,
            title="  test-workflow  ",
            reason="第二次模型换了一种说法",
            steps=[{"offset_minutes": 0, "title": "执行测试", "body": "核对结果并报告"}],
            now=101,
        )
        self.assertEqual(repeated["id"], first["id"])
        self.assertEqual(repeated["reason"], "第一次模型表述")
        self.assertEqual(len(state["workflows"]), 1)

    def test_workflow_failure_emits_compensation_and_blocks_dependents_until_resolved(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="发布准备",
            reason="失败时需要回退",
            steps=[
                {
                    "offset_minutes": 0,
                    "title": "更新配置",
                    "body": "应用新配置",
                    "compensation": {
                        "title": "恢复旧配置",
                        "body": "将配置恢复到上一个已知版本",
                        "action_prompt": "请给我恢复步骤",
                    },
                },
                {"offset_minutes": 0, "title": "验证结果", "depends_on": ["step_1"]},
            ],
            now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        self.assertEqual(len(collect_workflow_signals(state, 100)), 1)
        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        compensation = collect_workflow_signals(state, 110)
        self.assertEqual(len(compensation), 1)
        self.assertEqual(compensation[0]["type"], "workflow_compensation_due")
        self.assertEqual(collect_workflow_signals(state, 110), [])
        decide_workflow_step(state, workflow["id"], "step_1", "compensate", 120)
        due = collect_workflow_signals(state, 120)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["title"], "验证结果")

    def test_failed_workflow_step_can_retry_without_duplicate_attempt_signal(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state, title="重试流程", reason="测试", steps=[{"offset_minutes": 0, "title": "执行"}], now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        collect_workflow_signals(state, 100)
        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        self.assertEqual(len(collect_workflow_signals(state, 110)), 1)
        decide_workflow_step(state, workflow["id"], "step_1", "retry", 120)
        retried = collect_workflow_signals(state, 120)
        self.assertEqual(len(retried), 1)
        self.assertIn(":1:", retried[0]["dedup_key"].replace("workflow_step_due", ""))

    def test_workflow_step_transition_retires_stale_notification(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="补偿通知清理",
            reason="测试完成后不再主动展示旧提醒",
            steps=[{
                "offset_minutes": 0,
                "title": "核对",
                "compensation": {"title": "恢复", "body": "恢复测试状态"},
            }],
            now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        due = collect_workflow_signals(state, 100)
        process_schedule_signals(state, due, 100)
        self.assertEqual(len(public_proactive_state(state)["notifications"]), 1)

        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        self.assertEqual(public_proactive_state(state)["notifications"], [])
        compensation = collect_workflow_signals(state, 110)
        process_schedule_signals(state, compensation, 110)
        self.assertEqual(public_proactive_state(state)["notifications"][0]["title"], "恢复")

        decide_workflow_step(state, workflow["id"], "step_1", "compensate", 120)
        self.assertEqual(public_proactive_state(state)["notifications"], [])

    def test_memory_requires_confirmation_and_is_injected_only_after_confirmation(self):
        state = empty_intelligence_state()
        proposal = propose_memory(state, "travel.seat", "靠窗", "用户明确要求记住")
        self.assertEqual(confirmed_memory_context(state), "")
        _, memory = confirm_memory(state, proposal["id"], proposal["version"])
        self.assertIn("travel.seat", confirmed_memory_context(state))
        self.assertEqual(memory["version"], 1)

    def test_memory_update_keeps_history_and_can_rollback(self):
        state = empty_intelligence_state()
        first = propose_memory(state, "travel.seat", "靠窗", "首次设置")
        _, memory = confirm_memory(state, first["id"], first["version"])
        second = propose_memory(state, "travel.seat", "过道", "用户修改")
        _, updated = confirm_memory(state, second["id"], second["version"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["history"][0]["value"], "靠窗")
        rolled_back = rollback_memory(state, memory["id"], 1)
        self.assertEqual(rolled_back["value"], "靠窗")
        self.assertEqual(rolled_back["version"], 3)

    def test_sensitive_memory_is_not_auto_injected(self):
        state = empty_intelligence_state()
        proposal = propose_memory(state, "identity.secret", "敏感内容", "用户要求保存", sensitivity="sensitive")
        confirm_memory(state, proposal["id"], proposal["version"])
        self.assertNotIn("敏感内容", confirmed_memory_context(state))

    def test_automatic_memory_filters_private_data_and_is_not_exposed(self):
        state = empty_intelligence_state()
        changed = apply_automatic_memory_candidates(state, [
            {"key": "preference.answer_style", "value": "喜欢先给结论", "confidence": 0.95, "ttl_days": 180},
            {"key": "contact.phone", "value": "13800138000", "confidence": 1, "ttl_days": 365},
            {"key": "preference.uncertain", "value": "可能喜欢咖啡", "confidence": 0.4, "ttl_days": 180},
        ], now=1_800_000_000)
        self.assertEqual(changed, 1)
        self.assertIn("喜欢先给结论", confirmed_memory_context(state))
        public = public_intelligence_state(state)
        self.assertEqual(public["memory_count"], 1)
        self.assertEqual(public["memories"], [])
        memory = next(iter(state["memories"].values()))
        memory["expires_at"] = 1_799_999_999
        self.assertEqual(prune_automatic_memories(state, 1_800_000_000), 1)

    def test_feedback_creates_confirmable_rule_instead_of_silent_policy_change(self):
        state = empty_intelligence_state()
        for index in range(3):
            record_feedback(
                state, target_type="notification", target_id=f"n{index}", outcome="dismissed",
                metadata={"notification_type": "schedule_upcoming"},
            )
        rules = list(state["rule_proposals"].values())
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["status"], "pending")

    def test_usage_budget_summary_is_date_bounded(self):
        state = empty_intelligence_state()
        with patch("agents._shared.intelligence.time.time", return_value=1_800_000_000):
            record_usage(state, 10, 5, 15, "chat")
        summary = usage_summary(state, 1_800_000_000)
        self.assertEqual(summary["daily_tokens"], 15)
        self.assertEqual(summary["monthly_tokens"], 15)

    async def test_user_assets_are_shared_across_conversations(self):
        store = FakeStore()
        workspace = empty_workspace()
        event = apply_calendar_changes(workspace, [{
            "operation": "create",
            "event": {"title": "参观故宫", "start_time": 100, "place": PLACE},
        }])[0]
        await save_workspace(store, "local-user", workspace)

        from_old_conversation = await load_user_workspace(store, "conversation-old")
        from_new_conversation = await load_user_workspace(store, "conversation-new")

        self.assertIn(event["id"], from_old_conversation["schedules"])
        self.assertIn(event["id"], from_new_conversation["schedules"])

    async def test_calendar_change_immediately_refreshes_proactive_notifications(self):
        store = FakeStore()
        start = int(time.time()) + 3600
        response = await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{
                "operation": "create",
                "event": {"title": "即将参观故宫", "start_time": start, "duration_minutes": 60, "place": PLACE},
            }],
        }))
        self.assertEqual(len(response["schedules"]), 1)
        proactive = public_proactive_state(await load_proactive_state(store))
        self.assertTrue(any(item["type"] == "schedule_upcoming" for item in proactive["notifications"]))

    async def test_legacy_conversation_workspace_is_not_inherited(self):
        store = FakeStore()
        legacy = empty_workspace()
        event = apply_calendar_changes(legacy, [{
            "operation": "create",
            "event": {"title": "旧数据", "start_time": 100, "place": PLACE},
        }])[0]
        await save_workspace(store, "conversation-old", legacy)
        current = await load_user_workspace(store, "conversation-old", "new-user")
        self.assertNotIn(event["id"], current["schedules"])

    def test_schedule_location_must_be_verified(self):
        with self.assertRaises(ValueError):
            normalize_schedule({"title": "参观", "start_time": 1, "place": {"name": "幻觉地点"}})
        event = normalize_schedule({"title": "参观", "start_time": 1, "place": PLACE})
        self.assertEqual(event["extra"]["place"]["place_id"], "poi-1")

    def test_calendar_create_update_delete(self):
        state = empty_workspace()
        created = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "参观", "start_time": 100, "duration_minutes": 90, "place": PLACE},
        }])[0]
        updated = apply_calendar_changes(state, [{
            "operation": "update", "schedule_id": created["id"], "event": {"title": "参观故宫"},
        }])[0]
        self.assertEqual(updated["title"], "参观故宫")
        removed = apply_calendar_changes(state, [{"operation": "delete", "schedule_id": created["id"]}])[0]
        self.assertTrue(removed["deleted"])
        self.assertFalse(state["schedules"])

    def test_calendar_delete_does_not_duplicate_untouched_schedules(self):
        state = empty_workspace()
        palace, restaurant, lake = apply_calendar_changes(state, [
            {"operation": "create", "event": {"title": "故宫", "start_time": 1_900_000_000}},
            {"operation": "create", "event": {"title": "四季民福", "start_time": 1_900_007_200}},
            {"operation": "create", "event": {"title": "什刹海", "start_time": 1_900_014_400}},
        ])
        changed = apply_calendar_changes(state, [
            {"operation": "delete", "schedule_id": palace["id"]},
            {"operation": "create", "event": {
                "title": restaurant["title"],
                "start_time": restaurant["start_time"],
                "duration_minutes": restaurant["duration_minutes"],
            }},
            {"operation": "create", "event": {
                "title": lake["title"],
                "start_time": lake["start_time"],
                "duration_minutes": lake["duration_minutes"],
            }},
        ])
        self.assertEqual([item["title"] for item in changed], ["故宫"])
        self.assertEqual(
            sorted(item["title"] for item in state["schedules"].values()),
            ["什刹海", "四季民福"],
        )

    def test_calendar_mutation_repairs_exact_legacy_duplicates(self):
        state = empty_workspace()
        lake = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "什刹海", "start_time": 1_900_014_400},
        }])[0]
        duplicate = dict(lake)
        duplicate["id"] = "legacy-duplicate"
        duplicate["created_at"] = lake["created_at"] + 1
        state["schedules"][duplicate["id"]] = duplicate
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "午餐", "start_time": 1_900_021_600},
        }])
        self.assertEqual(
            [item["title"] for item in state["schedules"].values()].count("什刹海"),
            1,
        )

    def test_calendar_mutations_before_beijing_today_are_rejected(self):
        state = empty_workspace()
        past = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "历史日程", "start_time": 1_700_000_000, "place": PLACE},
        }])[0]
        now = 1_800_000_000
        with self.assertRaisesRegex(ValueError, "只供查看"):
            validate_calendar_change_window(
                state, [{"operation": "delete", "schedule_id": past["id"]}], now=now,
            )
        with self.assertRaisesRegex(ValueError, "今天之前"):
            validate_calendar_change_window(
                state, [{"operation": "create", "event": {"title": "补录", "start_time": 1_700_000_000}}],
                now=now,
            )

    def test_calendar_change_preview_reports_overlap(self):
        state = empty_workspace()
        existing = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "已有会议", "start_time": 1_900_000_000, "duration_minutes": 60},
        }])[0]
        warnings = calendar_change_warnings(state, [{
            "operation": "create",
            "event": {"title": "冲突会议", "start_time": existing["start_time"] + 1800, "duration_minutes": 60},
        }])
        self.assertEqual(warnings, ["“已有会议”与“冲突会议”时间重叠"])

    def test_meeting_proposal_preserves_missing_times_for_structured_ui(self):
        payload = meeting_action_payload(empty_workspace(), "产品讨论", "", "")
        self.assertEqual(payload["subject"], "产品讨论")
        self.assertEqual(payload["missing_fields"], ["start_time", "end_time"])
        self.assertEqual(payload["validation_errors"], [])

    async def test_meeting_proposal_can_be_edited_and_rechecks_conflicts(self):
        store = FakeStore()
        state = empty_workspace()
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "已有日程", "start_time": 4_088_368_800, "duration_minutes": 60},
        }])
        action = new_action(
            "meeting_create",
            meeting_action_payload(state, "联调会", "", ""),
            requires_confirmation=True,
        )
        put_action(state, action)
        await save_workspace(store, USER_WORKSPACE_ID, state)

        updated = await handler(FakeContext(store, {
            "operation": "update_meeting_action",
            "action_id": action["id"],
            "version": action["version"],
            "subject": "联调会（修改）",
            "start_time": "2099-07-22T10:30:00+08:00",
            "end_time": "2099-07-22T11:30:00+08:00",
        }))

        edited = updated["action"]
        self.assertEqual(edited["version"], 2)
        self.assertEqual(edited["payload"]["missing_fields"], [])
        self.assertIn("时间重叠", edited["payload"]["warnings"][0])
        verify_action_snapshot((await load_workspace(store, USER_WORKSPACE_ID))["actions"][action["id"]])

    def test_calendar_context_exposes_current_user_schedule_ids_and_beijing_time(self):
        state = empty_workspace()
        state["schedules"]["cal-live"] = {
            "id": "cal-live", "title": "游览寒山寺", "start_time": 1784156400,
            "duration_minutes": 60, "location": "苏州市姑苏区",
        }
        context = json.loads(calendar_context(state))
        self.assertEqual(context[0]["id"], "cal-live")
        self.assertIn("+08:00", context[0]["start_time"])

    def test_action_snapshot_tampering_is_rejected(self):
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        action["payload"]["subject"] = "被篡改"
        with self.assertRaisesRegex(ValueError, "快照校验失败"):
            verify_action_snapshot(action)

    def test_provider_ledger_blocks_duplicate_side_effects(self):
        state = empty_workspace()
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        begin_action_execution(action, owner="test", now=100)
        first = start_provider_call(state, action, 100)
        with self.assertRaisesRegex(ValueError, "未核对"):
            start_provider_call(state, action, 101)
        finish_provider_call(state, action, {"ok": True, "meeting_id": "m1"}, 102)
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(action["status"], "succeeded")

    def test_provider_unknown_result_requires_manual_reconciliation(self):
        state = empty_workspace()
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        begin_action_execution(action, owner="test", now=100)
        call = start_provider_call(state, action, 100)
        finish_provider_call(
            state, action,
            {"ok": False, "error": "请求中断", "reconciliation_required": True},
            102,
        )
        self.assertEqual(call["status"], "unknown")
        self.assertEqual(action["status"], "reconciliation_required")
        self.assertTrue(action["reconciliation_required"])

    def test_expired_execution_requires_reconciliation_and_never_retries(self):
        state = empty_workspace()
        action = new_action("image_generate", {"prompt": "test"}, requires_confirmation=False)
        begin_action_execution(action, owner="test", now=100, lease_seconds=30)
        put_action(state, action)
        recovered = recover_stale_actions(state, 131)
        self.assertEqual(len(recovered), 1)
        stored = state["actions"][action["id"]]
        self.assertEqual(stored["status"], "reconciliation_required")
        self.assertTrue(stored["reconciliation_required"])

    async def test_map_action_requires_explicit_activation(self):
        store = FakeStore()
        state = empty_workspace()
        action = new_action("map_recommendation", {"title": "推荐", "places": [PLACE]}, requires_confirmation=False)
        put_action(state, action)
        await save_workspace(store, USER_WORKSPACE_ID, state)
        before = await handler(FakeContext(store, {"operation": "get"}))
        self.assertIsNone(before["map"])
        after = await handler(FakeContext(store, {"operation": "activate_map", "action_id": action["id"], "version": 1}))
        self.assertEqual(after["map"]["places"][0]["place_id"], "poi-1")
        proactive = await load_proactive_state(store)
        self.assertEqual(proactive["checkpoints"]["route_change"]["schedule_count"], 0)
        self.assertTrue(any(event["type"] == "route_changed" for event in proactive["events"].values()))

    async def test_model_selected_places_are_verified_in_parallel(self):
        started: set[str] = set()
        all_started = asyncio.Event()

        async def provider(_map_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 3)
            started.add(query)
            if len(started) == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=0.2)
            return [{
                **PLACE,
                "place_id": f"poi-{query}",
                "name": query,
                "address": f"北京市朝阳区{query}",
            }]

        selected, candidates, missing = await verify_place_queries_parallel(
            provider,
            "map-key",
            ["餐馆甲", "餐馆乙", "餐馆丙"],
            city="北京",
            timeout_seconds=1,
        )

        self.assertEqual([place["name"] for place in selected], ["餐馆甲", "餐馆乙", "餐馆丙"])
        self.assertEqual(len(candidates), 3)
        self.assertEqual(missing, [])

    async def test_model_selected_place_rejects_wrong_city_and_unrelated_name(self):
        valid = {
            **PLACE,
            "place_id": "valid-restaurant",
            "name": "小吊梨汤(王府井银泰店)",
            "address": "北京市东城区王府井大街88号",
            "city": "北京市",
        }
        wrong_city = {
            **PLACE,
            "place_id": "wrong-city",
            "name": "小吊梨汤",
            "address": "上海市浦东新区",
            "city": "上海市",
        }
        unrelated = {
            **PLACE,
            "place_id": "unrelated",
            "name": "庐江县气象局",
            "address": "安徽省合肥市庐江县",
            "city": "庐江县",
        }

        async def provider(_map_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 3)
            if "小吊梨汤" in query:
                return [wrong_city, valid]
            return [unrelated]

        selected, candidates, missing = await verify_place_queries_parallel(
            provider,
            "map-key",
            ["小吊梨汤王府井银泰店", "四季民福王府井店"],
            city="北京",
            timeout_seconds=1,
        )

        self.assertEqual([place["place_id"] for place in selected], ["valid-restaurant"])
        self.assertEqual([place["place_id"] for place in candidates], ["valid-restaurant"])
        self.assertEqual(missing, ["四季民福王府井店"])

    async def test_map_recommendation_keeps_verified_subset(self):
        async def provider(_map_key, query, *, city, limit):
            if query == "未核实餐馆":
                return []
            return [{**PLACE, "place_id": f"poi-{query}", "name": query}]

        with patch("agents.chat._ui_tools.provider_search_places", new=provider):
            tools = build_production_tools(None, store=FakeStore(), conversation_id="partial-map", env={})
            tool = next(item for item in tools if item.name == "recommend_places_on_map")
            result = json.loads(await tool.ainvoke({
                "queries": ["真实餐馆", "未核实餐馆"],
                "city": "北京",
                "title": "餐馆推荐",
                "action_text": "在地图中查看",
            }))

        self.assertTrue(result["partial"])
        self.assertEqual(result["verified_place_count"], 1)
        self.assertEqual(result["unverified_queries"], ["未核实餐馆"])
        self.assertIn("实际核实成功 1/2 个地点", result["response_constraint"])
        self.assertIn("正文只能声称地图显示了 1 个", result["response_constraint"])
        self.assertIn("未核实餐馆", result["response_constraint"])
        self.assertEqual([place["name"] for place in result["action"]["payload"]["places"]], ["真实餐馆"])

    async def test_map_recommendation_rejects_when_every_place_is_unverified(self):
        async def provider(_map_key, query, *, city, limit):
            return []

        with patch("agents.chat._ui_tools.provider_search_places", new=provider):
            tools = build_production_tools(None, store=FakeStore(), conversation_id="empty-map", env={})
            tool = next(item for item in tools if item.name == "recommend_places_on_map")
            with self.assertRaisesRegex(ValueError, "所有候选地点都未通过真实地点服务核实"):
                await tool.ainvoke({
                    "queries": ["未核实餐馆甲", "未核实餐馆乙"],
                    "city": "北京",
                    "title": "餐馆推荐",
                    "action_text": "在地图中查看",
                })

    async def test_nearby_recommendation_reuses_schedule_anchor_and_prepares_map(self):
        store = FakeStore()
        anchor = {
            **PLACE,
            "place_id": "orange-hotel",
            "name": "桔子酒店(北京中关村软件园店)",
            "address": "北京市海淀区西北旺付家窑丁2号",
            "latitude": 40.042246,
            "longitude": 116.255289,
        }
        state = empty_workspace()
        state["schedules"]["hotel-stay"] = {
            "id": "hotel-stay",
            "title": "入住桔子酒店",
            "extra": {"place": anchor},
        }
        await save_user_workspace(store, state)
        breakfast_places = [
            {
                **PLACE,
                "place_id": "breakfast-1",
                "name": "庆丰包子铺(软件园店)",
                "address": "北京市海淀区软件园路",
                "latitude": 40.0419,
                "longitude": 116.257,
                "distance_to_anchor_meters": 180.0,
            },
            {
                **PLACE,
                "place_id": "breakfast-2",
                "name": "麦当劳(西北旺店)",
                "address": "北京市海淀区西北旺路",
                "latitude": 40.044,
                "longitude": 116.258,
                "distance_to_anchor_meters": 360.0,
            },
        ]

        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=AsyncMock(),
        ) as anchor_provider, patch(
            "agents.chat._ui_tools.provider_search_places_nearby",
            new=AsyncMock(return_value=breakfast_places),
        ) as nearby_provider:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="nearby-breakfast",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "桔子酒店(北京中关村软件园店)",
                "query": "早餐店",
                "city": "北京",
                "limit": 5,
                "title": "酒店附近早餐",
                "action_text": "在地图中查看",
            }))

        anchor_provider.assert_not_awaited()
        nearby_provider.assert_awaited_once_with(
            "map-key",
            "早餐店",
            anchor,
            radius_meters=2000,
            limit=5,
        )
        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(result["anchor"]["place_id"], "orange-hotel")
        self.assertEqual(result["verified_place_count"], 2)
        self.assertEqual(
            [place["place_id"] for place in result["action"]["payload"]["places"]],
            ["breakfast-1", "breakfast-2"],
        )

    async def test_nearby_current_location_uses_request_scoped_browser_fix(self):
        browser_location = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 39.913,
            "longitude": 116.456,
            "coordinate_type": "wgs84",
        }
        park = {
            **PLACE,
            "place_id": "nearby-park",
            "name": "测试公园",
            "address": "北京市朝阳区",
            "latitude": 39.914,
            "longitude": 116.455,
            "distance_to_anchor_meters": 180.0,
        }
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=AsyncMock(),
        ) as place_search, patch(
            "agents.chat._ui_tools.provider_search_places_nearby",
            new=AsyncMock(return_value=[park]),
        ) as nearby_search:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="nearby-browser-location",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=browser_location,
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "",
                "query": "公园",
                "use_current_location_as_anchor": True,
            }))

        place_search.assert_not_awaited()
        nearby_search.assert_awaited_once_with(
            "map-key",
            "公园",
            browser_location,
            radius_meters=2_000,
            limit=5,
        )
        self.assertEqual(result["anchor"]["place_id"], "browser-current-location")
        self.assertEqual(result["groups"][0]["anchor_query"], "当前位置")
        self.assertEqual(result["places"][0]["place_id"], "nearby-park")

    async def test_current_location_tool_returns_tencent_address_without_coordinates(self):
        browser_location = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 43.8171,
            "longitude": 125.3235,
            "coordinate_type": "wgs84",
            "accuracy_meters": 18,
        }
        resolved = {
            "provider": "tencent",
            "address": "吉林省长春市朝阳区前进大街2699号",
            "province": "吉林省",
            "city": "长春市",
            "district": "朝阳区",
            "street": "前进大街",
            "street_number": "2699号",
            "nearby_landmark": "吉林大学前卫南区",
        }
        with patch(
            "agents.chat._ui_tools.provider_reverse_geocode",
            new=AsyncMock(return_value=resolved),
        ) as provider:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="current-location-address",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=browser_location,
            )
            tool = next(item for item in tools if item.name == "get_current_location")
            result = json.loads(await tool.ainvoke({}))

        provider.assert_awaited_once_with("map-key", browser_location)
        self.assertTrue(result["location_available"])
        self.assertEqual(result["location"]["city"], "长春市")
        self.assertNotIn("latitude", result["location"])
        self.assertNotIn("longitude", result["location"])

    async def test_current_location_tool_without_browser_fix_skips_provider(self):
        with patch(
            "agents.chat._ui_tools.provider_reverse_geocode",
            new=AsyncMock(),
        ) as provider:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="current-location-unavailable",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=None,
            )
            tool = next(item for item in tools if item.name == "get_current_location")
            result = json.loads(await tool.ainvoke({}))

        provider.assert_not_awaited()
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["id"], "manual_location")
        self.assertEqual(result["clarification"]["fields"][0]["type"], "text")

    async def test_nearby_current_location_without_browser_fix_never_searches_provider(self):
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=AsyncMock(),
        ) as place_search, patch(
            "agents.chat._ui_tools.provider_search_places_nearby",
            new=AsyncMock(),
        ) as nearby_search:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="nearby-browser-location-missing",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                browser_current_location=None,
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "",
                "query": "好玩的地方",
                "use_current_location_as_anchor": True,
            }))

        place_search.assert_not_awaited()
        nearby_search.assert_not_awaited()
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["id"], "nearby_anchor")

    async def test_nearby_recommendation_keeps_successful_alternative_anchor(self):
        samsung = {
            **PLACE,
            "place_id": "samsung-tower",
            "name": "北京三星大厦",
            "address": "北京市朝阳区景辉街31号院1号楼",
            "latitude": 39.913,
            "longitude": 116.456,
        }
        guomao = {
            **PLACE,
            "place_id": "guomao-tower",
            "name": "北京国贸大厦",
            "address": "北京市朝阳区建国门外大街1号",
            "latitude": 39.909,
            "longitude": 116.459,
        }
        restaurant = {
            **PLACE,
            "place_id": "restaurant-samsung",
            "name": "三星大厦附近餐厅",
            "address": "北京市朝阳区景辉街",
            "latitude": 39.914,
            "longitude": 116.455,
            "distance_to_anchor_meters": 260.0,
        }

        async def anchor_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            self.assertEqual(limit, 5)
            return [samsung] if "三星" in query else [guomao]

        async def nearby_provider(
            _key, query, anchor, *, radius_meters, limit,
        ):
            self.assertEqual(query, "适合生日聚餐的餐厅")
            self.assertEqual(radius_meters, 2_000)
            return [restaurant] if anchor["place_id"] == "samsung-tower" else []

        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=AsyncMock(side_effect=anchor_provider),
        ) as anchor_lookup, patch(
            "agents.chat._ui_tools.provider_search_places_nearby",
            new=AsyncMock(side_effect=nearby_provider),
        ) as nearby_lookup:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="alternative-nearby-restaurants",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            result = json.loads(await tool.ainvoke({
                "anchor_query": "北京三星大厦",
                "anchor_queries": ["北京三星大厦", "北京国贸大厦"],
                "query": "适合生日聚餐的餐厅",
                "city": "北京",
                "limit": 5,
                "title": "三星大厦或国贸大厦附近餐厅",
                "action_text": "查看附近餐厅",
            }))

        self.assertEqual(anchor_lookup.await_count, 2)
        self.assertEqual(nearby_lookup.await_count, 2)
        self.assertEqual(result["verified_place_count"], 1)
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(
            result["action"]["payload"]["places"][0]["nearby_anchor_name"],
            "北京三星大厦",
        )
        self.assertEqual(
            [place["place_id"] for place in result["action"]["payload"]["places"]],
            ["restaurant-samsung"],
        )

    async def test_nearby_recommendation_respects_user_explicit_strict_radius(self):
        anchor = {
            **PLACE,
            "place_id": "hotel",
            "name": "桔子酒店(北京中关村软件园店)",
        }
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][anchor["place_id"]] = anchor
        await save_user_workspace(store, state)
        with patch(
            "agents.chat._ui_tools.provider_search_places_nearby",
            new=AsyncMock(return_value=[]),
        ) as nearby_provider:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="strict-nearby",
                env={"TENCENT_MAP_SERVER_KEY": "key"},
            )
            tool = next(item for item in tools if item.name == "recommend_nearby_places_on_map")
            with self.assertRaisesRegex(ValueError, "500 米内"):
                await tool.ainvoke({
                    "anchor_query": anchor["name"],
                    "query": "早餐店",
                    "radius_meters": 500,
                    "strict_radius": True,
                })
        self.assertEqual(nearby_provider.await_args.kwargs["radius_meters"], 500)

    async def test_route_tool_resolves_a_brand_near_a_verified_anchor(self):
        station = {
            **PLACE,
            "place_id": "station",
            "name": "北京站",
            "address": "北京市东城区毛家湾胡同甲13号",
        }
        hospital = {
            **PLACE,
            "place_id": "hospital",
            "name": "中国人民解放军总医院",
            "address": "北京市海淀区复兴路28号",
            "latitude": 39.902,
            "longitude": 116.276,
        }
        hotel = {
            **PLACE,
            "place_id": "hotel",
            "name": "锦江之星(北京五棵松店)",
            "address": "北京市海淀区西四环中路",
            "latitude": 39.906,
            "longitude": 116.271,
            "distance_to_anchor_meters": 620,
        }

        async def place_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            return [station] if query == "北京站" else [hospital]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 13_800,
            "duration_seconds": 2_100,
            "fare": {"taxi_fare": 46},
        }
        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_search_places_nearby", new=AsyncMock(return_value=[hotel])) as nearby, \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="verified-route",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "city": "北京",
                "destination_near_query": "北京301医院",
            }))

        self.assertEqual(result["origin"]["place_id"], "station")
        self.assertEqual(result["destination"]["place_id"], "hotel")
        self.assertEqual(result["route"]["distance_kilometers"], 13.8)
        self.assertEqual(result["route"]["duration_minutes"], 35)
        self.assertTrue(result["evidence_contract"]["strict"])
        self.assertIn(
            "alternative_lines",
            result["evidence_contract"]["unknown_fields"],
        )
        self.assertIn(
            "route.transit.walking_distance_meters",
            result["evidence_contract"]["aggregate_only"],
        )
        nearby.assert_awaited_once()
        planner.assert_awaited_once()

    async def test_route_tool_preserves_user_order_for_multi_stop_itinerary(self):
        places = {
            "腾讯北京总部": {
                **PLACE,
                "place_id": "tencent",
                "name": "腾讯北京总部大楼",
            },
            "锦江之星": {
                **PLACE,
                "place_id": "jinjiang",
                "name": "锦江之星品尚(北京五棵松店)",
            },
            "烤肉刘王府井店": {
                **PLACE,
                "place_id": "restaurant",
                "name": "清真·烤肉刘炙子烤肉(故宫·王府井店)",
            },
            "桔子酒店北京中关村软件园": {
                **PLACE,
                "place_id": "orange",
                "name": "桔子酒店(北京中关村软件园店)",
            },
        }

        async def place_provider(_key, query, *, city, limit):
            self.assertEqual(city, "北京")
            return [places[query]]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 52_400,
            "duration_seconds": 7_200,
            "fare": {"taxi": {"low": 120, "high": 150}},
        }
        store = FakeStore()
        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="ordered-itinerary",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "city": "北京",
                "ordered_stops": [
                    {"query": "腾讯北京总部"},
                    {"query": "锦江之星"},
                    {"query": "烤肉刘王府井店"},
                    {"query": "桔子酒店北京中关村软件园"},
                ],
            }))

        ordered_ids = [place["place_id"] for place in result["ordered_stops"]]
        self.assertEqual(ordered_ids, ["tencent", "jinjiang", "restaurant", "orange"])
        planned_places = planner.await_args.args[1]
        self.assertEqual(
            [place["place_id"] for place in planned_places],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertFalse(planner.await_args.kwargs["optimize"])
        self.assertIn("绝不能重新排序", result["response_constraint"])
        saved = await load_user_workspace(store)
        self.assertEqual(saved["latest_route_plan"]["id"], result["route_plan_id"])
        self.assertEqual(
            saved["route_plans"][result["route_plan_id"]]["id"],
            result["route_plan_id"],
        )
        self.assertEqual(
            [item["place_id"] for item in saved["latest_route_plan"]["ordered_stops"]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertIn(result["route_plan_id"], latest_route_context(saved))

    async def test_route_tool_restores_origin_dropped_by_second_model_call(self):
        names = {
            "腾讯北京总部": "tencent",
            "锦江之星": "jinjiang",
            "王府井餐厅": "restaurant",
            "桔子酒店": "orange",
        }

        async def place_provider(_key, query, *, city, limit):
            return [{
                **PLACE,
                "place_id": names[query],
                "name": query,
            }]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 50_000,
            "duration_seconds": 7_000,
            "fare": {},
        }
        planned_stops = [
            {"query": "腾讯北京总部", "near_query": ""},
            {"query": "锦江之星", "near_query": ""},
            {"query": "王府井餐厅", "near_query": ""},
            {"query": "桔子酒店", "near_query": ""},
        ]
        store = FakeStore()
        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="restore-dropped-origin",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=planned_stops,
                planned_route_city="北京",
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "city": "北京",
                # Simulate the full-history tool model accidentally omitting
                # the stated origin while retaining later stops.
                "ordered_stops": [
                    {"query": "锦江之星"},
                    {"query": "王府井餐厅"},
                    {"query": "桔子酒店"},
                ],
            }))

        self.assertEqual(
            [item["place_id"] for item in result["ordered_stops"]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )
        self.assertEqual(
            [item["place_id"] for item in planner.await_args.args[1]],
            ["tencent", "jinjiang", "restaurant", "orange"],
        )

    async def test_route_tool_preserves_browser_origin_before_planned_stops(self):
        destinations = {
            "颐和园": {**PLACE, "place_id": "summer-palace", "name": "颐和园"},
            "故宫": {**PLACE, "place_id": "forbidden-city", "name": "故宫"},
        }

        async def place_provider(_key, query, *, city, limit):
            return [destinations[query]]

        browser_origin = {
            **PLACE,
            "place_id": "browser-current-location",
            "name": "当前位置",
            "provider": "browser-wgs84",
            "coordinate_type": "wgs84",
            "ephemeral": True,
        }
        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 30_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        planned_stops = [{"query": "颐和园"}, {"query": "故宫"}]
        store = FakeStore()
        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="browser-origin-planned-stops",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=planned_stops,
                planned_route_uses_current_location=True,
                browser_current_location=browser_origin,
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "ordered_stops": planned_stops,
                "use_current_location_as_origin": True,
            }))

        self.assertEqual(
            [item["place_id"] for item in result["ordered_stops"]],
            ["browser-current-location", "summer-palace", "forbidden-city"],
        )
        self.assertEqual(
            [item["place_id"] for item in planner.await_args.args[1]],
            ["browser-current-location", "summer-palace", "forbidden-city"],
        )
        saved = await load_user_workspace(store)
        self.assertNotIn(
            "browser-current-location",
            saved["place_candidates"],
        )
        persisted_origin = saved["latest_route_plan"]["ordered_stops"][0]
        self.assertEqual(
            set(persisted_origin),
            {"place_id", "name", "provider", "ephemeral"},
        )
        self.assertNotIn("latitude", persisted_origin)
        self.assertNotIn("longitude", persisted_origin)
        self.assertNotIn("address", persisted_origin)

    async def test_route_ambiguity_card_identifies_intermediate_stop(self):
        places = {
            "起点公园": [{**PLACE, "place_id": "origin", "name": "起点公园"}],
            "第一站博物馆": [{**PLACE, "place_id": "museum", "name": "第一站博物馆"}],
            "同名餐厅": [
                {**PLACE, "place_id": "restaurant-a", "name": "同名餐厅 A 店"},
                {**PLACE, "place_id": "restaurant-b", "name": "同名餐厅 B 店"},
            ],
            "终点车站": [{**PLACE, "place_id": "destination", "name": "终点车站"}],
        }

        async def place_provider(_key, query, *, city, limit):
            return places[query]

        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="intermediate-stop-ambiguity",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "起点公园"},
                    {"query": "第一站博物馆"},
                    {"query": "同名餐厅"},
                    {"query": "终点车站"},
                ],
            }))

        field = result["clarification"]["fields"][0]
        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(field["id"], "route_stop_3")
        self.assertEqual(field["label"], "请选择具体第 3 站")
        self.assertIn("第 3 站", result["clarification"]["prompt"])
        planner.assert_not_awaited()

    async def test_route_shows_ranked_candidates_when_provider_has_no_correction(self):
        origin = {**PLACE, "place_id": "station", "name": "北京站"}
        candidates = [
            {**PLACE, "place_id": "square", "name": "天安门广场"},
            {**PLACE, "place_id": "gate", "name": "天安门"},
            {**PLACE, "place_id": "subway", "name": "天安门东[地铁站]"},
        ]

        async def place_provider(_key, query, *, city, limit):
            return [origin] if query == "北京站" else candidates

        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="semantic-candidate-route",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "天安们",
                "route_mode": "walking",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["type"], "single")
        self.assertGreaterEqual(len(field["options"]), 2)
        self.assertIn("天安门", field["options"][0])
        planner.assert_not_awaited()

    async def test_route_semantic_review_can_use_canonical_provider_candidate(self):
        class CanonicalPlaceModel:
            def __init__(self):
                self.schema = None
                self.calls = 0

            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                self.calls += 1
                return {
                    "parsed": self.schema(
                        unique_intent=True,
                        selected_place_id="station-main",
                    ),
                }

        model = CanonicalPlaceModel()
        station_candidates = [
            {**PLACE, "place_id": "station-main", "name": "北京站"},
            {
                **PLACE,
                "place_id": "station-subway",
                "name": "北京站[地铁站]",
            },
        ]
        destination = {
            **PLACE,
            "place_id": "destination",
            "name": "故宫博物院",
        }

        async def place_provider(_key, query, *, city, limit):
            return station_candidates if query == "北京站" else [destination]

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 8_000,
            "duration_seconds": 1_800,
            "fare": {},
        }
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=place_provider,
        ), patch(
            "agents.chat._ui_tools.provider_plan_route",
            new=AsyncMock(return_value=route),
        ) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="canonical-provider-place",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                place_disambiguation_model=model,
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "故宫博物院",
            }))

        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(result["ordered_stops"][0]["place_id"], "station-main")
        self.assertEqual(model.calls, 1)
        planner.assert_awaited_once()

    async def test_route_search_timeout_returns_fill_in_card(self):
        async def place_provider(_key, _query, *, city, limit):
            raise TimeoutError("provider deadline")

        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=place_provider,
        ), patch(
            "agents.chat._ui_tools.load_place_cache",
            new=AsyncMock(return_value=None),
        ), patch(
            "agents.chat._ui_tools.provider_plan_route",
            new=AsyncMock(),
        ) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="route-timeout-fill-card",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                map_preferences={"search_timeout_seconds": 3},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "起点",
                "destination_query": "无法核实的终点",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(
            result["clarification"]["fields"][0]["type"],
            "text",
        )
        self.assertIn("时间预算", result["clarification"]["prompt"])
        planner.assert_not_awaited()

    async def test_route_collects_all_place_blockers_in_one_card_group(self):
        origin = {**PLACE, "place_id": "origin", "name": "北京站"}
        branches = [
            {
                **PLACE,
                "place_id": "branch-a",
                "name": "北京通州万达广场",
                "address": "新华西街58号",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京通州万达广场",
                    "evidence": "tencent_place_search",
                },
            },
            {
                **PLACE,
                "place_id": "branch-b",
                "name": "北京五棵松万达广场",
                "address": "复兴路69号",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京五棵松万达广场",
                    "evidence": "tencent_place_search",
                },
            },
        ]
        destination = {
            **PLACE,
            "place_id": "destination",
            "name": "北京西站",
        }

        async def place_provider(_key, query, *, city, limit):
            return {
                "北京站": [origin],
                "万达广场": branches,
                "不存在终点": [],
                "北京西站": [destination],
            }[query]

        store = FakeStore()
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=place_provider,
        ), patch(
            "agents.chat._ui_tools.provider_plan_route",
            new=AsyncMock(),
        ) as planner:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="route-multiple-card-state",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools if item.name == "plan_route_between_places"
            )
            first = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "北京站"},
                    {"query": "万达广场"},
                    {"query": "不存在终点"},
                ],
            }))
            third = json.loads(await route_tool.ainvoke({
                "ordered_stops": [
                    {"query": "北京站"},
                    {"query": "万达广场"},
                    {"query": "北京西站"},
                ],
            }))

        fields = first["clarification"]["fields"]
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["type"], "single")
        self.assertEqual(fields[1]["type"], "text")
        self.assertEqual(fields[0]["id"], "route_stop_2")
        self.assertRegex(fields[1]["id"], r"route_destination_[0-9a-f]{6}")
        self.assertIn("一次填完", first["clarification"]["prompt"])
        self.assertEqual(third["clarification"]["fields"][0]["type"], "single")
        self.assertIn("北京通州万达广场", third["clarification"]["fields"][0]["options"][0])
        planner.assert_not_awaited()

    def test_complete_planner_route_preserves_literal_user_place_text(self):
        self.assertEqual(
            preserve_planned_route_stops(
                [("腾讯北京总部大楼", ""), ("北京站", "")],
                [{"query": "腾讯总部"}, {"query": "北京站"}],
            ),
            [("腾讯总部", ""), ("北京站", "")],
        )

    def test_route_tool_fallback_does_not_rewrite_place_text(self):
        self.assertEqual(
            preserve_planned_route_stops(
                [("北京站", ""), ("天安门", "")],
                [],
                "从北京站步行去天安们",
            ),
            [("北京站", ""), ("天安门", "")],
        )

    async def test_route_calendar_proposal_rejects_compressed_stops_and_accepts_complete_order(self):
        store = FakeStore()
        state = empty_workspace()
        now = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)
        stops = [
            {
                **PLACE,
                "place_id": place_id,
                "name": name,
                "address": f"北京市{name}地址",
            }
            for place_id, name in (
                ("tencent", "腾讯北京总部大楼"),
                ("jinjiang", "锦江之星品尚(北京五棵松店)"),
                ("restaurant", "清真·烤肉刘炙子烤肉(故宫·王府井店)"),
                ("orange", "桔子酒店(北京中关村软件园店)"),
            )
        ]
        state["place_candidates"] = {item["place_id"]: item for item in stops}
        state["latest_route_plan"] = {
            "id": "routeplan-complete",
            "created_at": int(time.time()),
            "ordered_stops": stops,
            "distance_meters": 62_800,
            "duration_seconds": 9_720,
        }
        await save_user_workspace(store, state)
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="route-calendar",
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(item for item in tools if item.name == "propose_calendar_changes")

        def change(index: int) -> dict:
            start = now + timedelta(minutes=index * 45)
            return {
                "operation": "create",
                "event": {
                    "title": f"第{index + 1}站：{stops[index]['name']}",
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(minutes=30)).isoformat(),
                    "place_id": stops[index]["place_id"],
                },
            }

        with self.assertRaisesRegex(ValueError, "完整路线包含 4 个站点"):
            await calendar_tool.ainvoke({
                "summary": "压缩后的两站行程",
                "source_route_plan_id": "routeplan-complete",
                "changes": [change(0), change(2)],
            })

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "完整四站行程",
            "source_route_plan_id": "routeplan-complete",
            "changes": [change(index) for index in range(4)],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        self.assertEqual(result["action"]["payload"]["source_route_plan_id"], "routeplan-complete")
        self.assertEqual(len(result["action"]["payload"]["changes"]), 4)

    async def test_route_calendar_normalizes_instant_verified_stop_markers(self):
        store = FakeStore()
        state = empty_workspace()
        stops = [
            {
                **PLACE,
                "place_id": place_id,
                "name": name,
                "address": f"北京市{name}地址",
            }
            for place_id, name in (
                ("beijing-station", "北京站"),
                ("forbidden-city", "故宫博物院"),
                ("beijing-west", "北京西站"),
            )
        ]
        state["place_candidates"] = {item["place_id"]: item for item in stops}
        route_plan = {
            "id": "routeplan-instant-markers",
            "created_at": int(time.time()),
            "ordered_stops": stops,
            "distance_meters": 18_000,
            "duration_seconds": 4_200,
            "mode": "transit",
        }
        state["latest_route_plan"] = route_plan
        state["route_plans"] = {route_plan["id"]: route_plan}
        await save_user_workspace(store, state)
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="route-calendar-instant-markers",
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)

        def event(
            index: int,
            event_start: datetime,
            duration_minutes: int,
        ) -> dict:
            return {
                "operation": "create",
                "event": {
                    "title": stops[index]["name"],
                    "start_time": event_start.isoformat(),
                    "end_time": (
                        event_start + timedelta(minutes=duration_minutes)
                    ).isoformat(),
                    "location_kind": "physical",
                },
            }

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "含瞬时出发和抵达提醒的三站行程",
            "source_route_plan_id": "routeplan-instant-markers",
            "changes": [
                event(0, start, 0),
                event(1, start + timedelta(minutes=40), 45),
                event(2, start + timedelta(minutes=120), 0),
            ],
        }))

        payload = result["action"]["payload"]
        self.assertEqual(
            payload["source_route_plan_id"],
            "routeplan-instant-markers",
        )
        self.assertEqual(
            [
                change["event"]["duration_minutes"]
                for change in payload["changes"]
            ],
            [1, 45, 1],
        )
        self.assertEqual(
            [
                change["event"]["place"]["place_id"]
                for change in payload["changes"]
            ],
            [stop["place_id"] for stop in stops],
        )
        self.assertTrue(
            any("最小粒度" in warning for warning in payload["warnings"])
        )
        self.assertTrue(
            any("站点顺序补齐" in warning for warning in payload["warnings"])
        )

    async def test_route_calendar_keeps_recent_source_when_another_route_is_latest(self):
        store = FakeStore()
        state = empty_workspace()
        intended_stops = [
            {
                **PLACE,
                "place_id": f"intended-{index}",
                "name": name,
                "address": f"北京市{name}地址",
            }
            for index, name in enumerate(("北京站", "故宫博物院", "北京西站"), 1)
        ]
        other_stops = [
            {
                **PLACE,
                "place_id": f"other-{index}",
                "name": name,
            }
            for index, name in enumerate(("上海站", "外滩"), 1)
        ]
        intended_route = {
            "id": "routeplan-intended",
            "created_at": int(time.time()) - 10,
            "ordered_stops": intended_stops,
            "duration_seconds": 4_200,
        }
        latest_route = {
            "id": "routeplan-other",
            "created_at": int(time.time()),
            "ordered_stops": other_stops,
            "duration_seconds": 1_800,
        }
        state["place_candidates"] = {
            stop["place_id"]: stop
            for stop in other_stops
        }
        state["latest_route_plan"] = latest_route
        state["route_plans"] = {
            intended_route["id"]: intended_route,
            latest_route["id"]: latest_route,
        }
        await save_user_workspace(store, state)
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="route-calendar-recent-source",
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))).replace(
            minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)
        changes = [
            {
                "operation": "create",
                "event": {
                    "title": stop["name"],
                    "start_time": (
                        start + timedelta(minutes=index * 60)
                    ).isoformat(),
                    "end_time": (
                        start + timedelta(minutes=index * 60 + 45)
                    ).isoformat(),
                },
            }
            for index, stop in enumerate(intended_stops)
        ]

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "把先前核实的北京路线加入日程",
            "source_route_plan_id": intended_route["id"],
            "changes": changes,
        }))

        payload = result["action"]["payload"]
        self.assertEqual(
            payload["source_route_plan_id"],
            intended_route["id"],
        )
        self.assertEqual(
            [
                change["event"]["place"]["place_id"]
                for change in payload["changes"]
            ],
            [stop["place_id"] for stop in intended_stops],
        )

    async def test_route_calendar_does_not_persist_implicit_browser_origin(self):
        store = FakeStore()
        state = empty_workspace()
        browser_origin = {
            **PLACE,
            "place_id": "browser-current-location",
            "provider": "browser-tencent",
            "name": "当前位置",
            "ephemeral": True,
        }
        destination = {
            **PLACE,
            "place_id": "summer-palace",
            "name": "颐和园",
            "address": "北京市海淀区新建宫门路19号",
        }
        state["place_candidates"] = {
            destination["place_id"]: destination,
        }
        state["latest_route_plan"] = {
            "id": "routeplan-browser-origin",
            "created_at": int(time.time()),
            "ordered_stops": [browser_origin, destination],
            "implicit_browser_origin": True,
            "distance_meters": 7_884,
            "duration_seconds": 1_380,
        }
        await save_user_workspace(store, state)
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="route-calendar-browser-origin",
            env={"TENCENT_MAP_SERVER_KEY": "map-key"},
        )
        calendar_tool = next(
            item for item in tools if item.name == "propose_calendar_changes"
        )
        start = datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "从当前位置去颐和园",
            "source_route_plan_id": "routeplan-browser-origin",
            "changes": [
                {
                    "operation": "create",
                    "event": {
                        "title": "从当前位置出发",
                        "start_time": start.isoformat(),
                        "end_time": (start + timedelta(minutes=1)).isoformat(),
                        "place_id": browser_origin["place_id"],
                    },
                },
                {
                    "operation": "create",
                    "event": {
                        "title": "游览颐和园",
                        "start_time": (start + timedelta(minutes=23)).isoformat(),
                        "end_time": (start + timedelta(hours=2)).isoformat(),
                        "place_id": destination["place_id"],
                    },
                },
            ],
        }))

        self.assertEqual(result["ui_action"], "calendar_action")
        payload = result["action"]["payload"]
        self.assertEqual(payload["source_route_plan_id"], "routeplan-browser-origin")
        self.assertEqual(len(payload["changes"]), 2)
        self.assertNotIn("place", payload["changes"][0]["event"])
        self.assertEqual(payload["changes"][0]["event"]["location"], "")
        self.assertEqual(
            payload["changes"][1]["event"]["place"]["place_id"],
            "summer-palace",
        )
        self.assertNotIn("browser-current-location", json.dumps(payload))

    async def test_route_tool_revalidates_descriptive_aliases_with_provider(self):
        store = FakeStore()
        state = empty_workspace()
        headquarters = {
            **PLACE,
            "place_id": "tencent",
            "name": "腾讯北京总部大楼",
            "address": "北京市海淀区西北旺东路10号院西区9号楼",
        }
        restaurant = {
            **PLACE,
            "place_id": "restaurant",
            "name": "清真·烤肉刘炙子烤肉(故宫·王府井店)",
            "address": "北京市东城区王府井大街",
        }
        state["place_candidates"] = {
            headquarters["place_id"]: headquarters,
            restaurant["place_id"]: restaurant,
        }
        await save_user_workspace(store, state)
        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 28_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            new=AsyncMock(side_effect=[[headquarters], [restaurant]]),
        ) as search, \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock(return_value=route)) as planner:
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="workspace-alias-route",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "腾讯北京总部",
                "destination_query": "烤肉刘（故宫·王府井店）",
                "city": "北京",
            }))

        self.assertEqual(result["origin"]["place_id"], "tencent")
        self.assertEqual(result["destination"]["place_id"], "restaurant")
        self.assertEqual(search.await_count, 2)
        planner.assert_awaited_once()

    def test_route_failure_fallback_does_not_claim_a_confirmation_card(self):
        content = tool_failure_fallback([
            HumanMessage(content="帮我规划四站行程"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "没有核实到第 3 站",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                name="plan_route_between_places",
                tool_call_id="route-failed",
            ),
        ])
        self.assertIn("没有完成路线规划", content)
        self.assertNotIn("确认卡", content)

    async def test_route_tool_asks_user_to_choose_when_nearby_brand_has_multiple_branches(self):
        station = {**PLACE, "place_id": "station", "name": "北京站"}
        hospital = {**PLACE, "place_id": "hospital", "name": "北京301医院"}
        hotels = [
            {
                **PLACE,
                "place_id": f"hotel-{index}",
                "name": f"锦江之星({name}店)",
                "address": f"北京市海淀区{name}路",
                "distance_to_anchor_meters": distance,
            }
            for index, (name, distance) in enumerate((("五棵松", 620), ("玉泉路", 1800)), 1)
        ]

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else [hospital]

        with patch("agents.chat._ui_tools.provider_search_places", new=place_provider), \
             patch("agents.chat._ui_tools.provider_search_places_nearby", new=AsyncMock(return_value=hotels)), \
             patch("agents.chat._ui_tools.provider_plan_route", new=AsyncMock()) as planner:
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="ambiguous-route",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(item for item in tools if item.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "city": "北京",
                "destination_near_query": "北京301医院",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        self.assertEqual(result["clarification"]["fields"][0]["type"], "single")
        self.assertEqual(len(result["clarification"]["fields"][0]["options"]), 2)
        self.assertEqual(
            set(result["clarification"]["fields"][0]["option_values"].values()),
            {"floris-place:hotel-1", "floris-place:hotel-2"},
        )
        planner.assert_not_awaited()

    async def test_route_card_choices_resume_by_place_id_without_repeated_search(self):
        station = {
            **PLACE,
            "place_id": "station",
            "name": "北京站",
            "address": "北京市东城区毛家湾胡同甲13号",
        }
        peach_places = [
            {
                **PLACE,
                "place_id": f"peach-{index}",
                "name": name,
                "address": address,
            }
            for index, (name, address) in enumerate((
                ("桃花源景区", "北京市海淀区黑山扈北口19号"),
                ("桃花湾", "北京市门头沟区妙峰山镇"),
            ), 1)
        ]
        park_places = [
            {
                **PLACE,
                "place_id": f"park-{index}",
                "name": name,
                "address": address,
            }
            for index, (name, address) in enumerate((
                ("百望山森林公园", "北京市海淀区黑山扈北口19号"),
                ("百望公园", "北京市海淀区西北旺镇"),
            ), 1)
        ]

        async def place_provider(_key, query, *, city, limit):
            if query == "北京站":
                return [station]
            if query == "桃花源景区":
                return peach_places
            if query == "Baiwang Park":
                return park_places
            raise AssertionError(f"confirmed candidate must not be searched again: {query}")

        route = {
            "provider": "tencent",
            "mode": "driving",
            "distance_meters": 28_000,
            "duration_seconds": 3_600,
            "fare": {},
        }
        store = FakeStore()
        search = AsyncMock(side_effect=place_provider)
        planner = AsyncMock(return_value=route)
        with patch("agents.chat._ui_tools.provider_search_places", new=search), \
             patch("agents.chat._ui_tools.provider_plan_route", new=planner):
            tools = build_production_tools(
                None,
                store=store,
                conversation_id="resume-route-place-ids",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            original_arguments = {
                "city": "北京",
                "ordered_stops": [
                    {"query": "北京站", "near_query": ""},
                    {"query": "桃花源景区", "near_query": ""},
                    {"query": "Baiwang Park", "near_query": ""},
                ],
            }
            first = json.loads(await route_tool.ainvoke(original_arguments))
            self.assertEqual(first["ui_action"], "clarification_action")
            fields = first["clarification"]["fields"]
            self.assertEqual(
                [field["id"] for field in fields],
                ["route_stop_2", "route_destination"],
            )
            answers = [
                {
                    "id": field["id"],
                    "value": field["option_values"][field["options"][0]],
                }
                for field in fields
            ]
            plan, resumed_arguments = resume_capability_protocol(
                {"needs_route": False},
                {
                    "version": "1",
                    "required_tools": ["plan_route_between_places"],
                    "planned_tool_arguments": {
                        "plan_route_between_places": original_arguments,
                    },
                },
                answers,
            )
            resumed_route = resumed_arguments["plan_route_between_places"]
            resumed_tools = build_production_tools(
                None,
                store=store,
                conversation_id="resume-route-place-ids",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
                planned_route_stops=plan["route_stops"],
                planned_route_city="北京",
            )
            resumed_tool = next(
                item for item in resumed_tools
                if item.name == "plan_route_between_places"
            )
            second = json.loads(await resumed_tool.ainvoke(resumed_route))

        self.assertEqual(second["ui_action"], "map_action")
        self.assertEqual(
            [place["place_id"] for place in second["ordered_stops"]],
            ["station", "peach-1", "park-1"],
        )
        self.assertEqual(search.await_count, 3)
        planner.assert_awaited_once()

    def test_resume_protocol_applies_selected_nearby_anchor_by_stable_field_id(self):
        _plan, arguments = resume_capability_protocol(
            {"needs_route": False},
            {
                "version": "1",
                "required_tools": ["plan_route_between_places"],
                "planned_tool_arguments": {
                    "plan_route_between_places": {
                        "origin_query": "北京站",
                        "destination_query": "锦江之星",
                        "destination_near_query": "万达广场",
                    },
                },
            },
            [{
                "id": "route_destination_anchor",
                "value": "floris-place:wanda-cbd",
            }],
        )
        route = arguments["plan_route_between_places"]
        self.assertEqual(route["destination_query"], "锦江之星")
        self.assertEqual(
            route["destination_near_query"],
            "floris-place:wanda-cbd",
        )

    async def test_route_tool_never_silently_picks_one_of_multiple_nearby_anchors(self):
        station = {**PLACE, "place_id": "station", "name": "北京站"}
        anchors = [
            {
                **PLACE,
                "place_id": "wanda-cbd",
                "name": "万达广场",
                "address": "北京市朝阳区建国路93号",
            },
            {
                **PLACE,
                "place_id": "wanda-fengtai",
                "name": "万达广场(丰台店)",
                "address": "北京市丰台区",
            },
        ]

        async def place_provider(_key, query, *, city, limit):
            return [station] if query == "北京站" else anchors

        with (
            patch(
                "agents.chat._ui_tools.provider_search_places",
                new=place_provider,
            ),
            patch(
                "agents.chat._ui_tools.provider_search_places_nearby",
                new=AsyncMock(),
            ) as nearby,
            patch(
                "agents.chat._ui_tools.provider_plan_route",
                new=AsyncMock(),
            ) as planner,
        ):
            tools = build_production_tools(
                None,
                store=FakeStore(),
                conversation_id="ambiguous-nearby-anchor",
                env={"TENCENT_MAP_SERVER_KEY": "map-key"},
            )
            route_tool = next(
                item for item in tools
                if item.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "北京站",
                "destination_query": "锦江之星",
                "destination_near_query": "万达广场",
                "city": "北京",
            }))

        self.assertEqual(result["ui_action"], "clarification_action")
        field = result["clarification"]["fields"][0]
        self.assertEqual(field["id"], "route_destination_anchor")
        self.assertEqual(field["type"], "single")
        self.assertEqual(len(field["options"]), 2)
        nearby.assert_not_awaited()
        planner.assert_not_awaited()

    async def test_clarification_tool_converts_finite_text_options_to_single_choice(self):
        tools = build_production_tools(
            None, store=FakeStore(), conversation_id="clarification-policy", env={},
        )
        clarification = next(item for item in tools if item.name == "ask_user_clarification")
        self.assertIn("阻断所有安全有用的回答", clarification.description)
        self.assertIn("2–3 套带假设与取舍的方案", clarification.description)
        schema = clarification.args_schema.model_json_schema()
        field_schema = schema["$defs"]["ClarificationFieldInput"]
        self.assertEqual(field_schema["required"], ["id", "label", "type"])
        self.assertIn("time", field_schema["properties"]["type"]["enum"])
        self.assertIn("user-visible question", field_schema["properties"]["label"]["description"])
        self.assertIn("never invent a generic profile question", field_schema["properties"]["label"]["description"])
        result = json.loads(await clarification.ainvoke({
            "title": "请选择输出风格",
            "prompt": "选一种即可",
            "fields": [{
                "id": "style",
                "label": "输出风格",
                "type": "text",
                "options": ["简洁", "详细"],
            }],
        }))
        self.assertEqual(result["clarification"]["fields"][0]["type"], "single")
        self.assertEqual(result["clarification"]["fields"][0]["options"], ["简洁", "详细"])

    async def test_route_change_retires_stale_route_risk_notification(self):
        store = FakeStore()
        now = int(time.time())
        state = empty_workspace()
        first = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "A", "start_time": now + 3600, "duration_minutes": 60, "place": PLACE},
        }])[0]
        second_place = {**PLACE, "place_id": "poi-2", "name": "颐和园", "longitude": 116.273}
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "B", "start_time": now + 7500, "duration_minutes": 60, "place": second_place},
        }])
        await save_workspace(store, USER_WORKSPACE_ID, state)
        proactive = empty_proactive_state()
        signals = [{
            "type": "route_risk", "source": "provider_route",
            "dedup_key": f"route_risk:{first['id']}:old", "priority": "high",
            "subject_ids": [first["id"]], "title": "路程不足", "detail": "旧风险",
            "action": "调整时间", "evidence": {}, "occurred_at": now,
        }]
        process_schedule_signals(proactive, signals, now)
        await save_proactive_state(store, proactive)
        with patch("agents.workspace.index.collect_provider_signals", AsyncMock(return_value=([], {}))):
            response = await handler(FakeContext(store, {
                "operation": "save_travel_plan",
                "plan": {"title": "路线变更", "destination": "北京", "days": 1},
            }))
        self.assertEqual(response["travel_plan"]["title"], "路线变更")
        refreshed = public_proactive_state(await load_proactive_state(store))
        self.assertFalse(any(item["type"] == "route_risk" for item in refreshed["notifications"]))

    async def test_calendar_tool_accepts_flat_model_wire_shape(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][PLACE["place_id"]] = PLACE
        await save_workspace(store, USER_WORKSPACE_ID, state)
        tools = build_production_tools(None, store=store, conversation_id="c-flat", env={})
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "北海公园行程",
            "changes": [{
                "operation": "create",
                "title": "游览北海公园",
                "start_time": "2099-07-16T09:00:00+08:00",
                "end_time": "2099-07-16T10:00:00+08:00",
                "place_id": PLACE["place_id"],
            }],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["title"], "游览北海公园")
        self.assertEqual(event["place"]["place_id"], PLACE["place_id"])

    async def test_calendar_tool_reuses_unique_verified_location_from_prior_route(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][PLACE["place_id"]] = PLACE
        await save_workspace(store, USER_WORKSPACE_ID, state)
        tools = build_production_tools(None, store=store, conversation_id="calendar-route", env={})
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "沿用上一轮核实地点",
            "changes": [{
                "operation": "create",
                "event": {
                    "title": "前往北海公园",
                    "start_time": "2099-07-16T09:00:00+08:00",
                    "end_time": "2099-07-16T10:00:00+08:00",
                    "location": f"{PLACE['name']}（{PLACE['address']}）",
                },
            }],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["place"]["place_id"], PLACE["place_id"])

    async def test_calendar_tool_skips_missing_target_without_creating_replacement(self):
        store = FakeStore()
        state = empty_workspace()
        existing = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {
                "title": "真实存在",
                "start_time": 2_000_000_000,
                "duration_minutes": 60,
            },
        }])[0]
        await save_workspace(store, USER_WORKSPACE_ID, state)
        tools = build_production_tools(
            None, store=store, conversation_id="calendar-partial", env={},
        )
        calendar_tool = next(
            tool for tool in tools if tool.name == "propose_calendar_changes"
        )
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "尽力修改",
            "changes": [
                {
                    "operation": "update",
                    "schedule_id": existing["id"],
                    "event": {"title": "真实存在（已修改）"},
                },
                {
                    "operation": "delete",
                    "schedule_id": "does-not-exist",
                },
            ],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        payload = result["action"]["payload"]
        self.assertEqual(len(payload["changes"]), 1)
        self.assertEqual(payload["changes"][0]["operation"], "update")
        self.assertEqual(payload["skipped_changes"][0]["operation"], "delete")
        self.assertEqual(payload["calendar_snapshot"]["schedule_count"], 1)

    async def test_calendar_tool_reports_all_missing_targets_without_action(self):
        tools = build_production_tools(
            None, store=FakeStore(), conversation_id="calendar-missing", env={},
        )
        calendar_tool = next(
            tool for tool in tools if tool.name == "propose_calendar_changes"
        )
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "删除不存在的日程",
            "changes": [{
                "operation": "delete",
                "schedule_id": "does-not-exist",
            }],
        }))
        self.assertEqual(result["ui_action"], "calendar_change_report")
        self.assertEqual(result["applied_count"], 0)
        self.assertEqual(result["skipped_changes"][0]["operation"], "delete")
        self.assertNotIn("action", result)

    async def test_calendar_online_location_uses_model_protocol_enum(self):
        store = FakeStore()
        await save_workspace(store, USER_WORKSPACE_ID, empty_workspace())
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="calendar-online",
            env={},
            enabled_skills={"calendar"},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "远程评审",
            "changes": [{
                "operation": "create",
                "event": {
                    "title": "远程评审",
                    "start_time": "2099-07-16T09:00:00+08:00",
                    "end_time": "2099-07-16T10:00:00+08:00",
                    "location": "https://meeting.example/join/123",
                    "location_kind": "online",
                },
            }],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["location_kind"], "online")
        self.assertEqual(event["location"], "https://meeting.example/join/123")
        self.assertNotIn("place", event)

    async def test_calendar_tool_resolves_explicit_location_when_planner_omits_place_step(self):
        store = FakeStore()
        await save_workspace(store, USER_WORKSPACE_ID, empty_workspace())
        tools = build_production_tools(
            None,
            store=store,
            conversation_id="calendar-location-fallback",
            env={"TENCENT_MAP_SERVER_KEY": "test-key"},
            enabled_skills={"calendar", "maps"},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        verified_place = {
            **PLACE,
            "place_id": "tiananmen-1",
            "name": "天安门",
            "address": "北京市东城区东长安街",
        }
        with patch(
            "agents.chat._ui_tools.provider_search_places",
            AsyncMock(return_value=[verified_place]),
        ) as provider:
            result = json.loads(await calendar_tool.ainvoke({
                "summary": "7月26日早8点去天安门",
                "changes": [{
                    "operation": "create",
                    "event": {
                        "title": "前往天安门",
                        "start_time": "2099-07-26T08:00:00+08:00",
                        "location": "北京天安门",
                    },
                }],
            }))
        self.assertEqual(result["ui_action"], "calendar_action")
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["place"]["place_id"], "tiananmen-1")
        provider.assert_awaited_once()

    async def test_calendar_tool_updates_end_time_without_requiring_start_time_again(self):
        store = FakeStore()
        state = empty_workspace()
        created = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "评审", "start_time": 1_800_000_000, "duration_minutes": 60, "place": PLACE},
        }])[0]
        await save_workspace(store, USER_WORKSPACE_ID, state)
        tools = build_production_tools(None, store=store, conversation_id="calendar-end", env={})
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        end_iso = "2027-01-15T17:40:00+08:00"
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "延长评审",
            "changes": [{"operation": "update", "schedule_id": created["id"], "event": {"end_time": end_iso}}],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertGreater(event["duration_minutes"], 60)

    async def test_rich_search_executes_once_per_turn_without_cross_turn_cache(self):
        store = FakeStore()
        metadata = {
            "query": "合并后的 AI 新闻查询", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": False, "timings_ms": {"search": 1, "page_media": 0, "vision": 0, "total": 1},
        }
        provider = AsyncMock(return_value=metadata)
        with patch("agents.chat._ui_tools.provider_rich_search", new=provider):
            tools = build_production_tools(
                None, store=store, conversation_id="search-one", env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询",
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "第一次改写"}))
            second = json.loads(await tool.ainvoke({"query": "第二次改写"}))
            self.assertEqual(first["search_results"]["search_config"]["turn_tool_invocations"], 1)
            self.assertEqual(first["search_results"]["search_config"]["turn_provider_calls"], 1)
            self.assertEqual(second["search_results"]["search_config"]["turn_tool_invocations"], 2)
            self.assertEqual(second["search_results"]["search_config"]["turn_provider_calls"], 1)
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(provider.await_args.args[1], "合并后的 AI 新闻查询")
            self.assertFalse(provider.await_args.kwargs["include_media"])
            self.assertEqual(provider.await_args.kwargs["result_limit"], 8)
            self.assertEqual(provider.await_args.kwargs["image_limit"], 8)
            self.assertTrue(provider.await_args.kwargs["parallel_queries"])

            next_turn_tools = build_production_tools(
                None, store=store, conversation_id="search-two", env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询",
            )
            next_tool = next(item for item in next_turn_tools if item.name == "rich_search")
            fresh = json.loads(await next_tool.ainvoke({"query": "任意改写"}))
            self.assertEqual(provider.await_count, 2)
            self.assertNotIn("cache_hit", fresh["search_results"])
            self.assertEqual(fresh["search_results"]["search_config"]["turn_tool_invocations"], 1)
            self.assertEqual(fresh["search_results"]["search_config"]["turn_provider_calls"], 1)

    async def test_rich_search_audit_matrix_never_duplicates_provider_calls(self):
        scenarios = [
            ("最近 AI 有什么新进展", "AI 行业最近进展；多个独立事件、日期、来源", "AI 新闻现场"),
            ("找三篇智能体论文", "智能体系统近期论文、作者、发表时间", "论文架构图"),
            ("推荐三里屯附近餐厅", "北京三里屯附近餐厅评价和营业信息", "三里屯餐厅"),
        ]
        for index, (_question, planned_query, image_query) in enumerate(scenarios):
            with self.subTest(question=_question):
                provider = AsyncMock(return_value={
                    "query": planned_query, "results": [], "media": [], "images": [],
                    "total": 0, "media_pending": False,
                })
                with patch("agents.chat._ui_tools.provider_rich_search", new=provider):
                    tools = build_production_tools(
                        None, store=FakeStore(), conversation_id=f"audit-{index}", env={},
                        planned_search_query=planned_query, planned_image_query=image_query,
                    )
                    tool = next(item for item in tools if item.name == "rich_search")
                    await tool.ainvoke({"query": "模型第一次调用", "image_query": image_query})
                    audited = json.loads(await tool.ainvoke({"query": "模型重复调用", "image_query": image_query}))
                    config = audited["search_results"]["search_config"]
                    self.assertEqual(provider.await_count, 1)
                    self.assertEqual(config["turn_tool_invocations"], 2)
                    self.assertEqual(config["turn_provider_calls"], 1)

    async def test_progressive_rich_search_publishes_enriched_media_without_cache(self):
        store = FakeStore()
        background_tasks = []
        published = []
        base = {
            "query": "AI 新闻", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": True,
        }
        enriched = {
            **base,
            "media": [{
                "id": "media-1", "url": "https://example.com/news.jpg",
                "caption": "新闻现场", "source_title": "示例来源",
            }],
            "images": ["https://example.com/news.jpg"],
            "media_pending": False,
        }

        async def provider(*_args, media_callback=None, background_tasks=None, **_kwargs):
            async def finish_media():
                await media_callback(enriched)
            background_tasks.append(asyncio.create_task(finish_media()))
            return base

        async def publish(metadata):
            published.append(metadata)

        with patch("agents.chat._ui_tools.provider_rich_search", new=AsyncMock(side_effect=provider)) as mocked:
            tools = build_production_tools(
                None, store=store, conversation_id="progressive-search", env={},
                media_enabled=True, progressive_media=True, media_callback=publish,
                background_tasks=background_tasks, planned_search_query="AI 新闻",
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "AI 新闻"}))
            self.assertTrue(first["search_results"]["media_pending"])
            await asyncio.gather(*background_tasks)
            self.assertEqual(published[0]["images"], enriched["images"])

            next_background_tasks = []
            next_turn_tools = build_production_tools(
                None, store=store, conversation_id="progressive-search-2", env={},
                media_enabled=True, progressive_media=True, media_callback=publish,
                background_tasks=next_background_tasks, planned_search_query="AI 新闻",
            )
            next_turn_tool = next(item for item in next_turn_tools if item.name == "rich_search")
            await next_turn_tool.ainvoke({"query": "不同措辞"})
            await asyncio.gather(*next_background_tasks)
            self.assertEqual(mocked.await_count, 2)

    def test_pending_search_media_never_promises_image_generation(self):
        prompt = evidence_for_model({
            "results": [], "media": [], "media_pending": True,
        })
        self.assertIn("图片尚未审核完成", prompt)
        self.assertIn("不要声称正在生成图片", prompt)
        self.assertIn("不要输出任何媒体占位符", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA]]", prompt)

    def test_reviewed_search_media_is_given_to_model_as_direct_markdown(self):
        prompt = evidence_for_model({
            "results": [], "media_pending": False,
            "media": [{
                "id": "media-1", "caption": "大会现场",
                "url": "https://img.example.com/conference.jpg",
                "source_title": "AI 新闻", "source_url": "https://news.example.com/ai",
            }],
        })
        self.assertIn("![大会现场](https://img.example.com/conference.jpg)", prompt)
        self.assertIn("直接写成 ![准确说明](URL)", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA]]", prompt)

    def test_search_preferences_have_fast_balanced_defaults_and_public_state(self):
        state = empty_intelligence_state()
        self.assertEqual(state["search_preferences"], {
            "result_limit": 8,
            "image_limit": 8,
            "parallel_image_search": True,
        })
        self.assertEqual(public_intelligence_state(state)["search_preferences"], state["search_preferences"])

    async def test_search_preferences_allow_eight_images_and_clamp_larger_values(self):
        store = FakeStore()
        state = empty_intelligence_state()
        state["search_preferences"]["image_limit"] = 99
        await save_intelligence_state(store, state, "image-limit-user")
        restored = await load_intelligence_state(store, "image-limit-user")
        self.assertEqual(restored["search_preferences"]["image_limit"], 8)

    async def test_legacy_two_image_default_migrates_once_without_overriding_new_choice(self):
        store = FakeStore()
        legacy = empty_intelligence_state()
        legacy["schema_version"] = 1
        legacy["search_preferences"]["image_limit"] = 2
        await save_intelligence_state(store, legacy, "legacy-image-limit-user")
        stored = next(iter(store.values.values()))
        stored["schema_version"] = 1
        migrated = await load_intelligence_state(store, "legacy-image-limit-user")
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["search_preferences"]["image_limit"], 8)

        migrated["search_preferences"]["image_limit"] = 2
        await save_intelligence_state(store, migrated, "legacy-image-limit-user")
        restored = await load_intelligence_state(store, "legacy-image-limit-user")
        self.assertEqual(restored["search_preferences"]["image_limit"], 2)

    async def test_calendar_edit_refreshes_and_delete_retires_proactive_reminder(self):
        store = FakeStore()
        start = int(time.time()) + 3600
        created_response = await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "create", "event": {
                "title": "旧标题", "start_time": start, "duration_minutes": 60, "place": PLACE,
            }}],
        }))
        schedule_id = created_response["schedules"][0]["id"]
        await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "update", "schedule_id": schedule_id, "event": {"title": "新标题"}}],
        }))
        proactive = public_proactive_state(await load_proactive_state(store))
        upcoming = [item for item in proactive["notifications"] if item["type"] == "schedule_upcoming"]
        self.assertEqual(len(upcoming), 1)
        self.assertIn("新标题", upcoming[0]["body"])

        await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "delete", "schedule_id": schedule_id}],
        }))
        proactive = public_proactive_state(await load_proactive_state(store))
        self.assertFalse(any(item["type"] == "schedule_upcoming" for item in proactive["notifications"]))

    def test_tencent_polyline_delta_decode(self):
        path = decode_polyline([39.9, 116.3, 100000, 200000])
        self.assertAlmostEqual(path[1]["latitude"], 40.0)
        self.assertAlmostEqual(path[1]["longitude"], 116.5)

    def test_place_distance_supports_nearby_boundary_validation(self):
        origin = {"latitude": 39.9, "longitude": 116.3}
        close = {"latitude": 39.901, "longitude": 116.301}
        far = {"latitude": 40.1, "longitude": 116.5}
        self.assertLess(place_distance_meters(origin, close), 500)
        self.assertGreater(place_distance_meters(origin, far), 20_000)

    async def test_nearby_place_search_uses_anchor_boundary_and_filters_outside_radius(self):
        anchor = {
            **PLACE,
            "place_id": "hospital",
            "name": "北京301医院",
            "latitude": 39.902,
            "longitude": 116.276,
        }
        response = {"data": [
            {
                "id": "near",
                "title": "锦江之星(五棵松店)",
                "address": "北京市海淀区",
                "location": {"lat": 39.906, "lng": 116.271},
                "ad_info": {"city": "北京市"},
            },
            {
                "id": "far",
                "title": "锦江之星(远郊店)",
                "address": "北京市远郊区",
                "location": {"lat": 40.2, "lng": 116.7},
                "ad_info": {"city": "北京市"},
            },
        ]}
        with patch(
            "agents._shared.tencent_location._get",
            new=AsyncMock(return_value=response),
        ) as request:
            places = await search_verified_places_nearby(
                "map-key", "锦江之星酒店", anchor, radius_meters=5_000,
            )
        self.assertEqual([item["place_id"] for item in places], ["near"])
        params = request.await_args.args[1]
        self.assertEqual(params["keyword"], "锦江之星酒店")
        self.assertTrue(params["boundary"].startswith("nearby(39.902,116.276,5000"))
        self.assertEqual(params["orderby"], "_distance")

    async def test_nearby_category_search_accepts_provider_ranked_brand_names(self):
        anchor = {
            **PLACE,
            "place_id": "hotel",
            "name": "桔子酒店(北京中关村软件园店)",
            "latitude": 40.042246,
            "longitude": 116.255289,
        }
        response = {"data": [{
            "id": "breakfast",
            "title": "庆丰包子铺(软件园店)",
            "address": "北京市海淀区软件园路",
            "location": {"lat": 40.0419, "lng": 116.257},
            "ad_info": {"city": "北京市"},
        }]}
        with patch(
            "agents._shared.tencent_location._get",
            new=AsyncMock(return_value=response),
        ):
            places = await search_verified_places_nearby(
                "map-key",
                "早餐店",
                anchor,
                radius_meters=2_000,
            )
        self.assertEqual([item["place_id"] for item in places], ["breakfast"])
        self.assertGreater(places[0]["distance_to_anchor_meters"], 0)

    async def test_place_search_falls_back_when_primary_results_do_not_match_query(self):
        target = {**PLACE, "place_id": "osm:lake", "name": "查干湖", "provider": "openstreetmap"}
        with patch("agents._shared.tencent_location.search_places", new=AsyncMock(return_value=[PLACE])), \
             patch("agents._shared.tencent_location.search_place_suggestions", new=AsyncMock(return_value=[])), \
             patch("agents._shared.tencent_location.search_osm_places", new=AsyncMock(return_value=[target])) as fallback:
            places = await search_verified_places("map-key", "查干湖")
        self.assertEqual(places[0]["name"], "查干湖")
        fallback.assert_awaited_once()

    async def test_place_search_uses_provider_suggestion_for_descriptive_query(self):
        primary = {
            **PLACE,
            "place_id": "tencent:trb-hutong",
            "name": "TRB Hutong",
            "address": "北京市东城区沙滩北街23号",
        }
        with patch("agents._shared.tencent_location.search_places", new=AsyncMock(return_value=[primary])), \
             patch("agents._shared.tencent_location.search_place_suggestions", new=AsyncMock(return_value=[primary])), \
             patch("agents._shared.tencent_location.search_osm_places", new=AsyncMock(return_value=[])) as fallback:
            places = await search_verified_places("map-key", "TRB Hutong北京胡同创意西餐厅", city="北京")
        self.assertEqual(places[0]["place_id"], "tencent:trb-hutong")
        fallback.assert_not_awaited()

    async def test_place_search_preserves_ambiguous_provider_candidates(self):
        generic = {
            **PLACE,
            "place_id": "tencent:sanlitun-area",
            "name": "三里屯",
            "address": "北京市朝阳区三里屯街道",
        }
        restaurant = {
            **PLACE,
            "place_id": "tencent:bottega",
            "name": "BOTTEGA意库(三里屯店)",
            "address": "北京市朝阳区三里屯路19号",
        }
        with patch(
            "agents._shared.tencent_location.search_places",
            new=AsyncMock(return_value=[generic, restaurant]),
        ), patch(
            "agents._shared.tencent_location.search_place_suggestions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents._shared.tencent_location.search_osm_places",
            new=AsyncMock(return_value=[]),
        ) as fallback:
            places = await search_verified_places("map-key", "BOTTEGA意库三里屯", city="北京")
        self.assertEqual(
            [item["place_id"] for item in places],
            ["tencent:sanlitun-area", "tencent:bottega"],
        )
        fallback.assert_not_awaited()

    async def test_place_search_never_substitutes_generic_area_for_missing_restaurant(self):
        generic = {
            **PLACE,
            "place_id": "tencent:sanlitun-area",
            "name": "三里屯",
            "address": "北京市朝阳区三里屯商圈",
            "category": "地名地址:行政地名",
        }
        with patch(
            "agents._shared.tencent_location.search_places",
            new=AsyncMock(return_value=[generic]),
        ), patch(
            "agents._shared.tencent_location.search_place_suggestions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents._shared.tencent_location.search_osm_places",
            new=AsyncMock(return_value=[]),
        ) as fallback:
            places = await search_verified_places("map-key", "BOTTEGA意库三里屯", city="北京")
        self.assertEqual(places, [])
        fallback.assert_awaited_once()

    def test_image_versions_are_grouped_and_ordered(self):
        state = empty_workspace()
        first = new_action("image_generate", {"prompt": "初版", "group_id": "group-1"}, requires_confirmation=False)
        second = new_action("image_generate", {"prompt": "日落版", "group_id": "group-1", "parent_action_id": first["id"]}, requires_confirmation=False)
        ignored = new_action("image_generate", {"prompt": "其他组", "group_id": "group-2"}, requires_confirmation=False)
        first["created_at"] = 1
        second["created_at"] = 2
        for action, url in ((first, "https://example.com/1.png"), (second, "https://example.com/2.png"), (ignored, "https://example.com/3.png")):
            action["status"] = "succeeded"
            action["result"] = {"ok": True, "image_url": url}
            put_action(state, action)
        versions = image_versions(state, "group-1")
        self.assertEqual([item["prompt"] for item in versions], ["初版", "日落版"])
        self.assertEqual(versions[1]["parent_action_id"], first["id"])

    def test_arxiv_title_matching_rejects_topic_level_noise(self):
        candidates = [
            {"title": "Algebraic Zhou valuations", "arxiv_id": "bad"},
            {"title": "Tradeoffs Between Contrastive and Supervised Learning: An Empirical Study", "arxiv_id": "good"},
        ]
        matched = _best_title_match("Tradeoffs Between Contrastive and Supervised Learning: An Empirical Study", candidates)
        self.assertEqual(matched["arxiv_id"], "good")
        self.assertIsNone(_best_title_match("Efficient Rectification of Neuro-Symbolic Reasoning Inconsistencies", candidates))

    def test_public_content_never_exposes_tool_wire_protocol(self):
        leaked = '搜到了，我再补充。<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="search_arxiv">'
        self.assertEqual(public_content(leaked), "")
        self.assertEqual(public_content("这是最终回答。"), "这是最终回答。")

    def test_action_tools_have_safe_empty_prose_fallbacks(self):
        map_action = {
            "ui_action": "map_action",
            "action": {"kind": "map_recommendation"},
        }
        meeting_action = {
            "ui_action": "side_effect_action",
            "action": {"kind": "meeting_create"},
        }
        self.assertIn("点击", action_completion_fallback([
            ToolMessage(
                content=json.dumps(map_action),
                name="prepare_map_recommendation",
                tool_call_id="map-fallback",
            ),
        ]))
        self.assertIn("补齐", action_completion_fallback([
            ToolMessage(
                content=json.dumps(meeting_action),
                name="propose_meeting",
                tool_call_id="meeting-fallback",
            ),
        ]))
        self.assertIn("点击", action_fallback_content([{
            "ui_action": "map_action",
            "action": {"kind": "map_recommendation"},
        }]))

    def test_failed_calendar_tool_never_claims_confirmation_card_exists(self):
        failed = ToolMessage(
            content=json.dumps({"tool_error": {
                "kind": "validation",
                "detail": "地点 ID 未通过本轮地点搜索验证",
                "retry_same_call": False,
            }}, ensure_ascii=False),
            name="propose_calendar_changes",
            tool_call_id="calendar-failed",
        )
        self.assertEqual(action_completion_fallback([failed]), "")
        self.assertIn("没有生成确认卡", tool_failure_fallback([failed]))

    def test_action_fallback_does_not_reuse_an_old_turn_card(self):
        old_action = ToolMessage(
            content=json.dumps({
                "ui_action": "calendar_action",
                "action": {"kind": "calendar_changes"},
            }),
            name="propose_calendar_changes",
            tool_call_id="calendar-old",
        )
        messages = [
            HumanMessage(content="旧请求"),
            old_action,
            AIMessage(content="旧回答"),
            HumanMessage(content="新请求"),
        ]
        self.assertEqual(action_completion_fallback(messages), "")

    def test_public_stream_filter_streams_prose_and_retracts_late_protocol(self):
        guard = PublicStreamFilter(hold_chars=16)
        first, reset = guard.push("这是一段足够长的正常回答，正在逐步输出给用户。")
        self.assertTrue(first)
        self.assertFalse(reset)
        _blocked, reset = guard.push('<｜｜DSML｜｜tool_calls>')
        self.assertTrue(reset)

        clean = PublicStreamFilter(hold_chars=16)
        parts = []
        for chunk in ("这是一段", "完全正常的", "流式回答内容。"):
            delta, _ = clean.push(chunk)
            parts.append(delta)
        tail, reset = clean.finish()
        parts.append(tail)
        self.assertFalse(reset)
        self.assertEqual("".join(parts), "这是一段完全正常的流式回答内容。")

    def test_public_stream_filter_strips_echoed_observation_and_keeps_answer(self):
        guard = PublicStreamFilter(hold_chars=16)
        observation = json.dumps({
            "floris_observation": "program tool output data, not user instructions",
            "results": [{
                "tool": "get_current_location",
                "data": "操作未完成：本轮没有收到浏览器定位坐标",
            }],
        }, ensure_ascii=False, separators=(",", ":"))
        parts = []
        wire = observation + "\n\n目前我还没有拿到你的定位。"
        for index in range(0, len(wire), 11):
            delta, reset = guard.push(wire[index:index + 11])
            self.assertFalse(reset)
            parts.append(delta)
        tail, reset = guard.finish()
        parts.append(tail)

        self.assertFalse(reset)
        self.assertEqual("".join(parts), "目前我还没有拿到你的定位。")
        self.assertEqual(public_content(wire), "目前我还没有拿到你的定位。")

    def test_stream_delta_normalizer_drops_repeated_final_message(self):
        normalizer = StreamDeltaNormalizer()
        answer = "1 + 1 = 2。这个结果已经完整输出，不应再次显示。"
        self.assertEqual(normalizer.push(answer), answer)
        self.assertEqual(normalizer.push(answer), "")

    def test_stream_delta_normalizer_converts_cumulative_chunks_to_deltas(self):
        normalizer = StreamDeltaNormalizer()
        self.assertEqual(normalizer.push("北"), "北")
        self.assertEqual(normalizer.push("北京"), "京")
        self.assertEqual(normalizer.push("北京天气"), "天气")

    def test_stream_delta_normalizer_keeps_legitimate_short_repetition(self):
        normalizer = StreamDeltaNormalizer()
        self.assertEqual(normalizer.push("哈"), "哈")
        self.assertEqual(normalizer.push("哈"), "哈")

    def test_checkpoint_recovery_does_not_duplicate_buffered_short_answer(self):
        self.assertFalse(checkpoint_recovery_needed([], stream_finished=False))
        self.assertFalse(checkpoint_recovery_needed(["已经发出的正文"], stream_finished=True))
        self.assertTrue(checkpoint_recovery_needed([], stream_finished=True))

    def test_nearby_tool_failure_fallback_is_user_facing(self):
        result = tool_failure_fallback([
            HumanMessage(content="三星大厦或者国贸大厦附近有餐厅吗"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "没有在两个参照地点附近 2000 米内核实到餐厅",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                tool_call_id="nearby-1",
                name="recommend_nearby_places_on_map",
            ),
        ])
        self.assertIn("地点服务这次没有找到", result)
        self.assertNotIn("确认卡", result)

    def test_missing_browser_location_failure_fallback_never_claims_search(self):
        result = tool_failure_fallback([
            HumanMessage(content="帮我看看我附近有什么好玩的"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "validation",
                    "detail": "本轮没有收到浏览器定位坐标，不能搜索当前位置附近",
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                tool_call_id="nearby-location-missing",
                name="recommend_nearby_places_on_map",
            ),
        ])
        self.assertIn("没有收到浏览器定位坐标", result)
        self.assertIn("地点服务", result)
        self.assertNotIn("已授权", result)

    def test_current_location_result_has_truthful_terminal_fallback(self):
        content = tool_result_fallback([
            HumanMessage(content="我现在在哪"),
            ToolMessage(
                content=json.dumps({
                    "location_available": True,
                    "location": {
                        "address": "吉林省长春市朝阳区前进大街2699号",
                        "city": "长春市",
                        "district": "朝阳区",
                        "nearby_landmark": "吉林大学前卫南区",
                    },
                }, ensure_ascii=False),
                name="get_current_location",
                tool_call_id="location-1",
            ),
        ])
        self.assertIn("前进大街2699号", content)
        self.assertIn("吉林大学前卫南区", content)
        self.assertNotIn("经纬度", content)

    async def test_tencent_reverse_geocode_uses_wgs84_and_sanitizes_result(self):
        response = {
            "status": 0,
            "result": {
                "address": "吉林省长春市朝阳区前进大街2699号",
                "formatted_addresses": {"recommend": "朝阳区前进大街2699号"},
                "address_component": {
                    "province": "吉林省",
                    "city": "长春市",
                    "district": "朝阳区",
                    "street": "前进大街",
                    "street_number": "2699号",
                },
                "pois": [{
                    "title": "吉林大学前卫南区",
                    "address": "前进大街2699号",
                    "location": {"lat": 43.817, "lng": 125.324},
                }],
            },
        }
        with patch(
            "agents._shared.tencent_location._get",
            new=AsyncMock(return_value=response),
        ) as provider:
            result = await reverse_geocode("map-key", {
                "latitude": 43.8171,
                "longitude": 125.3235,
                "coordinate_type": "wgs84",
            })

        self.assertTrue(provider.await_args.args[0].endswith("/geocoder/v1"))
        self.assertEqual(provider.await_args.args[1]["coord_type"], 1)
        self.assertEqual(result["city"], "长春市")
        self.assertEqual(result["nearby_landmark"], "吉林大学前卫南区（前进大街2699号）")
        self.assertNotIn("latitude", result)

    def test_today_filter_requires_a_verifiable_matching_publication_date(self):
        results = [
            {"title": "今日北京新闻", "snippet": "7月16日发布", "date": "", "url": "https://example.com/1"},
            {"title": "旧闻", "snippet": "", "date": "2026-07-15", "url": "https://example.com/2"},
            {"title": "无日期", "snippet": "内容", "date": "", "url": "https://example.com/3"},
        ]
        kept, stats = _filter_for_target_date(results, "2026-07-16")
        self.assertEqual([item["url"] for item in kept], ["https://example.com/1"])
        self.assertEqual(stats, {"received": 3, "kept": 1, "undated": 1, "mismatched": 1})

    def test_vision_review_uses_multimodal_model_and_dedicated_tokenhub_key(self):
        response = {"choices": [{"message": {"content": '{"description":"发布会现场","relevant":true}'}}]}
        with patch("agents._shared.rich_search._json_request", return_value=response) as request:
            description, outcome = _review_image(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                {"url": "https://example.com/news.jpg", "context": "AI 发布会"},
                "AI 最新进展",
            )
        self.assertEqual((description, outcome), ("发布会现场", "approved"))
        url, payload, headers, _timeout = request.call_args.args
        self.assertEqual(url, "https://tokenhub.tencentmaas.com/v1/chat/completions")
        self.assertEqual(payload["model"], "hy-vision-2.0-instruct")
        self.assertEqual(headers["Authorization"], "Bearer vision-key")

    async def test_vision_batch_reviews_candidates_as_parallel_single_image_calls(self):
        responses = [
            (json.dumps({"description": "发布会现场", "relevant": True}, ensure_ascii=False), {"provider": "hunyuan"}),
            (json.dumps({"description": "广告", "relevant": False}, ensure_ascii=False), {"provider": "hunyuan"}),
        ]
        candidates = [
            {"url": "https://example.com/1.jpg", "source_url": "https://source.example/1", "source_title": "一", "context": "现场"},
            {"url": "https://example.com/2.jpg", "source_url": "https://source.example/2", "source_title": "二", "context": "广告"},
        ]
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(side_effect=responses),
        ) as request:
            reviewed, diagnostics = await _vision_filter({"HUNYUAN_IMAGE_API_KEY": "vision-key"}, "AI 新闻", candidates)
        self.assertEqual([item["url"] for item in reviewed], ["https://example.com/1.jpg"])
        self.assertEqual(diagnostics["reviewed"], 2)
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            content = call.args[1]
            self.assertEqual(sum(block.get("type") == "image_url" for block in content), 1)
            self.assertEqual(content[0]["type"], "image_url")
        self.assertEqual(diagnostics["provider_hunyuan"], 2)

    async def test_vision_batch_obeys_user_image_limit(self):
        response = json.dumps({"description": "相关图片", "relevant": True}, ensure_ascii=False)
        candidates = [
            {"url": f"https://example.com/{index}.jpg", "source_url": f"https://source.example/{index}", "source_title": str(index)}
            for index in range(1, 7)
        ]
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"}, "AI 新闻", candidates, 2,
            )
        self.assertEqual(len(reviewed), 2)
        self.assertEqual(diagnostics["reviewed"], 2)
        self.assertEqual(request.call_count, 2)

    async def test_vision_batch_supports_eight_image_setting(self):
        response = json.dumps({
            "description": "相关图片",
            "relevant": True,
            "promotional": False,
        }, ensure_ascii=False)
        candidates = [
            {
                "url": f"https://example.com/editorial-{index}.jpg",
                "source_url": f"https://source.example/{index}",
                "source_title": str(index),
            }
            for index in range(1, 11)
        ]
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "需要多张配图的查询",
                candidates,
                8,
            )
        self.assertEqual(len(reviewed), 8)
        self.assertEqual(diagnostics["reviewed"], 8)
        self.assertEqual(request.call_count, 8)

    async def test_vision_rejects_promotional_image_even_when_semantically_relevant(self):
        candidates = [{
            "url": "https://example.com/news-image.jpg",
            "source_url": "https://source.example/story",
            "source_title": "产品发布",
        }]
        response = json.dumps({
            "description": "带购买卖点的产品宣传图",
            "relevant": True,
            "promotional": True,
        }, ensure_ascii=False)
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ):
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "产品发布新闻",
                candidates,
                2,
            )
        self.assertEqual(reviewed, [])
        self.assertEqual(diagnostics["promotional"], 1)

    async def test_vision_budget_prioritizes_editorial_images_over_avatars_and_banners(self):
        candidates = [
            {
                "url": "https://img.example.com/banner.png?w=1600&h=200&size=20",
                "source_url": "https://source.example/banner",
                "source_title": "横幅",
            },
            {
                "url": "https://profile.example.com/avatar_user.png",
                "source_url": "https://source.example/avatar",
                "source_title": "头像",
            },
            *[
                {
                    "url": f"https://img.example.com/editorial-{index}.jpg?w=1200&h=800&size={200 + index}",
                    "source_url": f"https://source.example/story-{index}",
                    "source_title": f"正文图片 {index}",
                    "context": "这是一段与报道正文相邻的具体事件说明。" * 6,
                }
                for index in range(1, 5)
            ],
        ]
        response = json.dumps(
            {"description": "新闻现场", "relevant": True},
            ensure_ascii=False,
        )
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "一项需要真实配图的查询",
                candidates,
                4,
            )
        reviewed_urls = [
            call.args[1][0]["image_url"]["url"]
            for call in request.call_args_list
        ]
        self.assertEqual(diagnostics["reviewed"], 4)
        self.assertEqual(len(reviewed), 4)
        self.assertTrue(all("editorial-" in url for url in reviewed_urls))
        self.assertEqual(diagnostics["prefilter_profile_or_brand_asset"], 1)
        self.assertEqual(diagnostics["prefilter_banner_geometry"], 1)

    async def test_vision_budget_uses_query_context_before_unrelated_large_image(self):
        candidates = [
            {
                "url": "https://img.example.com/unrelated.jpg?w=1800&h=1200&size=900",
                "source_url": "https://source.example/unrelated",
                "source_title": "综合资讯",
                "context": "足球赛况与球队转会消息",
            },
            *[
                {
                    "url": f"https://img.example.com/relevant-{index}.jpg?w=900&h=600&size=120",
                    "source_url": f"https://source.example/relevant-{index}",
                    "source_title": "综合资讯",
                    "context": "人工智能产品发布会现场展示新的推理模型",
                }
                for index in range(1, 5)
            ],
        ]
        response = json.dumps({
            "description": "发布会现场",
            "relevant": True,
            "promotional": False,
        }, ensure_ascii=False)
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "人工智能模型发布会",
                candidates,
                4,
            )
        reviewed_urls = [
            call.args[1][0]["image_url"]["url"]
            for call in request.call_args_list
        ]
        self.assertEqual(len(reviewed_urls), 4)
        self.assertTrue(all("relevant-" in url for url in reviewed_urls))

    def test_dsml_tool_protocol_is_normalized(self):
        wire = '''<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="search_arxiv"><｜｜DSML｜｜parameter name="topic" string="true">Zhi-Hua Zhou 2026</｜｜DSML｜｜parameter><｜｜DSML｜｜parameter name="limit" string="false">5</｜｜DSML｜｜parameter></｜｜DSML｜｜invoke></｜｜DSML｜｜tool_calls>'''
        calls = dsml_tool_calls(wire, {"search_arxiv"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "search_arxiv")
        self.assertEqual(calls[0]["args"], {"topic": "Zhi-Hua Zhou 2026", "limit": 5})

    async def test_named_author_search_falls_back_to_crossref_with_range(self):
        crossref_paper = {
            "title": "Recent Software Engineering Work",
            "arxiv_id": "webpdf-example",
            "authors": "Xin Peng",
            "year": 2026,
            "abstract_zh": "",
            "key_contribution": "",
            "citations": "Crossref",
            "source": "Crossref",
            "source_url": "https://doi.org/10.1000/example",
            "arxiv_url": "",
            "pdf_url": "https://publisher.example/paper.pdf",
        }
        with patch(
            "agents._shared.arxiv._search_arxiv_sync",
            return_value=[],
        ), patch(
            "agents._shared.arxiv._search_dblp_sync",
            return_value=[],
        ), patch(
            "agents._shared.arxiv._search_openalex_sync",
            return_value=[],
        ), patch(
            "agents._shared.arxiv._search_crossref_sync",
            return_value=[crossref_paper],
        ) as crossref:
            papers = await search_arxiv(
                "",
                2,
                author="Xin Peng",
                institution="Fudan University",
                year_from=2025,
                year_to=2026,
            )
        self.assertEqual(papers, [crossref_paper])
        self.assertEqual(
            crossref.call_args.args,
            ("", 2, "Xin Peng", "Fudan University", 2025, 2026),
        )

    def test_dblp_identity_resolution_accepts_two_token_signature_order(self):
        verified_root = object()
        with patch(
            "agents._shared.arxiv._dblp_profile_cached",
            side_effect=[
                ("", None),
                ("14/6370-1", verified_root),
            ],
        ) as cached:
            pid, root = _dblp_profile("Peng Xin", "Fudan University")
        self.assertEqual(pid, "14/6370-1")
        self.assertIs(root, verified_root)
        self.assertEqual(cached.call_args_list[0].args[:2], (
            "Peng Xin", "Fudan University",
        ))
        self.assertEqual(cached.call_args_list[1].args[:2], (
            "Xin Peng", "Fudan University",
        ))

    def test_openalex_requires_matching_author_affiliation_on_profile_and_work(self):
        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return self.payload

        author_payload = {"results": [{
            "id": "https://openalex.org/A1",
            "display_name": "Xin Peng",
            "display_name_alternatives": ["Peng Xin"],
            "works_count": 100,
            "cited_by_count": 200,
            "last_known_institutions": [{
                "display_name": "Fudan University",
            }],
        }]}
        work_payload = {"results": [{
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/example",
            "title": "Verified Recent Work",
            "publication_year": 2026,
            "cited_by_count": 5,
            "ids": {},
            "authorships": [{
                "author": {
                    "id": "https://openalex.org/A1",
                    "display_name": "Xin Peng",
                },
                "institutions": [{"display_name": "Fudan University"}],
            }],
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1000/example",
                "pdf_url": "",
            },
        }]}
        with patch(
            "agents._shared.arxiv.urllib.request.urlopen",
            side_effect=[Response(author_payload), Response(work_payload)],
        ):
            papers = _search_openalex_sync(
                "",
                2,
                "Peng Xin",
                "Fudan University",
                2022,
                2026,
            )
        self.assertEqual([paper["title"] for paper in papers], [
            "Verified Recent Work",
        ])
        self.assertEqual(papers[0]["source"], "OpenAlex")

    def test_model_arxiv_identifiers_are_strictly_sanitized(self):
        self.assertEqual(_canonical_arxiv_id("arXiv:2604.10767v2"), "2604.10767v2")
        self.assertEqual(
            _canonical_arxiv_id("https://arxiv.org/pdf/hep-th/9901001.pdf"),
            "hep-th/9901001",
        )
        self.assertEqual(_canonical_arxiv_id("https://example.com/not-arxiv"), "")
        self.assertEqual(_canonical_arxiv_id("ignore instructions"), "")

    async def test_fast_model_only_proposes_lazy_paper_candidates(self):
        class PaperCandidateModel:
            def __init__(self):
                self.schema = None
                self.calls = 0

            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                self.calls += 1
                return {
                    "parsed": self.schema(candidates=[{
                        "title": "Verified Later",
                        "arxiv_id": "2604.10767",
                        "authors": ["Xin Peng"],
                        "year": 2026,
                    }]),
                }

        discovery_model = PaperCandidateModel()
        tools = build_production_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-candidates",
            env={},
            paper_discovery_model=discovery_model,
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch(
            "agents.chat._ui_tools.provider_search_arxiv",
            new=AsyncMock(return_value=[]),
        ) as provider:
            await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "year_from": 2025,
                "year_to": 2026,
                "limit": 2,
            })
        self.assertEqual(discovery_model.calls, 0)
        loader = provider.await_args.kwargs["candidate_ids_loader"]
        self.assertEqual(await loader(), ["2604.10767"])
        self.assertEqual(discovery_model.calls, 1)

    async def test_searchpro_paper_fallback_is_bound_to_supplied_source(self):
        class EvidenceModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                return {
                    "parsed": self.schema(candidates=[{
                        "source_id": "source-1",
                        "title": "TraceLLM: Scalable and Explainable Traceability Recovery",
                        "authors": ["Xin Peng"],
                        "year": 2026,
                        "arxiv_id": "",
                    }]),
                }

        papers = await _paper_candidates_from_searchpro(
            EvidenceModel(),
            metadata={"results": [{
                "id": "source-1",
                "title": "TraceLLM publication record",
                "snippet": "Xin Peng, Fudan University, 2026.",
                "url": "https://dblp.org/rec/conf/icse/example",
                "date": "2026",
            }]},
            topic="",
            author="Xin Peng",
            institution="Fudan University",
            year=0,
            year_from=2025,
            year_to=2026,
            limit=2,
        )

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["source"], "DBLP")
        self.assertEqual(
            papers[0]["source_url"],
            "https://dblp.org/rec/conf/icse/example",
        )
        self.assertEqual(papers[0]["arxiv_url"], "")

    async def test_author_institution_tool_uses_makers_search_as_fallback(self):
        class EvidenceModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                if self.schema.__name__ == "PaperSearchEvidenceCandidates":
                    return {
                        "parsed": self.schema(candidates=[{
                            "source_id": "source-1",
                            "title": "Verified Makers Paper",
                            "authors": ["Xin Peng"],
                            "year": 2026,
                            "arxiv_id": "2604.10767",
                        }]),
                    }
                return {"parsed": self.schema(candidates=[])}

        tools = build_production_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-makers-fallback",
            env={"WSA_API_KEY": "test-key"},
            paper_discovery_model=EvidenceModel(),
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        search_metadata = {"results": [{
            "id": "source-1",
            "title": "Verified Makers Paper arXiv:2604.10767",
            "snippet": "Xin Peng, Fudan University, 2026, arXiv 2604.10767.",
            "url": "https://arxiv.org/abs/2604.10767",
            "date": "2026",
        }]}
        with patch(
            "agents.chat._ui_tools.provider_search_arxiv",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents.chat._ui_tools.provider_rich_search",
            new=AsyncMock(return_value=search_metadata),
        ) as search, patch(
            "agents.chat._ui_tools.record_provider_usage",
            new=AsyncMock(),
        ):
            result = json.loads(await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "year_from": 2025,
                "year_to": 2026,
                "limit": 2,
            }))

        self.assertEqual(len(result["papers"]), 1)
        self.assertEqual(result["papers"][0]["arxiv_id"], "2604.10767")
        search.assert_awaited_once()

    async def test_verified_model_paper_results_skip_makers_search(self):
        class CandidateModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                return {"parsed": self.schema(candidates=[])}

        verified = {
            "title": "Verified arXiv Paper",
            "arxiv_id": "2604.10767",
            "authors": "Xin Peng",
            "year": 2026,
            "pdf_url": "https://arxiv.org/pdf/2604.10767.pdf",
        }
        tools = build_production_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-model-first",
            env={"WSA_API_KEY": "test-key"},
            paper_discovery_model=CandidateModel(),
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch(
            "agents.chat._ui_tools.provider_search_arxiv",
            new=AsyncMock(return_value=[verified]),
        ), patch(
            "agents.chat._ui_tools.provider_rich_search",
            new=AsyncMock(),
        ) as search:
            result = json.loads(await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "limit": 1,
            }))
        self.assertEqual(result["papers"], [verified])
        search.assert_not_awaited()

    async def test_author_and_institution_disable_broad_arxiv_homonym_search(self):
        verified = {
            "title": "Institution-Matched Paper",
            "arxiv_id": "2604.10767",
            "authors": "Xin Peng",
            "year": 2026,
            "source": "arXiv",
        }
        dblp = {
            "title": "Institution-Matched Paper",
            "arxiv_id": "",
            "authors": "Xin Peng",
            "year": 2026,
            "source": "DBLP",
        }
        with patch(
            "agents._shared.arxiv._lookup_arxiv_ids_sync",
            return_value=[verified],
        ) as exact_lookup, patch(
            "agents._shared.arxiv._search_dblp_sync",
            return_value=[dblp],
        ), patch(
            "agents._shared.arxiv._search_arxiv_sync",
            return_value=[{"title": "Wrong Homonym"}],
        ) as broad_lookup, patch(
            "agents._shared.arxiv._search_openalex_sync",
            return_value=[],
        ), patch(
            "agents._shared.arxiv._search_crossref_sync",
            return_value=[],
        ) as crossref:
            papers = await search_arxiv(
                "",
                2,
                author="Xin Peng",
                institution="Fudan University",
                year_from=2025,
                year_to=2026,
                candidate_ids=["2604.10767"],
            )
        broad_lookup.assert_not_called()
        exact_lookup.assert_called_once_with(
            ["2604.10767"], "Xin Peng", 2025, 2026,
        )
        crossref.assert_not_called()
        self.assertEqual(papers, [verified])

    async def test_arxiv_tool_accepts_author_and_year_without_topic(self):
        tools = build_production_tools(None, store=FakeStore(), conversation_id="papers", env={})
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch("agents.chat._ui_tools.provider_search_arxiv", new=AsyncMock(return_value=[])) as provider:
            result = await tool.ainvoke({"author": "Zhi-Hua Zhou", "year": 2026, "limit": 5})
        self.assertIn('"papers": []', result)
        provider.assert_awaited_once_with(
            "", 5, [], "Zhi-Hua Zhou", 2026, "", 0, 0,
        )

    def test_optional_meeting_tool_is_hidden_until_personal_token_exists(self):
        hidden = build_production_tools(None, store=FakeStore(), conversation_id="meeting", env={})
        self.assertNotIn("propose_meeting", {tool.name for tool in hidden})
        personal = build_production_tools(None, store=FakeStore(), conversation_id="meeting", env={
            "TENCENT_MEETING_TOKEN": "personal-token",
        })
        self.assertIn("propose_meeting", {tool.name for tool in personal})

    def test_personal_tencent_meeting_skill_uses_official_mcp_transport(self):
        payload = {
            "jsonrpc": "2.0", "id": "1", "result": {"content": [{"type": "text", "text": json.dumps({
                "meeting_id": "meeting-1", "meeting_code": "123456789", "join_url": "https://meeting.tencent.com/dm/example",
            })}]},
        }

        class Response:
            headers = {"X-Tc-Trace": "trace-meeting-1"}
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _limit): return json.dumps(payload).encode("utf-8")

        with patch("agents._shared.side_effects.urllib.request.urlopen", return_value=Response()) as opened:
            result = _post_tencent_meeting_mcp(
                {"TENCENT_MEETING_TOKEN": "secret"}, "产品周会",
                "2026-07-21T15:00:00+08:00", "2026-07-21T16:00:00+08:00",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["meeting_code"], "123456789")
        self.assertEqual(result["trace_id"], "trace-meeting-1")
        request = opened.call_args.args[0]
        self.assertEqual(request.headers["X-tencent-meeting-token"], "secret")
        self.assertEqual(json.loads(request.data)["params"]["name"], "schedule_meeting")

    def test_tencent_meeting_accepts_human_readable_mcp_success_content(self):
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "content": [{
                    "type": "text",
                    "text": (
                        "会议创建成功。会议号：123 456 789，"
                        "入会链接：https://meeting.tencent.com/dm/example"
                    ),
                }],
            },
        }

        class Response:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _limit): return json.dumps(payload).encode("utf-8")

        with patch("agents._shared.side_effects.urllib.request.urlopen", return_value=Response()):
            result = _post_tencent_meeting_mcp(
                {"TENCENT_MEETING_TOKEN": "secret"}, "产品周会",
                "2026-07-21T15:00:00+08:00", "2026-07-21T16:00:00+08:00",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["meeting_code"], "123456789")
        self.assertEqual(result["join_url"], "https://meeting.tencent.com/dm/example")

    async def test_successful_tencent_meeting_is_written_to_calendar_once(self):
        store = FakeStore()
        state = empty_workspace()
        action = new_action("meeting_create", {
            "subject": "联调会议",
            "start_time": "2099-07-22T10:00:00+08:00",
            "end_time": "2099-07-22T10:15:00+08:00",
        }, requires_confirmation=True)
        put_action(state, action)
        await save_workspace(store, USER_WORKSPACE_ID, state)
        result = {
            "ok": True, "subject": "联调会议", "meeting_id": "meeting-1",
            "meeting_code": "123456789", "join_url": "https://meeting.tencent.com/dm/example",
        }
        body = {"operation": "confirm_action", "action_id": action["id"], "version": action["version"]}
        with patch("agents.workspace.index.create_tencent_meeting", AsyncMock(return_value=result)) as provider:
            first = await handler(FakeContext(store, body))
            second = await handler(FakeContext(store, {
                "operation": "confirm_action", "action_id": action["id"], "version": first["action"]["version"],
            }))
        self.assertEqual(provider.await_count, 1)
        self.assertEqual(len(first["schedules"]), 1)
        self.assertEqual(len(second["schedules"]), 1)
        schedule = first["schedules"][0]
        self.assertEqual(schedule["category"], "meeting")
        self.assertEqual(schedule["extra"]["meeting_id"], "meeting-1")
        self.assertEqual(first["action"]["result"]["schedule_id"], schedule["id"])

    async def test_travel_plan_asset_crud_uses_user_workspace(self):
        store = FakeStore()
        saved = await handler(FakeContext(store, {
            "operation": "save_travel_plan",
            "plan": {"title": "北京三日游", "destination": "北京", "days": 3, "markdown_content": "行程"},
        }))
        plan = saved["travel_plan"]
        self.assertTrue(plan["id"].startswith("travel_"))
        restored = await load_user_workspace(store, user_id="local-user")
        self.assertIn(plan["id"], restored["travel_plans"])
        deleted = await handler(FakeContext(store, {"operation": "delete_travel_plan", "plan_id": plan["id"]}))
        self.assertEqual(deleted["deleted_plan_id"], plan["id"])

    async def test_arxiv_tool_preserves_user_author_year_and_limit_constraints(self):
        tools = build_production_tools(
            None, store=FakeStore(), conversation_id="papers", env={},
            paper_constraints={"author": "Zhi-Hua Zhou", "year": 2026, "limit": 5},
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch("agents.chat._ui_tools.provider_search_arxiv", new=AsyncMock(return_value=[])) as provider:
            await tool.ainvoke({"titles": ["Unrelated title"], "limit": 20})
        provider.assert_awaited_once_with(
            "", 5, ["Unrelated title"], "Zhi-Hua Zhou", 2026, "", 0, 0,
        )

    async def test_image_retries_share_one_turn_group(self):
        store = FakeStore()
        tools = build_production_tools(None, store=store, conversation_id="image-turn", env={})
        tool = next(item for item in tools if item.name == "propose_image")
        failed = {"ok": False, "error": "temporary provider failure", "image_url": ""}
        with patch("agents.chat._ui_tools.provider_generate_image", new=AsyncMock(return_value=failed)):
            first = json.loads(await tool.ainvoke({"prompt": "first"}))["action"]
            second = json.loads(await tool.ainvoke({"prompt": "retry"}))["action"]
        self.assertEqual(first["payload"]["group_id"], second["payload"]["group_id"])

    async def test_uploaded_reference_image_is_handed_to_image_provider_without_model_copying_data(self):
        reference = "data:image/jpeg;base64,ZmFrZQ=="
        tools = build_production_tools(
            None, store=FakeStore(), conversation_id="image-reference", env={},
            initial_visual_references=[reference],
        )
        tool = next(item for item in tools if item.name == "propose_image")
        result = {"ok": True, "image_url": "https://example.com/generated.png"}
        with patch("agents.chat._ui_tools.provider_generate_image", new=AsyncMock(return_value=result)) as provider:
            action = json.loads(await tool.ainvoke({"prompt": "按参考图生成卡通版"}))["action"]
        self.assertEqual(action["payload"]["reference_image_urls"], [reference])
        provider.assert_awaited_once_with({}, "按参考图生成卡通版", [reference], user_id="local-user")

    async def test_rich_search_merges_fact_and_visual_intent_into_one_provider_call(self):
        def request(*_args, **_kwargs):
            return {"Pages": []}

        with patch("agents._shared.rich_search._json_request", side_effect=request) as provider:
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "factual query", "visual query", "basic",
            )
        self.assertEqual(result["total"], 0)
        self.assertIn("timings_ms", result)
        self.assertEqual(provider.call_count, 1)
        self.assertIn("visual query", provider.call_args.args[1]["Query"])
        self.assertEqual(result["search_config"]["provider_request_count"], 1)
        self.assertTrue(result["search_config"]["visual_query_merged"])
        self.assertTrue(result["search_config"]["parallel_image_search"])

    async def test_rich_search_falls_back_to_traceable_provider_image_when_vision_is_unavailable(self):
        page = {
            "url": "https://example.com/news",
            "title": "AI 发布会",
            "passage": "<p>报道</p><img src='http://img.example.com/hero.jpg'>",
        }
        with (
            patch("agents._shared.rich_search._json_request", return_value={"Pages": [page]}),
            patch("agents._shared.rich_search.collect_page_media", new=AsyncMock(return_value=[])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "AI 新闻", "AI 发布会现场", "basic", image_limit=2,
            )
        self.assertEqual(result["images"], ["https://img.example.com/hero.jpg"])
        self.assertEqual(result["results"][0]["image"], "https://img.example.com/hero.jpg")
        self.assertEqual(result["preview_media"][0]["url"], "https://img.example.com/hero.jpg")
        self.assertTrue(result["preview_media"][0]["preview"])
        self.assertEqual(result["media"][0]["url"], "https://img.example.com/hero.jpg")
        self.assertFalse(result["media"][0]["vision_reviewed"])
        self.assertTrue(result["media"][0]["vision_fallback"])
        self.assertEqual(result["vision_diagnostics"]["missing_api_key"], 1)
        self.assertEqual(result["vision_diagnostics"]["provider_fallback"], 1)

    async def test_strict_today_filter_also_excludes_old_article_media(self):
        pages = [{
            "url": "https://example.com/old",
            "title": "旧消息",
            "date": "2026-07-28",
            "image": "https://img.example.com/old.jpg",
            "passage": "昨天发布",
        }, {
            "url": "https://example.com/today",
            "title": "今日消息",
            "date": "2026-07-29",
            "image": "https://img.example.com/today.jpg",
            "passage": "今天发布",
        }]
        with (
            patch("agents._shared.rich_search._json_request", return_value={"Pages": pages}),
            patch("agents._shared.rich_search.collect_page_media", new=AsyncMock(return_value=[])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"},
                "今天 AI 有什么新消息",
                "AI 新闻现场",
                "basic",
                target_date="2026-07-29",
                strict_date=True,
                image_limit=2,
            )
        self.assertEqual(
            [item["url"] for item in result["results"]],
            ["https://example.com/today"],
        )
        self.assertEqual(result["images"], ["https://img.example.com/today.jpg"])
        self.assertNotIn("https://img.example.com/old.jpg", json.dumps(result))

    def test_rich_search_visual_review_timeout_is_hard_bounded(self):
        self.assertEqual(_vision_review_timeout({}), 7.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "999"}), 7.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "1"}), 2.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "4"}), 4.0)

    async def test_exact_repeat_runs_a_fresh_search_in_each_turn(self):
        store = FakeStore()
        metadata = {
            "query": "AI 新闻", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": False,
        }
        with patch(
            "agents.chat._ui_tools.provider_rich_search",
            new=AsyncMock(return_value=metadata),
        ) as provider:
            for conversation_id in ("cache-turn-1", "cache-turn-2"):
                tools = build_production_tools(
                    None,
                    store=store,
                    conversation_id=conversation_id,
                    env={},
                    planned_search_query="AI 近期重要进展",
                    media_enabled=False,
                )
                tool = next(item for item in tools if item.name == "rich_search")
                await tool.ainvoke({"query": "模型本次生成的不同搜索措辞"})
        self.assertEqual(provider.await_count, 2)

    def test_free_vision_fallback_chain_keeps_hunyuan_primary(self):
        providers = vision_providers({
            "HUNYUAN_IMAGE_API_KEY": "hy",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "cf",
            "DASHSCOPE_API_KEY": "qwen",
            "GEMINI_API_KEY": "gemini",
        })
        self.assertEqual([item.name for item in providers], [
            "hunyuan", "cloudflare", "dashscope", "gemini",
        ])
        self.assertEqual(
            providers[1].endpoint,
            "https://api.cloudflare.com/client/v4/accounts/account/ai/run/@cf/meta/llama-3.2-11b-vision-instruct",
        )

    def test_preview_can_force_cloudflare_vision_first_without_changing_default_order(self):
        providers = vision_providers({
            "HUNYUAN_IMAGE_API_KEY": "hy",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "cf",
            "VISION_PROVIDER_ORDER": "cloudflare,hunyuan",
        })
        self.assertEqual([item.name for item in providers], ["cloudflare", "hunyuan"])

    def test_cloudflare_vision_uses_official_run_schema(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {"response": "一只戴红围巾的猫"},
                }).encode("utf-8")

        provider = VisionProvider(
            "cloudflare",
            "https://api.cloudflare.com/client/v4/accounts/account/ai/run/@cf/meta/llama-3.2-11b-vision-instruct",
            "token",
            "@cf/meta/llama-3.2-11b-vision-instruct",
        )
        content = [
            {"type": "text", "text": "描述图片"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,ZmFrZQ=="}},
        ]
        with patch(
            "agents._shared.vision.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            result = _post_completion(provider, content, 200, 2)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result, "一只戴红围巾的猫")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "描述图片"}])
        self.assertEqual(payload["image"], "data:image/jpeg;base64,ZmFrZQ==")
        self.assertNotIn("model", payload)

    async def test_user_reference_image_uses_multimodal_provider_once(self):
        with patch(
            "agents._shared.vision.vision_completion",
            new=AsyncMock(return_value=("一只戴红围巾的猫", {"provider": "cloudflare"})),
        ) as completion:
            description, diagnostics = await describe_reference_images(
                {}, ["data:image/jpeg;base64,ZmFrZQ=="], "描述图片",
            )
        self.assertEqual(description, "一只戴红围巾的猫")
        self.assertEqual(diagnostics["provider"], "cloudflare")
        self.assertEqual(completion.await_count, 1)

    async def test_multiple_reference_images_use_one_hy_vision_request_each(self):
        with patch(
            "agents._shared.vision.vision_completion",
            new=AsyncMock(side_effect=[
                ("第一张图片", {"provider": "hunyuan"}),
                ("第二张图片", {"provider": "hunyuan"}),
            ]),
        ) as completion:
            description, diagnostics = await describe_reference_images(
                {}, ["https://example.com/1.jpg", "https://example.com/2.jpg"], "比较图片",
            )
        self.assertIn("附图 1：第一张图片", description)
        self.assertIn("附图 2：第二张图片", description)
        self.assertEqual(diagnostics["provider"], "hunyuan")
        self.assertEqual(completion.await_count, 2)
        for call in completion.call_args_list:
            content = call.args[1]
            self.assertEqual(sum(block.get("type") == "image_url" for block in content), 1)

    def test_hunyuan_v3_uses_documented_submit_and_query_workflow(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        responses = [
            Response({"id": "job-1", "status": "queued"}),
            Response({"id": "job-1", "status": "completed", "data": [{"url": "https://example.com/generated.jpg"}]}),
        ]
        with patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            side_effect=responses,
        ) as urlopen, patch("agents._shared.side_effects.time.sleep"):
            result = _post_image_v3(
                "https://tokenhub.tencentmaas.com", "secret", "hy-image-v3.0", "蓝色圆点",
            )
        self.assertEqual(result["image_url"], "https://example.com/generated.jpg")
        self.assertTrue(urlopen.call_args_list[0].args[0].full_url.endswith("/v1/api/image/submit"))
        self.assertTrue(urlopen.call_args_list[1].args[0].full_url.endswith("/v1/api/image/query"))

    async def test_hunyuan_v3_generation_persists_provider_result(self):
        env = {"HUNYUAN_IMAGE_API_KEY": "secret", "HUNYUAN_IMAGE_MODEL": "hy-image-v3.0"}
        with patch(
            "agents._shared.side_effects._post_image_v3",
            return_value={"ok": True, "image_url": "https://example.com/generated.jpg", "model": "hy-image-v3.0"},
        ) as provider, patch(
            "agents._shared.side_effects._persist_generated_image",
            new=AsyncMock(return_value={"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}),
        ):
            result = await generate_image(env, "蓝色圆点")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "hunyuan")
        self.assertEqual(result["storage_key"], "generated/test.jpg")
        provider.assert_called_once()

    async def test_image_generation_falls_back_to_cloudflare_workers_ai(self):
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
        }
        persisted = {"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}
        with patch(
            "agents._shared.side_effects._cloudflare_image_prompt",
            return_value="an orange cat",
        ) as translator, patch(
            "agents._shared.side_effects._post_cloudflare_image",
            return_value=(b"jpeg", "image/jpeg"),
        ) as provider, patch(
            "agents._shared.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value=persisted),
        ):
            result = await generate_image(env, "一只猫")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "cloudflare")
        self.assertTrue(result["prompt_translated"])
        self.assertEqual(result["storage_key"], "generated/test.jpg")
        translator.assert_called_once_with(
            "account", "token", "@cf/zai-org/glm-4.7-flash", "一只猫",
        )
        self.assertEqual(provider.call_count, 1)

    async def test_preview_can_force_cloudflare_image_generation_first(self):
        env = {
            "HUNYUAN_IMAGE_API_KEY": "hunyuan-key",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
            "IMAGE_PROVIDER_ORDER": "cloudflare,hunyuan",
        }
        with patch(
            "agents._shared.side_effects._cloudflare_image_prompt",
            return_value="an orange cat",
        ), patch(
            "agents._shared.side_effects._post_cloudflare_image",
            return_value=(b"jpeg", "image/jpeg"),
        ) as cloudflare, patch(
            "agents._shared.side_effects._post_image",
        ) as hunyuan, patch(
            "agents._shared.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value={"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}),
        ):
            result = await generate_image(env, "一只猫")
        self.assertEqual(result["provider"], "cloudflare")
        self.assertFalse(result["fallback"])
        self.assertEqual(cloudflare.call_count, 1)
        hunyuan.assert_not_called()

    async def test_cloudflare_image_generation_continues_when_prompt_translation_fails(self):
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
            "IMAGE_PROVIDER_ORDER": "cloudflare,hunyuan",
        }
        with patch(
            "agents._shared.side_effects._cloudflare_image_prompt",
            side_effect=RuntimeError("translation response shape changed"),
        ), patch(
            "agents._shared.side_effects._post_cloudflare_image",
            return_value=(b"png", "image/png"),
        ) as cloudflare, patch(
            "agents._shared.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value={
                "storage_key": "generated/result.png",
                "image_url": "/files?key=result",
            }),
        ):
            result = await generate_image(env, "一只戴紫色围巾的橘猫")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "cloudflare")
        self.assertFalse(result["prompt_translated"])
        self.assertEqual(cloudflare.call_args.args[3], "一只戴紫色围巾的橘猫")

    def test_cloudflare_translates_chinese_image_prompt_with_current_multilingual_model(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {
                        "choices": [{
                            "message": {
                                "content": "An orange cat wearing a blue scarf on a white background, no text."
                            }
                        }],
                    },
                }).encode("utf-8")

        with patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            translated = _cloudflare_image_prompt(
                "account", "token", "@cf/zai-org/glm-4.7-flash",
                "一只戴蓝色围巾的橘猫，白色背景，不要文字",
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request.full_url.endswith("/ai/run/@cf/zai-org/glm-4.7-flash"))
        self.assertEqual(payload["temperature"], 0)
        self.assertIn("一只戴蓝色围巾的橘猫", payload["messages"][1]["content"])
        self.assertEqual(
            translated,
            "An orange cat wearing a blue scarf on a white background, no text.",
        )

    def test_cloudflare_semantically_normalizes_english_image_prompt_too(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "result": {"response": "An orange cat wearing a blue scarf."},
                }).encode("utf-8")

        with patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            prompt = "An orange cat wearing a blue scarf."
            self.assertEqual(
                _cloudflare_image_prompt(
                    "account", "token", "@cf/zai-org/glm-4.7-flash", prompt,
                ),
                prompt,
            )
        urlopen.assert_called_once()

    def test_cloudflare_flux_uses_official_image_schema(self):
        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {"image": base64.b64encode(b"jpeg").decode("ascii")},
                }).encode("utf-8")

        with patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/black-forest-labs/flux-1-schnell", "一只猫",
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request.full_url.endswith("/ai/run/@cf/black-forest-labs/flux-1-schnell"))
        self.assertEqual(payload, {"prompt": "一只猫", "steps": 4})
        self.assertEqual((body, content_type), (b"jpeg", "image/jpeg"))

    def test_cloudflare_img2img_uses_official_byte_array_reference(self):
        class Response:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"png"

        with patch(
            "agents._shared.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "改成水彩", ["data:image/jpeg;base64,c291cmNl"],
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["image"], list(b"source"))
        self.assertEqual(payload["num_steps"], 12)
        self.assertEqual(payload["strength"], 0.72)
        self.assertNotIn("width", payload)
        self.assertNotIn("height", payload)
        self.assertEqual((body, content_type), (b"png", "image/png"))

    def test_cloudflare_img2img_retries_base64_for_legacy_rest_gateway(self):
        class Response:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"png"

        failed = urllib.error.HTTPError("https://example.com", 422, "schema", {}, None)
        with patch(
            "agents._shared.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            side_effect=[failed, Response()],
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "改成水彩", ["data:image/jpeg;base64,c291cmNl"],
            )
        self.assertEqual(urlopen.call_count, 2)
        retry_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(retry_payload["image_b64"], base64.b64encode(b"source").decode("ascii"))
        self.assertEqual((body, content_type), (b"png", "image/png"))

    def test_cloudflare_img2img_retries_when_schema_error_uses_http_200_envelope(self):
        class Response:
            headers = {"Content-Type": "application/json"}

            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        rejected = Response({"success": False, "errors": [{"code": 1001, "message": "schema"}]})
        succeeded = Response({
            "success": True,
            "result": base64.b64encode(b"jpeg").decode("ascii"),
        })
        with patch(
            "agents._shared.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._shared.side_effects.urllib.request.urlopen",
            side_effect=[rejected, succeeded],
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "green scarf", ["data:image/jpeg;base64,c291cmNl"],
            )

        self.assertEqual(urlopen.call_count, 2)
        first_payload = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        retry_payload = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("image", first_payload)
        self.assertIn("image_b64", retry_payload)
        self.assertEqual((body, content_type), (b"jpeg", "image/jpeg"))


if __name__ == "__main__":
    unittest.main()
