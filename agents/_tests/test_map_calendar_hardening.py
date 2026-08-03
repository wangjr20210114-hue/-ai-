from __future__ import annotations

import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from agents._application.intelligence.service import normalize_map_preferences
from agents._infrastructure.providers.tencent_location import plan_verified_route
from agents._application.workspace.service import (
    WorkspaceConflictError,
    apply_calendar_changes,
    apply_calendar_changes_best_effort,
    empty_workspace,
    load_workspace,
    save_workspace,
)
from agents.chat._calendar_context import calendar_context
from agents._infrastructure.skills.builtin_operations import build_system_skill_tools


TEST_USER_ID = "test:map-calendar"


PLACE_A = {
    "schema_version": 1,
    "place_id": "tencent:a",
    "provider": "tencent",
    "name": "起点",
    "address": "北京市起点路",
    "latitude": 39.9,
    "longitude": 116.3,
    "city": "北京市",
    "category": "地名",
}
PLACE_B = {
    **PLACE_A,
    "place_id": "tencent:b",
    "name": "终点",
    "address": "北京市终点路",
    "latitude": 39.8,
    "longitude": 116.4,
}


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class MapCalendarHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_calendar_continuation_collects_timing_then_reuses_verified_stops(self):
        store = FakeStore()
        state = empty_workspace()
        stops = [
            {
                **PLACE_A,
                "place_id": f"hangzhou-{index}",
                "name": name,
                "address": f"杭州市{name}",
            }
            for index, name in enumerate(("灵隐寺", "西湖", "河坊街"), 1)
        ]
        state["place_candidates"] = {item["place_id"]: item for item in stops}
        route_plan = {
            "id": "routeplan-hangzhou",
            "created_at": int(time.time()),
            "ordered_stops": stops,
            "distance_meters": 16_900,
            "duration_seconds": 8_700,
            "mode": "transit",
            "legs": [
                {"duration_seconds": 1_800, "distance_meters": 6_000, "mode": "transit"},
                {"duration_seconds": 2_100, "distance_meters": 10_900, "mode": "transit"},
            ],
        }
        state["latest_route_plan"] = route_plan
        state["route_plans"] = {route_plan["id"]: route_plan}
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="route-calendar-continuation",
            user_id=TEST_USER_ID,
            env={},
            planned_reuse_latest_route=True,
            requested_route_plan_id=route_plan["id"],
        )
        calendar_tool = next(item for item in tools if item.name == "propose_calendar_changes")

        clarification = json.loads(await calendar_tool.ainvoke({
            "summary": "把路线添加到日程",
            "changes": [],
        }))
        self.assertEqual(clarification["ui_action"], "clarification_action")
        self.assertEqual(
            [field["id"] for field in clarification["clarification"]["fields"]],
            ["route_calendar_start", "route_calendar_stop_minutes"],
        )

        result = json.loads(await calendar_tool.ainvoke({
            "summary": "杭州一日游",
            "changes": [],
            "route_start_time": "2099-08-04T08:00:00+08:00",
            "route_stop_minutes": 60,
        }))
        payload = result["action"]["payload"]
        self.assertEqual(payload["source_route_plan_id"], route_plan["id"])
        self.assertEqual(
            [change["event"]["place"]["place_id"] for change in payload["changes"]],
            [item["place_id"] for item in stops],
        )
        starts = [change["event"]["start_time"] for change in payload["changes"]]
        self.assertEqual(starts[1] - starts[0], 90 * 60)
        self.assertEqual(starts[2] - starts[1], 95 * 60)

    def test_map_preferences_are_bounded_and_have_speed_profiles(self):
        self.assertEqual(
            normalize_map_preferences({"service_mode": "fast"})["search_timeout_seconds"],
            20,
        )
        complete = normalize_map_preferences({
            "service_mode": "complete",
            "place_result_limit": 999,
            "route_stop_limit": 999,
            "search_timeout_seconds": 999,
        })
        self.assertEqual(complete["place_result_limit"], 12)
        self.assertEqual(complete["route_stop_limit"], 12)
        self.assertEqual(complete["search_timeout_seconds"], 55)

    def test_calendar_context_prioritizes_future_over_oldest_history(self):
        state = empty_workspace()
        for index in range(120):
            state["schedules"][f"old-{index}"] = {
                "id": f"old-{index}",
                "title": f"历史 {index}",
                "start_time": 100 + index,
                "duration_minutes": 30,
            }
        state["schedules"]["future"] = {
            "id": "future",
            "title": "明天的会议",
            "start_time": 2_000,
            "duration_minutes": 60,
        }
        context = json.loads(calendar_context(state, now=1_000))
        self.assertEqual(context[0]["id"], "future")
        self.assertIn("future", {item["id"] for item in context})
        self.assertLessEqual(len(context), 100)

    async def test_stale_workspace_cannot_overwrite_newer_revision(self):
        store = FakeStore()
        first = await load_workspace(store, "user")
        stale = await load_workspace(store, "user")
        first["schedules"]["a"] = {"id": "a"}
        await save_workspace(store, "user", first)
        stale["schedules"]["b"] = {"id": "b"}
        with self.assertRaises(WorkspaceConflictError):
            await save_workspace(store, "user", stale)

    async def test_route_never_falls_back_to_osm(self):
        failure = RuntimeError("Tencent unavailable")
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.plan_driving_route",
                new=AsyncMock(side_effect=failure),
            ) as tencent,
            patch(
                "agents._infrastructure.providers.tencent_location._get_public",
                new=AsyncMock(),
            ) as public_provider,
        ):
            with self.assertRaisesRegex(RuntimeError, "Tencent unavailable"):
                await plan_verified_route("key", [PLACE_A, PLACE_B])
        tencent.assert_awaited_once()
        public_provider.assert_not_awaited()

    async def test_chat_route_creates_independent_clickable_map_action(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"] = {
            PLACE_A["place_id"]: PLACE_A,
            PLACE_B["place_id"]: PLACE_B,
        }
        await save_workspace(store, TEST_USER_ID, state)
        route = {
            "provider": "tencent",
            "mode": "driving",
            "places": [PLACE_A, PLACE_B],
            "path": [],
            "distance_meters": 10_000,
            "duration_seconds": 1_800,
            "fare": {},
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(return_value=route),
        ):
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-map",
                user_id=TEST_USER_ID,
                env={},
            )
            route_tool = next(tool for tool in tools if tool.name == "plan_route_between_places")
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "起点｜北京市起点路",
                "destination_query": "终点｜北京市终点路",
                "city": "北京",
            }))
        self.assertEqual(result["ui_action"], "map_action")
        self.assertEqual(result["action"]["kind"], "map_recommendation")
        self.assertEqual(
            [item["place_id"] for item in result["action"]["payload"]["places"]],
            ["tencent:a", "tencent:b"],
        )
        self.assertTrue(result["route_plan_id"])
        self.assertTrue(result["action"]["payload"]["calendar_offer"])

    async def test_route_calendar_offer_is_hidden_when_calendar_skill_is_disabled(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"] = {
            PLACE_A["place_id"]: PLACE_A,
            PLACE_B["place_id"]: PLACE_B,
        }
        await save_workspace(store, TEST_USER_ID, state)
        route = {
            "provider": "tencent",
            "mode": "driving",
            "places": [PLACE_A, PLACE_B],
            "path": [],
            "distance_meters": 10_000,
            "duration_seconds": 1_800,
            "fare": {},
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_plan_route",
            new=AsyncMock(return_value=route),
        ):
            tools = build_system_skill_tools(
                None,
                store=store,
                conversation_id="route-map-no-calendar",
                user_id=TEST_USER_ID,
                env={},
                enabled_skills={"maps", "proactive-agent"},
            )
            route_tool = next(
                tool for tool in tools
                if tool.name == "plan_route_between_places"
            )
            result = json.loads(await route_tool.ainvoke({
                "origin_query": "起点｜北京市起点路",
                "destination_query": "终点｜北京市终点路",
                "city": "北京",
            }))
        self.assertFalse(result["action"]["payload"]["calendar_offer"])

    def test_confirmed_calendar_changes_apply_valid_subset(self):
        state = empty_workspace()
        existing = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {
                "title": "保留目标",
                "start_time": 2_000_000_000,
                "duration_minutes": 60,
            },
        }])[0]
        changed, skipped = apply_calendar_changes_best_effort(state, [
            {
                "operation": "update",
                "schedule_id": existing["id"],
                "event": {"title": "已更新目标"},
            },
            {
                "operation": "delete",
                "schedule_id": "missing-id",
            },
        ], now=1_900_000_000)
        self.assertEqual([item["title"] for item in changed], ["已更新目标"])
        self.assertEqual(skipped[0]["operation"], "delete")
        self.assertIn("找不到", skipped[0]["reason"])

    async def test_calendar_move_keeps_duration_and_can_clear_location(self):
        store = FakeStore()
        state = empty_workspace()
        created = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {
                "title": "两小时会议",
                "start_time": 2_000_000_000,
                "duration_minutes": 120,
                "place": PLACE_A,
            },
        }])[0]
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="calendar-duration",
            user_id=TEST_USER_ID,
            env={},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "移动并清空地点",
            "changes": [{
                "operation": "update",
                "schedule_id": created["id"],
                "event": {
                    "start_time": "2033-05-18T04:33:20+08:00",
                    "clear_location": True,
                },
            }],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["duration_minutes"], 120)
        self.assertEqual(event["location"], "")
        self.assertIsNone(event["place"])

    async def test_schedule_place_can_be_shown_on_map_without_research(self):
        store = FakeStore()
        state = empty_workspace()
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {
                "title": "日程中的故宫",
                "start_time": 2_000_000_000,
                "duration_minutes": 60,
                "place": PLACE_A,
            },
        }])
        state["place_candidates"] = {}
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="calendar-map",
            user_id=TEST_USER_ID,
            env={},
        )
        map_tool = next(tool for tool in tools if tool.name == "prepare_map_recommendation")
        result = json.loads(await map_tool.ainvoke({
            "title": "日程地点",
            "place_ids": [PLACE_A["place_id"]],
            "action_text": "显示日程地点",
            "expected_place_count": 1,
        }))
        self.assertEqual(result["action"]["payload"]["places"][0]["place_id"], PLACE_A["place_id"])


if __name__ == "__main__":
    unittest.main()
