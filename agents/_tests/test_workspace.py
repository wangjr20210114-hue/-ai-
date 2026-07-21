from __future__ import annotations

import asyncio
import unittest
import json
import ast
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents.chat._capability_plan import (
    media_enabled_for_plan,
    parse_capability_plan,
    plan_capabilities,
    next_required_tool,
    required_tool_for_plan,
    required_tools_for_plan,
)
from agents.chat._followups import parse_followups
from agents.chat._history import bounded_history
from agents.chat._calendar_context import calendar_context
from agents.chat._ui_tools import build_production_tools
from agents.chat._protocol import PublicStreamFilter, dsml_tool_calls, public_content, public_error
from agents.messages.index import handler as messages_handler
from agents._shared.side_effects import _meeting_payload, _meeting_result, _meeting_signature, _post_tencent_meeting_mcp, generate_image
from agents._shared.vision import describe_reference_images, vision_providers
from agents._shared.auth import require_user, scoped_conversation_id
from agents._shared.rich_search import (
    _filter_for_target_date,
    _parse_pages,
    _review_image,
    _vision_filter,
    evidence_for_model,
    rich_search as run_rich_search,
)
from agents._shared.arxiv import _best_title_match
from agents._shared.tencent_location import decode_polyline, search_verified_places
from agents._shared.workspace import (
    USER_WORKSPACE_ID,
    apply_calendar_changes,
    begin_action_execution,
    empty_workspace,
    image_versions,
    load_user_workspace,
    load_workspace,
    new_action,
    normalize_schedule,
    put_action,
    save_workspace,
    finish_provider_call,
    recover_stale_actions,
    start_provider_call,
    verify_action_snapshot,
)
from agents._shared.proactive import (
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
    propose_memory,
    prune_automatic_memories,
    public_intelligence_state,
    record_feedback,
    record_usage,
    rollback_memory,
    usage_summary,
)
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


class FlakyPlannerModel:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        content = "not-json" if self.calls == 1 else json.dumps({
            "needs_web_search": True,
            "needs_rich_answer": True,
            "needs_images": True,
            "search_query": "故宫历史",
            "image_query": "故宫建筑",
        }, ensure_ascii=False)
        return SimpleNamespace(content=content)


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
    def test_personal_runtime_uses_one_fixed_owner_and_raw_conversation_id(self):
        ctx = SimpleNamespace(request=FakeRequest({}), conversation_id="conversation-personal")
        self.assertEqual(require_user(ctx)["user_id"], USER_WORKSPACE_ID)
        self.assertEqual(require_user(ctx)["roles"], ["owner"])
        self.assertEqual(scoped_conversation_id(ctx, USER_WORKSPACE_ID), "conversation-personal")

    def test_long_history_is_trimmed_at_human_boundary(self):
        messages = [SimpleNamespace(type="human", content=f"q{index}") if index % 3 == 0
                    else SimpleNamespace(type="ai", content=f"a{index}") for index in range(60)]
        trimmed = bounded_history(messages, limit=20)
        self.assertLessEqual(len(trimmed), 20)
        self.assertEqual(trimmed[0].type, "human")
        self.assertEqual(trimmed[-1].content, "a59")

    async def test_capability_planner_retries_invalid_json(self):
        model = FlakyPlannerModel()
        plan = await plan_capabilities(model, "能给我讲讲故宫的历史吗")
        self.assertEqual(model.calls, 2)
        self.assertTrue(plan["needs_web_search"])
        self.assertTrue(plan["needs_images"])
        self.assertEqual(plan["image_query"], "故宫建筑")

    async def test_capability_planner_receives_filtered_memory_context(self):
        model = AsyncMock()
        model.ainvoke.return_value = SimpleNamespace(content=json.dumps({"needs_web_search": False}))
        await plan_capabilities(model, "帮我规划旅行", "- preference.travel: 喜欢安静的博物馆")
        system_prompt = model.ainvoke.await_args.args[0][0]["content"]
        self.assertIn("喜欢安静的博物馆", system_prompt)
        self.assertIn("不得把姓名、联系方式", system_prompt)

    async def test_message_restore_keeps_rich_search_metadata(self):
        metadata = {"total": 1, "results": [{"title": "故宫", "url": "https://example.com"}], "media": []}
        messages = [
            {"type": "human", "content": "故宫历史", "id": "u1"},
            {"type": "tool", "content": json.dumps({"ui_action": "rich_search_results", "search_results": metadata})},
            {"type": "ai", "content": "## 故宫历史", "id": "a1"},
        ]
        langgraph_store = FakeStore()
        await langgraph_store.aput(
            ("yuanbao_message_meta_v1", "restore-rich"),
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
        module = ast.parse((Path(__file__).parents[1] / "chat" / "index.py").read_text(encoding="utf-8"))
        prompt_node = next(
            node.value for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in node.targets)
        )
        prompt = ast.literal_eval(prompt_node)
        rendered = prompt.format(
            now="2026-07-15 12:00:00 UTC+08:00",
            capability_plan='{"needs_places": true}',
            calendar_context='[{"id":"cal-live"}]',
            reference_image_context="无",
        )
        self.assertIn("2026-07-15", rendered)

    def test_provider_errors_are_safe_and_actionable(self):
        raw = "Error code: 400 - Model ID must include provider prefix; type=invalid_request"
        message = public_error(raw)
        self.assertIn("模型配置", message)
        self.assertNotIn("provider prefix", message)
        self.assertNotIn("invalid_request", message)

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

    def test_semantic_web_search_makes_media_available_without_keyword_rules(self):
        self.assertTrue(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_rich_answer": False,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": False,
            "needs_rich_answer": False,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_rich_answer": True,
            "needs_images": True,
        }, 0))

    def test_searchpro_html_passage_exposes_provider_article_image(self):
        pages = _parse_pages({"Response": {"Pages": [{
            "url": "https://news.example/item",
            "title": "大会新闻",
            "passage": "<p>正文</p><img src='http://qqpublic.qpic.cn/news.jpg' width='700'>",
        }]}}, 8)
        self.assertEqual(pages[0]["image"], "http://qqpublic.qpic.cn/news.jpg")

    def test_temporal_policy_is_derived_after_capability_planning(self):
        source = (Path(__file__).parents[1] / "chat" / "index.py").read_text(encoding="utf-8")
        planned = source.index("capability_plan = await plan_capabilities")
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

    def test_follow_up_parser_accepts_only_three_unique_questions(self):
        self.assertEqual(
            parse_followups('```json\n["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？", "多余问题？"]\n```'),
            ["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？"],
        )
        self.assertEqual(parse_followups("不是 JSON"), [])


    def test_tencent_meeting_result_normalizes_official_shape(self):
        result = _meeting_result(
            {"meeting_number": 1, "meeting_info_list": [{
                "meeting_id": "m-1", "meeting_code": "123456789",
                "join_url": "https://meeting.example/join", "subject": "评审会",
            }]},
            "评审会",
            "2026-07-17T09:00:00+08:00",
        )
        self.assertEqual(result["meeting_id"], "m-1")
        self.assertEqual(result["meeting_code"], "123456789")
        self.assertEqual(result["join_url"], "https://meeting.example/join")

    def test_tencent_meeting_signature_and_payload_follow_official_contract(self):
        signature = _meeting_signature(
            "AKIDEXAMPLE", "secret-key", "88080", "1572168600", '{"userid":"tester"}',
        )
        self.assertEqual(
            signature,
            "ZWY3YTFlMTgyMmFmYWU4OWJhMTQ1OWQ2NzQ2OGNkZjAxZTJlZTEzZjMxZDhhNWU4MTFjZDFmZTZhMTA5NGJhMw==",
        )
        payload = _meeting_payload(
            {"TENCENT_MEETING_USER_ID": "tester", "TENCENT_MEETING_INSTANCE_ID": "1"},
            "评审会", "2026-07-18T09:00:00+08:00", "2026-07-18T10:00:00+08:00",
        )
        self.assertEqual(payload["type"], 0)
        self.assertEqual(int(payload["end_time"]) - int(payload["start_time"]), 3600)

    def test_rich_search_handoff_uses_standard_markdown(self):
        metadata = {
            "results": [{"source": "wsa", "title": "故宫", "snippet": "明清宫殿", "url": "https://example.com/palace"}],
            "media": [{"caption": "故宫太和殿建筑", "url": "https://cdn.example.com/palace.jpg"}],
        }
        evidence = evidence_for_model(metadata)
        self.assertIn("![故宫太和殿建筑](https://cdn.example.com/palace.jpg)", evidence)
        self.assertNotIn("[[image:", evidence)
        self.assertNotIn("[[card:", evidence)

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
        self.assertFalse(restored["preferences"]["enabled"])
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
                "start_time": "2026-07-16T09:00:00+08:00",
                "end_time": "2026-07-16T10:00:00+08:00",
                "place_id": PLACE["place_id"],
            }],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["title"], "游览北海公园")
        self.assertEqual(event["place"]["place_id"], PLACE["place_id"])

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

    async def test_rich_search_executes_once_per_turn_and_reuses_persistent_cache(self):
        store = FakeStore()
        metadata = {
            "query": "合并后的 AI 新闻查询", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": False, "timings_ms": {"search": 1, "page_media": 0, "vision": 0, "total": 1},
        }
        provider = AsyncMock(return_value=metadata)
        with patch("agents.chat._ui_tools.provider_rich_search", new=provider):
            tools = build_production_tools(
                None, store=store, conversation_id="search-one", env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询", search_cache_ttl_seconds=3600,
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "第一次改写"}))
            second = json.loads(await tool.ainvoke({"query": "第二次改写"}))
            self.assertEqual(first, second)
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(provider.await_args.args[1], "合并后的 AI 新闻查询")
            self.assertFalse(provider.await_args.kwargs["include_media"])
            self.assertEqual(provider.await_args.kwargs["result_limit"], 8)
            self.assertEqual(provider.await_args.kwargs["image_limit"], 2)
            self.assertTrue(provider.await_args.kwargs["parallel_queries"])

            next_turn_tools = build_production_tools(
                None, store=store, conversation_id="search-two", env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询", search_cache_ttl_seconds=3600,
            )
            next_tool = next(item for item in next_turn_tools if item.name == "rich_search")
            cached = json.loads(await next_tool.ainvoke({"query": "任意改写"}))
            self.assertEqual(provider.await_count, 1)
            self.assertTrue(cached["search_results"]["cache_hit"])

    async def test_progressive_rich_search_publishes_and_caches_enriched_media(self):
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
                search_cache_identity="progressive-media-test",
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "AI 新闻"}))
            self.assertTrue(first["search_results"]["media_pending"])
            await asyncio.gather(*background_tasks)
            self.assertEqual(published[0]["images"], enriched["images"])

            cached_tools = build_production_tools(
                None, store=store, conversation_id="progressive-search-2", env={},
                media_enabled=True, progressive_media=True, media_callback=publish,
                background_tasks=[], planned_search_query="AI 新闻",
                search_cache_identity="progressive-media-test",
            )
            cached_tool = next(item for item in cached_tools if item.name == "rich_search")
            cached = json.loads(await cached_tool.ainvoke({"query": "不同措辞"}))
            self.assertTrue(cached["search_results"]["cache_hit"])
            self.assertEqual(cached["search_results"]["images"], enriched["images"])
            self.assertEqual(mocked.await_count, 1)

    def test_search_preferences_have_fast_balanced_defaults_and_public_state(self):
        state = empty_intelligence_state()
        self.assertEqual(state["search_preferences"], {
            "result_limit": 8,
            "image_limit": 2,
            "parallel_image_search": True,
        })
        self.assertEqual(public_intelligence_state(state)["search_preferences"], state["search_preferences"])

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

    async def test_place_search_falls_back_when_primary_results_do_not_match_query(self):
        target = {**PLACE, "place_id": "osm:lake", "name": "查干湖", "provider": "openstreetmap"}
        with patch("agents._shared.tencent_location.search_places", new=AsyncMock(return_value=[PLACE])), \
             patch("agents._shared.tencent_location.search_osm_places", new=AsyncMock(return_value=[target])) as fallback:
            places = await search_verified_places("map-key", "查干湖")
        self.assertEqual(places[0]["name"], "查干湖")
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
                {"HUNYUAN_API_KEY": "text-plan", "HUNYUAN_IMAGE_API_KEY": "vision-key"},
                {"url": "https://example.com/news.jpg", "context": "AI 发布会"},
                "AI 最新进展",
            )
        self.assertEqual((description, outcome), ("发布会现场", "approved"))
        url, payload, headers, _timeout = request.call_args.args
        self.assertEqual(url, "https://tokenhub.tencentmaas.com/v1/chat/completions")
        self.assertEqual(payload["model"], "hy-vision-2.0-instruct")
        self.assertEqual(headers["Authorization"], "Bearer vision-key")

    async def test_vision_batch_reviews_multiple_candidates_in_one_model_call(self):
        response = json.dumps({"items": [
            {"index": 1, "description": "发布会现场", "relevant": True},
            {"index": 2, "description": "广告", "relevant": False},
        ]}, ensure_ascii=False)
        candidates = [
            {"url": "https://example.com/1.jpg", "source_url": "https://source.example/1", "source_title": "一", "context": "现场"},
            {"url": "https://example.com/2.jpg", "source_url": "https://source.example/2", "source_title": "二", "context": "广告"},
        ]
        with patch(
            "agents._shared.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "cloudflare"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter({"HUNYUAN_IMAGE_API_KEY": "vision-key"}, "AI 新闻", candidates)
        self.assertEqual([item["url"] for item in reviewed], ["https://example.com/1.jpg"])
        self.assertEqual(diagnostics["reviewed"], 2)
        self.assertEqual(request.call_count, 1)
        content = request.call_args.args[1]
        self.assertEqual(sum(block.get("type") == "image_url" for block in content), 2)
        self.assertEqual(diagnostics["provider_cloudflare"], 1)

    async def test_vision_batch_obeys_user_image_limit(self):
        response = json.dumps({"items": [
            {"index": index, "description": f"相关图片 {index}", "relevant": True}
            for index in range(1, 7)
        ]}, ensure_ascii=False)
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
        self.assertEqual(diagnostics["reviewed"], 4)
        self.assertEqual(request.call_count, 1)

    def test_dsml_tool_protocol_is_normalized(self):
        wire = '''<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="search_arxiv"><｜｜DSML｜｜parameter name="topic" string="true">Zhi-Hua Zhou 2026</｜｜DSML｜｜parameter><｜｜DSML｜｜parameter name="limit" string="false">5</｜｜DSML｜｜parameter></｜｜DSML｜｜invoke></｜｜DSML｜｜tool_calls>'''
        calls = dsml_tool_calls(wire, {"search_arxiv"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "search_arxiv")
        self.assertEqual(calls[0]["args"], {"topic": "Zhi-Hua Zhou 2026", "limit": 5})

    async def test_arxiv_tool_accepts_author_and_year_without_topic(self):
        tools = build_production_tools(None, store=FakeStore(), conversation_id="papers", env={})
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch("agents.chat._ui_tools.provider_search_arxiv", new=AsyncMock(return_value=[])) as provider:
            result = await tool.ainvoke({"author": "Zhi-Hua Zhou", "year": 2026, "limit": 5})
        self.assertIn('"papers": []', result)
        provider.assert_awaited_once_with("", 5, [], "Zhi-Hua Zhou", 2026)

    def test_optional_meeting_tool_is_hidden_until_all_credentials_exist(self):
        hidden = build_production_tools(None, store=FakeStore(), conversation_id="meeting", env={})
        self.assertNotIn("propose_meeting", {tool.name for tool in hidden})
        ready = build_production_tools(None, store=FakeStore(), conversation_id="meeting", env={
            "TENCENT_MEETING_SECRET_ID": "id",
            "TENCENT_MEETING_SECRET_KEY": "key",
            "TENCENT_MEETING_APP_ID": "app",
            "TENCENT_MEETING_SDK_ID": "sdk",
            "TENCENT_MEETING_USER_ID": "user",
        })
        self.assertIn("propose_meeting", {tool.name for tool in ready})
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
        request = opened.call_args.args[0]
        self.assertEqual(request.headers["X-tencent-meeting-token"], "secret")
        self.assertEqual(json.loads(request.data)["params"]["name"], "schedule_meeting")

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
        provider.assert_awaited_once_with("", 5, ["Unrelated title"], "Zhi-Hua Zhou", 2026)

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

    async def test_rich_search_uses_provider_article_image_when_vision_is_unavailable(self):
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
        self.assertFalse(result["media"][0]["vision_reviewed"])
        self.assertEqual(result["vision_diagnostics"]["provider_image_fallback"], 1)

    async def test_exact_repeat_reuses_persistent_rich_search_cache(self):
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
                    search_cache_identity="最近AI有什么新进展",
                    media_enabled=False,
                )
                tool = next(item for item in tools if item.name == "rich_search")
                await tool.ainvoke({"query": "模型本次生成的不同搜索措辞"})
        self.assertEqual(provider.await_count, 1)

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

    async def test_image_generation_falls_back_to_cloudflare_workers_ai(self):
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
        }
        persisted = {"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}
        with patch(
            "agents._shared.side_effects._post_cloudflare_image",
            return_value=(b"jpeg", "image/jpeg"),
        ) as provider, patch(
            "agents._shared.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value=persisted),
        ):
            result = await generate_image(env, "一只猫")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "cloudflare")
        self.assertEqual(result["storage_key"], "generated/test.jpg")
        self.assertEqual(provider.call_count, 1)


if __name__ == "__main__":
    unittest.main()
