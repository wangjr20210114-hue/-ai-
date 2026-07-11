from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

import aiosqlite

from agent.collectors.schedule_collector import ScheduleCollector
from agent.collectors.travel_weather_collector import TravelWeatherCollector
from database.init_db import M1_SCHEMA, SCHEMA
from database.migrations import Migration, apply_migrations
from database.repositories import conversation_repo


class FakeWeatherProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    async def get_weather(self, city: str):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class CollectorContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(
            self.db,
            [
                Migration(1, "initial_schema", SCHEMA),
                Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
            ],
        )
        self.patches = [
            patch("agent.collectors.schedule_collector.get_db", return_value=self.db),
            patch("agent.collectors.travel_weather_collector.get_db", return_value=self.db),
            patch.object(conversation_repo, "get_db", return_value=self.db),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        await self.db.close()

    async def _insert_schedule(
        self,
        item_id: str,
        title: str,
        start_time: float,
        duration: int,
        *,
        category: str = "other",
        location: str = "",
        extra: dict | None = None,
    ) -> None:
        now = time.time()
        await self.db.execute(
            "INSERT INTO schedules(id,session_id,title,category,start_time,duration_minutes,location,extra,done,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,0,?,?)",
            (
                item_id,
                "local-user",
                title,
                category,
                start_time,
                duration,
                location,
                json.dumps(extra or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        await self.db.commit()

    async def test_schedule_batch_contains_due_overdue_and_conflict(self) -> None:
        now = time.time()
        await self._insert_schedule("overdue", "已开始会议", now - 300, 60)
        await self._insert_schedule("left", "评审一", now + 600, 60)
        await self._insert_schedule("right", "评审二", now + 1200, 60)
        batch = await ScheduleCollector(lookahead_minutes=30).collect({}, now=now)
        event_types = {event.event_type for event in batch.events}
        self.assertEqual(event_types, {"schedule.due", "schedule.overdue", "schedule.conflict"})
        self.assertGreater(batch.next_run_at, now)
        self.assertEqual(batch.next_checkpoint["last_scan_at"], now)
        self.assertEqual(batch.diagnostics["rows_scanned"], 3)

    async def test_weather_failure_preserves_checkpoint(self) -> None:
        now = time.time()
        await self._insert_schedule(
            "travel-1",
            "西湖",
            now + 86400,
            120,
            category="travel",
            location="杭州",
            extra={"city": "杭州", "place_type": "scenic"},
        )
        old = {"weather": "晴", "temperature": 25, "observed_at": now - 100}
        collector = TravelWeatherCollector(provider=FakeWeatherProvider([TimeoutError("timeout")]))
        batch = await collector.collect({"cities": {"杭州": old}}, now=now)
        self.assertEqual(batch.events, [])
        self.assertEqual(batch.next_checkpoint["cities"]["杭州"], old)
        self.assertIn("杭州", batch.diagnostics["provider_errors"])

    async def test_weather_risk_targets_outdoor_schedules(self) -> None:
        now = time.time()
        await self._insert_schedule(
            "travel-2",
            "西湖",
            now + 86400,
            120,
            category="travel",
            location="杭州",
            extra={"city": "杭州", "place_type": "scenic"},
        )
        collector = TravelWeatherCollector(
            provider=FakeWeatherProvider([{"weather": "暴雨", "temperature": 18, "tips": "注意安全"}])
        )
        batch = await collector.collect(
            {"cities": {"杭州": {"weather": "晴", "temperature": 27}}},
            now=now,
        )
        self.assertEqual(len(batch.events), 1)
        self.assertEqual(batch.events[0].event_type, "travel.outdoor_risk")
        self.assertEqual(batch.events[0].payload["outdoor_schedule_ids"], ["travel-2"])


if __name__ == "__main__":
    unittest.main()
