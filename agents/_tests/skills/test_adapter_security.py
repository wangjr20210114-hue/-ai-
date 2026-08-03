from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents._application.skills.registry import parse_skill_manifests
from agents._application.skills.runtime import build_adapter_tools


def manifest(**changes):
    value = {
        "schema_version": 2,
        "id": "adapter-test",
        "kind": "system",
        "required_plan": "free",
        "capabilities": ["adapter_capability"],
        "tools": [
            {
                "name": "adapter_tool",
                "capability": "adapter_capability",
            },
        ],
        "permissions": [],
    }
    value.update(changes)
    return value


class SkillAdapterSecurityTests(unittest.TestCase):
    def test_tool_cannot_publish_an_internal_component_action(self):
        with self.assertRaisesRegex(ValueError, "only public component actions"):
            parse_skill_manifests([
                manifest(
                    adapter="agents._skill_adapters.example:build_tools",
                    tools=[{
                        "name": "adapter_tool",
                        "capability": "adapter_capability",
                        "publishes": ["workspace.state.read"],
                    }],
                    permissions=["components.workspace"],
                    component_actions=["workspace.state.read"],
                ),
            ])

    def test_executable_adapter_component_actions_are_bound_to_tools(self):
        with self.assertRaisesRegex(ValueError, "unused component actions"):
            parse_skill_manifests([
                manifest(
                    adapter="agents._skill_adapters.example:build_tools",
                    permissions=["components.search"],
                    component_actions=["search.evidence.publish"],
                ),
            ])

    def test_tool_cannot_publish_an_undeclared_component_action(self):
        with self.assertRaisesRegex(ValueError, "declared in component_actions"):
            parse_skill_manifests([
                manifest(
                    tools=[{
                        "name": "adapter_tool",
                        "capability": "adapter_capability",
                        "publishes": ["search.evidence.publish"],
                    }],
                ),
            ])

    def test_system_adapter_must_live_under_trusted_package(self):
        with self.assertRaisesRegex(ValueError, "trusted system adapter"):
            parse_skill_manifests([
                manifest(adapter="agents._infrastructure.skills.builtin_operations:build_tools"),
            ])

    def test_non_system_skill_adapter_is_never_executable(self):
        with self.assertRaisesRegex(ValueError, "cannot declare"):
            parse_skill_manifests([
                manifest(
                    kind="user",
                    adapter="agents._skill_adapters.evil:build_tools",
                ),
            ])

    def test_non_system_preference_hook_is_never_executable(self):
        with self.assertRaisesRegex(ValueError, "trusted system preference hook"):
            parse_skill_manifests([
                manifest(
                    kind="community",
                    preference_hook="evil.module:on_change",
                ),
            ])

    def test_adapter_must_return_every_required_declared_tool(self):
        module_name = "agents._skill_adapters._security_test"
        module = types.ModuleType(module_name)
        module.build_tools = lambda _context: ()
        sys.modules[module_name] = module
        parsed = parse_skill_manifests([
            manifest(adapter=f"{module_name}:build_tools"),
        ])
        try:
            with patch(
                "agents._application.skills.registry.skill_manifests",
                return_value=parsed,
            ):
                with self.assertRaisesRegex(ValueError, "required tools"):
                    build_adapter_tools({}, {"adapter-test"})
        finally:
            sys.modules.pop(module_name, None)

    def test_adapter_rejects_duplicate_returned_names(self):
        module_name = "agents._skill_adapters._duplicate_test"
        module = types.ModuleType(module_name)
        module.build_tools = lambda _context: (
            SimpleNamespace(name="adapter_tool"),
            SimpleNamespace(name="adapter_tool"),
        )
        sys.modules[module_name] = module
        parsed = parse_skill_manifests([
            manifest(adapter=f"{module_name}:build_tools"),
        ])
        try:
            with patch(
                "agents._application.skills.registry.skill_manifests",
                return_value=parsed,
            ):
                with self.assertRaisesRegex(ValueError, "duplicate or unnamed"):
                    build_adapter_tools({}, {"adapter-test"})
        finally:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
