from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents._infrastructure.makers.identity import AuthError, scoped_conversation_id
from agents._application.skills.component_api import public_component_api
from agents._infrastructure.makers.data_version import CONVERSATION_PREFIX, DATA_GENERATION
from agents._application.intelligence.service import (
    DEFAULT_SKILL_PREFERENCES,
    empty_intelligence_state,
    install_user_skill,
    set_user_skill_enabled,
    user_skill_prompt_context,
)
from agents._application.proactive.service import proactive_namespace
from agents._application.workspace.service import _namespace as workspace_namespace
from agents._infrastructure.skills.builtin_operations import build_system_skill_tools
from agents.intelligence.index import handler as intelligence_handler
from agents._tests.auth_helpers import TEST_USER_ID, authenticated_context


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

        scoped = scoped_conversation_id(Ctx(), TEST_USER_ID)
        self.assertRegex(scoped, rf"^{CONVERSATION_PREFIX}[0-9a-f]{{32}}$")
        self.assertLessEqual(len(scoped), 36)
        self.assertNotEqual(scoped_conversation_id(Ctx(), TEST_USER_ID, scoped), scoped)
        long_scoped = scoped_conversation_id(Ctx(), TEST_USER_ID, "legacy-" + "x" * 80)
        self.assertTrue(long_scoped.startswith(CONVERSATION_PREFIX))
        self.assertEqual(len(long_scoped), 36)
        self.assertIn(DATA_GENERATION, workspace_namespace(TEST_USER_ID)[0])
        self.assertIn(DATA_GENERATION, proactive_namespace(TEST_USER_ID)[0])

    def test_current_capabilities_default_to_enabled(self):
        state = empty_intelligence_state()
        self.assertEqual(state["skill_preferences"], DEFAULT_SKILL_PREFERENCES)
        self.assertTrue(all(state["skill_preferences"].values()))

    def test_private_user_skills_are_bounded_model_only_preferences(self):
        state = empty_intelligence_state()
        record = install_user_skill(state, {
            "name": "Research helper",
            "description": "Prefer primary sources",
            "instructions": "Cite primary papers and keep the answer concise.",
            "source_type": "paste",
            "adapter": "untrusted.module",
        }, limit=3, now_ms=1234)

        self.assertTrue(record["id"].startswith("user-research-helper-"))
        self.assertNotIn("adapter", record)
        self.assertIn("primary papers", user_skill_prompt_context(state))

        set_user_skill_enabled(state, record["id"], False)
        self.assertEqual(user_skill_prompt_context(state), "")

    def test_tool_factory_has_no_implicit_single_user_identity(self):
        with self.assertRaises(AuthError):
            build_system_skill_tools(object())

    def test_skill_progress_component_forbids_free_form_labels(self):
        action = next(
            item
            for item in public_component_api()["actions"]
            if item["id"] == "chat.progress.publish"
        )
        self.assertNotIn("label", action["input"])
        self.assertIn("planning", action["input"]["stage"])

    def test_calendar_can_run_without_map_but_map_tools_are_hidden(self):
        tools = build_system_skill_tools(
            object(),
            enabled_skills={"calendar"},
            user_id=TEST_USER_ID,
        )
        names = {tool.name for tool in tools}
        self.assertEqual(names, {
            "ask_user_clarification",
            "propose_calendar_changes",
            "propose_workflow",
        })
        self.assertNotIn("search_places", names)
        self.assertNotIn("recommend_places_on_map", names)


class SkillPreferenceEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_user_can_install_private_declarative_skill(self):
        store = FakeStore()
        ctx = authenticated_context(SimpleNamespace(
            request=SimpleNamespace(body={
                "operation": "install_user_skill",
                "skill": {
                    "name": "Writer",
                    "instructions": "Use short paragraphs.",
                    "source_type": "file",
                },
            }, headers={}),
            store=SimpleNamespace(langgraph_store=store),
        ))
        response = await intelligence_handler(ctx)
        self.assertEqual(len(response["user_skills"]), 1)
        self.assertEqual(response["user_skills"][0]["name"], "Writer")
        self.assertTrue(response["user_skills"][0]["enabled"])

    async def test_locked_proactive_skill_cannot_be_disabled(self):
        store = FakeStore()
        ctx = authenticated_context(SimpleNamespace(
            request=SimpleNamespace(body={
                "operation": "update_skill_preferences",
                "preferences": {"maps": False, "proactive-agent": False},
            }, headers={}),
            store=SimpleNamespace(langgraph_store=store),
        ))
        response = await intelligence_handler(ctx)
        self.assertFalse(response["skill_preferences"]["maps"])
        self.assertTrue(response["skill_preferences"]["proactive-agent"])
        self.assertTrue(response["skill_preferences"]["core"])
        proactive_values = [
            value for (namespace, key), value in store.values.items()
            if namespace[0].startswith("yuanbao_proactive_") and key == "state"
        ]
        self.assertFalse(any(
            value.get("preferences", {}).get("enabled") is False
            for value in proactive_values
        ))

    def test_tool_catalog_respects_each_disabled_skill(self):
        tools = build_system_skill_tools(
            object(),
            env={"TENCENT_MEETING_TOKEN": "configured"},
            enabled_skills={"web-search", "vision", "image-studio", "paper-reading", "tencent-meeting"},
            user_id=TEST_USER_ID,
        )
        names = {tool.name for tool in tools}
        self.assertIn("rich_search", names)
        self.assertIn("analyze_images_parallel", names)
        self.assertIn("propose_image", names)
        self.assertIn("propose_workflow", names)
        self.assertIn("search_arxiv", names)
        self.assertNotIn("propose_meeting", names)
        self.assertNotIn("propose_calendar_changes", names)
        self.assertNotIn("search_places", names)
        linked = build_system_skill_tools(
            object(), env={"TENCENT_MEETING_TOKEN": "configured"},
            enabled_skills={"calendar", "tencent-meeting"},
            user_id=TEST_USER_ID,
        )
        self.assertEqual(
            {tool.name for tool in linked},
            {
                "ask_user_clarification",
                "propose_calendar_changes",
                "propose_meeting",
                "propose_workflow",
            },
        )


if __name__ == "__main__":
    unittest.main()
