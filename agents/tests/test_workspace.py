from __future__ import annotations

import unittest
import json
import ast
from pathlib import Path
from types import SimpleNamespace

from agents.chat._capability_plan import parse_capability_plan, plan_capabilities
from agents.chat._history import bounded_history
from agents.chat._ui_tools import build_production_tools
from agents.messages.index import handler as messages_handler
from agents.shared.side_effects import _meeting_result
from agents.shared.rich_search import evidence_for_model
from agents.shared.tencent_location import decode_polyline
from agents.shared.workspace import (
    apply_calendar_changes,
    empty_workspace,
    load_user_workspace,
    load_workspace,
    new_action,
    normalize_schedule,
    put_action,
    save_workspace,
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
    def __init__(self, body):
        self.body = body


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
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=FakeStore(),
        )
        response = await messages_handler(SimpleNamespace(conversation_id="restore-rich", store=store))
        ai_message = next(item for item in response["messages"] if item["role"] == "ai")
        self.assertEqual(ai_message["searchMeta"], metadata)

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

    async def test_user_assets_are_shared_across_conversations(self):
        store = FakeStore()
        legacy = empty_workspace()
        event = apply_calendar_changes(legacy, [{
            "operation": "create",
            "event": {"title": "参观故宫", "start_time": 100, "place": PLACE},
        }])[0]
        await save_workspace(store, "conversation-old", legacy)

        migrated = await load_user_workspace(store, "conversation-old")
        from_new_conversation = await load_user_workspace(store, "conversation-new")

        self.assertIn(event["id"], migrated["schedules"])
        self.assertIn(event["id"], from_new_conversation["schedules"])

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

    async def test_map_action_requires_explicit_activation(self):
        store = FakeStore()
        state = empty_workspace()
        action = new_action("map_recommendation", {"title": "推荐", "places": [PLACE]}, requires_confirmation=False)
        put_action(state, action)
        await save_workspace(store, "conversation-1", state)
        before = await handler(FakeContext(store, {"operation": "get"}))
        self.assertIsNone(before["map"])
        after = await handler(FakeContext(store, {"operation": "activate_map", "action_id": action["id"], "version": 1}))
        self.assertEqual(after["map"]["places"][0]["place_id"], "poi-1")

    async def test_calendar_tool_accepts_flat_model_wire_shape(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][PLACE["place_id"]] = PLACE
        await save_workspace(store, "c-flat", state)
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


if __name__ == "__main__":
    unittest.main()
