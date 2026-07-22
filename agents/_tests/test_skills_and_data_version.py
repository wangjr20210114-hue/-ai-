from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents._shared.auth import scoped_conversation_id
from agents._shared.data_version import CONVERSATION_PREFIX, DATA_GENERATION
from agents._shared.intelligence import DEFAULT_SKILL_PREFERENCES, empty_intelligence_state
from agents._shared.proactive import proactive_namespace
from agents._shared.workspace import _namespace as workspace_namespace
from agents.chat._ui_tools import build_production_tools
from agents.intelligence.index import handler as intelligence_handler


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class SkillAndDataVersionTests(unittest.TestCase):
    def test_clean_generation_scopes_all_business_state(self):
        class Ctx:
            conversation_id = "conversation-1"

        scoped = scoped_conversation_id(Ctx(), "local-user")
        self.assertEqual(scoped, f"{CONVERSATION_PREFIX}conversation-1")
        self.assertLessEqual(len(scoped), 36)
        self.assertEqual(scoped_conversation_id(Ctx(), "local-user", scoped), scoped)
        long_scoped = scoped_conversation_id(Ctx(), "local-user", "legacy-" + "x" * 80)
        self.assertTrue(long_scoped.startswith(CONVERSATION_PREFIX))
        self.assertEqual(len(long_scoped), 36)
        self.assertIn(DATA_GENERATION, workspace_namespace("local-user")[0])
        self.assertIn(DATA_GENERATION, proactive_namespace("local-user")[0])

    def test_current_capabilities_default_to_enabled(self):
        state = empty_intelligence_state()
        self.assertEqual(state["skill_preferences"], DEFAULT_SKILL_PREFERENCES)
        self.assertTrue(all(state["skill_preferences"].values()))

    def test_calendar_can_run_without_map_but_map_tools_are_hidden(self):
        tools = build_production_tools(object(), enabled_skills={"calendar"})
        names = {tool.name for tool in tools}
        self.assertEqual(names, {"propose_calendar_changes"})
        self.assertNotIn("search_places", names)
        self.assertNotIn("recommend_places_on_map", names)


class SkillPreferenceEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_preferences_persist_and_proactive_toggle_is_linked(self):
        store = FakeStore()
        ctx = SimpleNamespace(
            request=SimpleNamespace(body={
                "operation": "update_skill_preferences",
                "preferences": {"maps": False, "proactive-agent": False},
            }),
            store=SimpleNamespace(langgraph_store=store),
        )
        response = await intelligence_handler(ctx)
        self.assertFalse(response["skill_preferences"]["maps"])
        self.assertFalse(response["skill_preferences"]["proactive-agent"])
        self.assertTrue(response["skill_preferences"]["core"])
        proactive_values = [
            value for (namespace, key), value in store.values.items()
            if namespace[0].startswith("yuanbao_proactive_") and key == "state"
        ]
        self.assertEqual(len(proactive_values), 1)
        self.assertFalse(proactive_values[0]["preferences"]["enabled"])

    def test_tool_catalog_respects_each_disabled_skill(self):
        tools = build_production_tools(
            object(),
            env={"TENCENT_MEETING_TOKEN": "configured"},
            enabled_skills={"web-search", "vision", "image-studio", "paper-reading", "tencent-meeting"},
        )
        names = {tool.name for tool in tools}
        self.assertIn("rich_search", names)
        self.assertIn("analyze_images_parallel", names)
        self.assertIn("propose_image", names)
        self.assertIn("search_arxiv", names)
        self.assertNotIn("propose_meeting", names)
        self.assertNotIn("propose_calendar_changes", names)
        self.assertNotIn("search_places", names)
        linked = build_production_tools(
            object(), env={"TENCENT_MEETING_TOKEN": "configured"},
            enabled_skills={"calendar", "tencent-meeting"},
        )
        self.assertEqual({tool.name for tool in linked}, {"propose_calendar_changes", "propose_meeting"})


if __name__ == "__main__":
    unittest.main()
