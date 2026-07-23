from __future__ import annotations

import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents._shared.makers_conversation import (
    public_chat_run,
    read_chat_run,
    write_chat_run,
)
from agents._shared.http import error
from agents._shared.proactive import collect_provider_signals
from agents._shared.proactive import empty_proactive_state, process_schedule_signals
from agents._shared.tencent_location import plan_driving_route
from agents.proactive.index import handler as proactive_handler
from agents.stop.index import handler as stop_handler
from agents.system_internal.index import _expected_tick_after
from agents.chat.index import run_cancelled


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeConversationStore:
    def __init__(self):
        self.metadata = {"title": "保留标题"}

    async def get_conversation(self, **_value):
        return {"metadata": self.metadata}

    async def update_conversation(self, **value):
        self.metadata.update(value["metadata"])


class FakeProactiveStores:
    def __init__(self):
        self.langgraph_store = FakeStore()
        self.messages = []

    async def append_message(self, **value):
        self.messages.append(value)
        return "proactive-message-1"

    async def get_messages(self, **_value):
        return list(reversed(self.messages))


class RuntimeRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_conversation_receives_one_model_written_proactive_opening(self):
        state = empty_proactive_state()
        now = int(datetime.fromisoformat("2026-07-21T12:00:00+08:00").timestamp())
        process_schedule_signals(state, [{
            "type": "schedule_upcoming", "dedup_key": "upcoming:test", "priority": "normal",
            "subject_ids": ["schedule-1"], "title": "即将开始", "detail": "产品评审将在一小时后开始",
            "action": "检查地点和材料", "evidence": {}, "occurred_at": now,
        }], now)
        stores = FakeProactiveStores()
        ctx = SimpleNamespace(
            env={}, store=stores, conversation_id="new-conversation",
            request=SimpleNamespace(body={"operation": "open_conversation"}, headers={}),
        )
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="产品评审一小时后开始。要我帮你检查地点或准备材料吗？")))
        with (
            patch("agents.proactive.index.run_proactive_tick", AsyncMock(return_value=(state, {"signals": 1}))),
            patch("agents.proactive.index.get_model", return_value=model),
        ):
            response = await proactive_handler(ctx)
        self.assertTrue(response["proactive_message"]["proactive"])
        self.assertEqual(len(stores.messages), 1)
        self.assertEqual(stores.messages[0]["metadata"]["source"], "yuanbao-proactive")
        self.assertEqual(response["notifications"], [])
        self.assertEqual(next(iter(state["notifications"].values()))["status"], "read")

    async def test_user_message_wins_race_with_proactive_opening(self):
        state = empty_proactive_state()
        now = int(datetime.fromisoformat("2026-07-21T12:00:00+08:00").timestamp())
        process_schedule_signals(state, [{
            "type": "schedule_upcoming", "dedup_key": "upcoming:race", "priority": "normal",
            "subject_ids": ["schedule-race"], "title": "即将开始", "detail": "会议即将开始",
            "action": "检查材料", "evidence": {}, "occurred_at": now,
        }], now)
        stores = FakeProactiveStores()

        async def compose_after_user_sent(_messages):
            stores.messages.append({"role": "user", "content": "我先问一个问题"})
            return SimpleNamespace(content="会议即将开始。要我帮你准备材料吗？")

        ctx = SimpleNamespace(
            env={}, store=stores, conversation_id="race-conversation",
            request=SimpleNamespace(body={"operation": "open_conversation"}, headers={}),
        )
        model = SimpleNamespace(ainvoke=AsyncMock(side_effect=compose_after_user_sent))
        with (
            patch("agents.proactive.index.run_proactive_tick", AsyncMock(return_value=(state, {"signals": 1}))),
            patch("agents.proactive.index.get_model", return_value=model),
        ):
            response = await proactive_handler(ctx)
        self.assertIsNone(response["proactive_message"])
        self.assertEqual(response["opening_suppressed"], "conversation_became_active")
        self.assertEqual(len(stores.messages), 1)
        self.assertEqual(response["notifications"][0]["status"], "unread")

    async def test_proactive_preference_change_triggers_one_refresh(self):
        stores = FakeProactiveStores()
        refreshed = empty_proactive_state()
        refreshed["preferences"]["daily_limit"] = 3
        ctx = SimpleNamespace(
            env={}, store=stores, conversation_id="settings-conversation",
            request=SimpleNamespace(body={
                "operation": "update_preferences", "preferences": {"daily_limit": 3},
            }, headers={}),
        )
        with patch(
            "agents.proactive.index.run_proactive_tick",
            AsyncMock(return_value=(refreshed, {"signals": 0})),
        ) as tick:
            response = await proactive_handler(ctx)
        tick.assert_awaited_once()
        self.assertEqual(response["preferences"]["daily_limit"], 3)
        self.assertEqual(response["tick_stats"], {"signals": 0})

    async def test_document_signal_immediately_creates_one_proactive_opportunity(self):
        stores = FakeProactiveStores()
        ctx = SimpleNamespace(
            env={}, store=stores, conversation_id="document-conversation",
            request=SimpleNamespace(body={
                "operation": "ingest_signal",
                "signal_type": "file_uploaded",
                "dedup_key": "blob-document-1",
                "payload": {
                    "file_id": "file-1", "storage_key": "uploads/file-1",
                    "filename": "TEST-方案.pdf", "is_paper": False,
                },
            }, headers={}),
        )
        first = await proactive_handler(ctx)
        second = await proactive_handler(ctx)
        self.assertTrue(first["signal_created"])
        self.assertEqual(first["tick_stats"]["notifications_created"], 1)
        self.assertEqual(first["notifications"][0]["type"], "opportunity_document_next_step")
        self.assertFalse(second["signal_created"])
        self.assertEqual(len(second["notifications"]), 1)

    async def test_generated_image_signal_runs_semantic_judgment_once(self):
        stores = FakeProactiveStores()
        ctx = SimpleNamespace(
            env={}, store=stores, conversation_id="image-conversation",
            request=SimpleNamespace(body={
                "operation": "ingest_signal",
                "signal_type": "image_generated",
                "dedup_key": "image-action-1",
                "payload": {
                    "action_id": "image-action-1",
                    "prompt": "活动页首屏插图，主体靠左并给右侧标题留白",
                    "has_reference_image": False,
                },
            }, headers={}),
        )
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=(
            '{"should_notify":true,"type":"image_iteration","title":"生成移动端适配版",'
            '"body":"当前横幅还可以补一版竖屏构图。",'
            '"action_prompt":"基于刚生成的图片制作9:16移动端版本并保留标题区域",'
            '"priority":"low","confidence":0.9,"expires_in_hours":24,"reason":"已有明确活动页用途"}'
        ))))
        with patch("agents.proactive.index.get_model", return_value=model):
            first = await proactive_handler(ctx)
            second = await proactive_handler(ctx)
        self.assertIn("signal_created", first, first)
        self.assertTrue(first["signal_created"])
        self.assertEqual(first["tick_stats"]["notifications_created"], 1)
        self.assertEqual(first["notifications"][0]["type"], "opportunity_image_iteration")
        self.assertFalse(second["signal_created"])
        self.assertEqual(model.ainvoke.await_count, 1)
        image_events = [
            value for value in stores.langgraph_store.values.values()
            if isinstance(value, dict) and isinstance(value.get("events"), dict)
        ]
        self.assertTrue(image_events)
        persisted = next(
            event for event in image_events[0]["events"].values()
            if event.get("type") == "image_generated"
        )
        self.assertNotIn("prompt", persisted["payload"])

    async def test_chat_run_uses_native_conversation_metadata(self):
        store = FakeConversationStore()
        await write_chat_run(store, "conversation-1", run_id="run-1", status="running")
        restored = await read_chat_run(store, "conversation-1")
        self.assertEqual(restored["status"], "running")
        self.assertEqual(public_chat_run(restored)["run_id"], "run-1")
        self.assertEqual(store.metadata["title"], "保留标题")

    async def test_stop_delegates_public_id_to_makers_abort(self):
        store = FakeConversationStore()
        await write_chat_run(store, "conversation-1", run_id="run-1", status="running")
        targets = []
        ctx = SimpleNamespace(
            env={},
            store=store,
            request=SimpleNamespace(body={"conversation_id": "conversation-1"}, headers={}),
            utils=SimpleNamespace(
                abortActiveRun=lambda target: (
                    targets.append(target)
                    or SimpleNamespace(aborted=True, run_id="run-1")
                ),
            ),
        )
        response = await stop_handler(ctx)
        self.assertEqual(targets, ["conversation-1"])
        self.assertEqual(response["status"], "aborted")
        self.assertEqual((await read_chat_run(store, "conversation-1"))["status"], "cancelled")

    def test_chat_producer_honors_both_makers_stop_states(self):
        self.assertTrue(run_cancelled({"status": "cancel_requested"}))
        self.assertTrue(run_cancelled({"status": "cancelled"}))
        self.assertFalse(run_cancelled({"status": "running"}))

    def test_daily_health_grace_uses_scheduled_boundary(self):
        now = int(datetime.fromisoformat("2026-07-19T11:00:00+08:00").timestamp())
        expected = _expected_tick_after(now)
        self.assertEqual(expected, int(datetime.fromisoformat("2026-07-19T08:00:00+08:00").timestamp()))


    def test_error_helper_uses_runtime_status_envelope(self):
        self.assertEqual(
            error("预算不足", 429),
            {"status_code": 429, "body": {"error": "预算不足"}},
        )

    async def test_tencent_duration_is_normalized_from_minutes_to_seconds(self):
        places = [
            {"place_id": "a", "latitude": 39.9, "longitude": 116.3},
            {"place_id": "b", "latitude": 39.8, "longitude": 116.4},
        ]
        response = {
            "result": {
                "routes": [{"distance": 4824, "duration": 24, "polyline": []}],
            },
        }
        with patch("agents._shared.tencent_location._get", AsyncMock(return_value=response)):
            route = await plan_driving_route("key", places)
        self.assertEqual(route["duration_seconds"], 24 * 60)
        self.assertEqual(route["schema_version"], 2)

    async def test_provider_collectors_keep_safe_weather_and_route_facts(self):
        now = int(time.time())
        place_a = {"place_id": "a", "latitude": 39.9, "longitude": 116.3}
        place_b = {"place_id": "b", "latitude": 39.8, "longitude": 116.4}
        schedules = [
            {"id": "a", "title": "A", "start_time": now + 3600, "duration_minutes": 30, "extra": {"place": place_a}},
            {"id": "b", "title": "B", "start_time": now + 5700, "duration_minutes": 30, "extra": {"place": place_b}},
        ]
        route = {"provider": "tencent", "duration_seconds": 1800, "distance_meters": 5000}
        weather = {"weather": "晴", "temperature": 28, "humidity": 55}
        with (
            patch("agents._shared.proactive.get_current_weather", AsyncMock(return_value=weather)),
            patch("agents._shared.proactive.plan_verified_route", AsyncMock(return_value=route)),
        ):
            signals, diagnostics = await collect_provider_signals({"TENCENT_MAP_KEY": "key"}, schedules, now)
        self.assertEqual(len(diagnostics["weather_facts"]), 2)
        self.assertEqual(diagnostics["route_facts"][0]["route_duration_seconds"], 1800)
        self.assertTrue(any(item["type"] == "route_risk" for item in signals))

if __name__ == "__main__":
    unittest.main()
