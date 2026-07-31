from __future__ import annotations

import importlib
import unittest

from agents._shared.skill_registry import (
    locked_skill_ids,
    skill_manifests,
    tool_skill_map,
)
from agents.chat._ui_tools import build_production_tools


class AllSystemSkillAdapterTests(unittest.TestCase):
    def test_every_system_skill_declares_one_trusted_adapter(self):
        for manifest in skill_manifests():
            with self.subTest(skill=manifest.id):
                self.assertEqual(manifest.kind, "system")
                self.assertTrue(
                    manifest.adapter.startswith("agents._skill_adapters.")
                )
                module_name, separator, function_name = manifest.adapter.partition(":")
                self.assertEqual(separator, ":")
                self.assertEqual(function_name, "build_tools")
                self.assertTrue(
                    callable(getattr(importlib.import_module(module_name), function_name))
                )

    def test_production_tools_exactly_match_manifest_ownership(self):
        tools = build_production_tools(
            object(),
            env={"TENCENT_MEETING_TOKEN": "configured"},
            user_id="adapter-user",
        )

        names = [tool.name for tool in tools]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(tool_skill_map()))

    def test_guest_receives_only_locked_core_and_proactive_tools(self):
        tools = build_production_tools(
            object(),
            env={"TENCENT_MEETING_TOKEN": "configured"},
            user_id="guest-user",
            identity={
                "tenant_id": "guest-tenant",
                "user_id": "guest-user",
                "membership": "guest",
            },
        )
        owners = tool_skill_map()

        self.assertEqual(
            {owners[tool.name] for tool in tools},
            locked_skill_ids(),
        )
        self.assertEqual(
            {tool.name for tool in tools},
            {"ask_user_clarification", "propose_workflow"},
        )

    def test_disabled_optional_skills_are_not_loaded(self):
        tools = build_production_tools(
            object(),
            user_id="adapter-user",
            enabled_skills=set(),
        )

        self.assertEqual(
            {tool.name for tool in tools},
            {"ask_user_clarification", "propose_workflow"},
        )


if __name__ == "__main__":
    unittest.main()

