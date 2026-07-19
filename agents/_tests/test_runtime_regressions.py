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
from agents._shared.tencent_location import plan_driving_route
from agents.stop.index import handler as stop_handler
from agents.system_internal.index import _expected_tick_after


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


class RuntimeRegressionTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual((await read_chat_run(store, "conversation-1"))["status"], "cancel_requested")

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
