from __future__ import annotations

import unittest
import json
import ast
import threading
import base64
import hashlib
import hmac
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents.chat._capability_plan import parse_capability_plan, plan_capabilities
from agents.chat._followups import parse_followups
from agents.chat._history import bounded_history
from agents.chat._ui_tools import build_production_tools
from agents.chat._protocol import PublicStreamFilter, dsml_tool_calls, public_content
from agents.messages.index import handler as messages_handler
from agents.shared.side_effects import _meeting_result
from agents.shared.auth import require_user, scoped_conversation_id, verify_jwt
from agents.shared.rich_search import (
    _filter_for_target_date,
    _review_image,
    evidence_for_model,
    rich_search as run_rich_search,
)
from agents.shared.arxiv import _best_title_match
from agents.shared.tencent_location import decode_polyline
from agents.shared.workspace import (
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
from agents.shared.proactive import (
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
    ingest_external_signal,
)
from agents.shared.intelligence import (
    confirm_memory,
    confirmed_memory_context,
    empty_intelligence_state,
    propose_memory,
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


def signed_test_jwt(user_id: str, secret: str, now: int | None = None) -> str:
    now = int(now or time.time())
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode({"sub": user_id, "username": "alice", "roles": ["user"], "iat": now - 1, "exp": now + 3600})
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


class WorkspaceUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_multi_user_jwt_and_conversation_scope_are_tenant_bound(self):
        secret = "0123456789abcdef0123456789abcdef"
        user_a = "11111111-1111-1111-1111-111111111111"
        user_b = "22222222-2222-2222-2222-222222222222"
        token = signed_test_jwt(user_a, secret)
        self.assertEqual(verify_jwt(token, secret)["sub"], user_a)
        ctx = SimpleNamespace(
            env={"AUTH_MODE": "multi_user", "JWT_SECRET": secret},
            request=FakeRequest({}, {"cookie": f"jwt_token={token}"}),
            conversation_id="conversation-shared",
        )
        self.assertEqual(require_user(ctx)["user_id"], user_a)
        self.assertEqual(scoped_conversation_id(ctx, user_a), f"tenant:{user_a}:conversation-shared")
        self.assertNotEqual(scoped_conversation_id(ctx, user_a), f"tenant:{user_b}:conversation-shared")

    async def test_user_workspaces_and_proactive_state_are_isolated(self):
        store = FakeStore()
        user_a = "11111111-1111-1111-1111-111111111111"
        user_b = "22222222-2222-2222-2222-222222222222"
        workspace = empty_workspace()
        workspace["schedules"]["private-a"] = {"id": "private-a", "title": "A 的日程", "start_time": 1, "end_time": 2}
        await save_workspace(store, user_a, workspace)
        self.assertIn("private-a", (await load_user_workspace(store, user_id=user_a))["schedules"])
        self.assertNotIn("private-a", (await load_user_workspace(store, user_id=user_b))["schedules"])
        proactive = empty_proactive_state()
        proactive["preferences"]["enabled"] = False
        await save_proactive_state(store, proactive, user_a)
        self.assertFalse((await load_proactive_state(store, user_a))["preferences"]["enabled"])
        self.assertTrue((await load_proactive_state(store, user_b))["preferences"]["enabled"])

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
        )
        self.assertIn("2026-07-15", rendered)

    def test_capability_plan_parser_is_bounded_to_known_booleans(self):
        plan = parse_capability_plan('```json\n{"needs_places": true, "needs_map_action": 1, "search_query": "北京旅行", "image_query": "故宫建筑", "unknown": true}\n```')
        self.assertTrue(plan["needs_places"])
        self.assertTrue(plan["needs_map_action"])
        self.assertEqual(plan["search_query"], "北京旅行")
        self.assertEqual(plan["image_query"], "故宫建筑")
        self.assertNotIn("unknown", plan)

    def test_follow_up_parser_accepts_only_three_unique_questions(self):
        self.assertEqual(
            parse_followups('```json\n["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？", "多余问题？"]\n```'),
            ["故宫为什么叫紫禁城？", "明清皇帝如何使用故宫？", "故宫有哪些必看建筑？"],
        )
        self.assertEqual(parse_followups("不是 JSON"), [])


    def test_meeting_bridge_result_normalizes_legacy_shape(self):
        result = _meeting_result(
            {"ok": True, "result": {"ok": True, "meetingId": "m-1", "joinUrl": "https://meeting.example/join"}},
            "评审会",
            "2026-07-17T09:00:00+08:00",
        )
        self.assertEqual(result["meeting_id"], "m-1")
        self.assertEqual(result["join_url"], "https://meeting.example/join")

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

    def test_external_connector_signals_are_persistent_and_deduplicated(self):
        state = empty_proactive_state()
        first, created = ingest_external_signal(
            state, signal_type="file_uploaded", dedup_key="blob-1", payload={"filename": "paper.pdf"}, now=100,
        )
        repeated, created_again = ingest_external_signal(
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
        with patch("agents.shared.intelligence.time.time", return_value=1_800_000_000):
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

    def test_tencent_polyline_delta_decode(self):
        path = decode_polyline([39.9, 116.3, 100000, 200000])
        self.assertAlmostEqual(path[1]["latitude"], 40.0)
        self.assertAlmostEqual(path[1]["longitude"], 116.5)

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
        with patch("agents.shared.rich_search._json_request", return_value=response) as request:
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

    async def test_rich_search_starts_fact_and_visual_queries_in_parallel(self):
        barrier = threading.Barrier(2, timeout=2)

        def request(*_args, **_kwargs):
            barrier.wait()
            return {"Pages": []}

        with patch("agents.shared.rich_search._json_request", side_effect=request):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "factual query", "visual query", "basic",
            )
        self.assertEqual(result["total"], 0)
        self.assertIn("timings_ms", result)


if __name__ == "__main__":
    unittest.main()
