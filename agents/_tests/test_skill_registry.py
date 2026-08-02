from __future__ import annotations

import sys
import types
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agents._application.skills.registry as registry_module
from agents._application.skills.registry import (
    SkillRuntimeContext,
    build_adapter_tools,
    default_skill_preferences,
    locked_skill_ids,
    parse_skill_manifests,
    planner_topic_tools,
    public_skill_catalog,
    public_skill_package,
    resolve_enabled_skills,
    skill_dependency_graph,
    skill_manifests,
    tool_skill_map,
    unavailable_skills_for_action,
)
from agents._application.intelligence.service import (
    configure_skill_connection,
    empty_intelligence_state,
    public_skill_connections,
    skill_runtime_env,
)
from agents.skill_marketplace.index import handler as skills_handler
from agents.chat._capability_plan import required_tools_for_plan
from agents._infrastructure.skills.builtin_operations import build_system_skill_tools
from agents._tests.auth_helpers import authenticated_context, authenticated_namespace
from agents._tests.auth_helpers import TEST_USER_ID


def _manifest(**changes):
    value = {
        "schema_version": 1,
        "id": "test-skill",
        "order": 5,
        "default_enabled": True,
        "capabilities": ["test_capability"],
        "tools": [
            {"name": "test_skill_tool", "capability": "test_capability"},
        ],
        "permissions": ["makers.model", "conversation.read"],
        "env_keys": ["TEST_VISIBLE"],
        "ui": {
            "name": {"zh-CN": "测试 Skill", "en": "Test Skill"},
            "description": {"zh-CN": "测试", "en": "Test"},
        },
        "planner": {
            "topic": "test",
            "summary": "A test-only capability.",
        },
    }
    value.update(changes)
    return value


class SkillRegistryContractTests(unittest.TestCase):
    def test_installed_registry_is_ordered_and_drives_defaults(self):
        manifests = skill_manifests()
        self.assertEqual(
            [manifest.id for manifest in manifests],
            [
                "core",
                "proactive-agent",
                "web-search",
                "vision",
                "image-studio",
                "maps",
                "calendar",
                "paper-reading",
                "tencent-meeting",
            ],
        )
        self.assertEqual(
            set(default_skill_preferences()),
            {manifest.id for manifest in manifests},
        )
        self.assertTrue(default_skill_preferences()["core"])
        self.assertEqual(locked_skill_ids(), {"core", "proactive-agent"})
        self.assertEqual(
            next(
                manifest.unavailable_fallback
                for manifest in manifests
                if manifest.id == "web-search"
            ),
            "model_only",
        )

    def test_edgeone_runtime_package_name_is_resolved_for_dynamic_entrypoints(self):
        with patch.object(
            registry_module,
            "__package__",
            "pages_agents._application.skills",
        ):
            self.assertEqual(
                registry_module._runtime_module_name(
                    "agents._skill_adapters.proactive_agent"
                ),
                "pages_agents._skill_adapters.proactive_agent",
            )

    def test_public_catalog_and_provider_readiness_are_manifest_driven(self):
        disconnected = public_skill_catalog({})
        meeting = next(item for item in disconnected if item["id"] == "tencent-meeting")
        self.assertFalse(meeting["configured"])
        self.assertEqual(meeting["requires"], ["calendar"])
        connected = public_skill_catalog({"TENCENT_MEETING_TOKEN": "ready"})
        self.assertTrue(
            next(item for item in connected if item["id"] == "tencent-meeting")[
                "configured"
            ]
        )
        self.assertEqual(meeting["credential"]["kind"], "token")
        self.assertEqual(meeting["credential"]["ttl_seconds"], 7 * 24 * 60 * 60)

    def test_every_built_in_is_a_downloadable_standard_skill_package(self):
        for manifest in skill_manifests():
            with self.subTest(skill=manifest.id):
                package_path = (
                    Path(registry_module.__file__).resolve().parents[2]
                    / manifest.package_path
                )
                self.assertTrue((package_path / "SKILL.md").is_file())
                self.assertTrue((package_path / "floris.json").is_file())
                package = public_skill_package(manifest.id)
                self.assertEqual(package["id"], manifest.id)
                self.assertEqual(
                    package["files"]["floris.json"]["id"],
                    manifest.id,
                )
                self.assertIn(
                    f"name: {manifest.id}",
                    package["files"]["SKILL.md"],
                )

    def test_dependency_graph_is_deterministic_and_matches_manifests(self):
        graph = skill_dependency_graph()
        self.assertEqual(
            {node["id"] for node in graph["nodes"]},
            {manifest.id for manifest in skill_manifests()},
        )
        self.assertIn({
            "from": "tencent-meeting",
            "to": "calendar",
            "type": "requires",
        }, graph["edges"])

    def test_personal_skill_token_is_private_and_expires_after_one_week(self):
        state = empty_intelligence_state()
        configured = configure_skill_connection(
            state,
            "tencent-meeting",
            "personal-token-that-is-long-enough",
            now=100,
        )
        self.assertEqual(configured["expires_at"], 100 + 7 * 24 * 60 * 60)
        self.assertEqual(
            skill_runtime_env({}, state, now=101)["TENCENT_MEETING_TOKEN"],
            "personal-token-that-is-long-enough",
        )
        self.assertNotIn(
            "TENCENT_MEETING_TOKEN",
            json.dumps(public_skill_connections(state, now=101)),
        )
        self.assertNotIn(
            "TENCENT_MEETING_TOKEN",
            skill_runtime_env({}, state, now=configured["expires_at"]),
        )

    def test_required_dependencies_are_resolved_before_tool_construction(self):
        self.assertNotIn(
            "tencent-meeting",
            resolve_enabled_skills({"tencent-meeting"}),
        )
        self.assertEqual(
            resolve_enabled_skills({"calendar", "tencent-meeting"}),
            frozenset({"calendar", "tencent-meeting"}),
        )
        self.assertEqual(
            unavailable_skills_for_action(
                "meeting_create",
                {"calendar": False, "tencent-meeting": True},
            ),
            ("tencent-meeting", "calendar"),
        )
        self.assertEqual(
            unavailable_skills_for_action(
                "meeting_create",
                {"calendar": True, "tencent-meeting": True},
            ),
            (),
        )

    def test_manifest_validation_rejects_registry_collisions_and_cycles(self):
        with self.assertRaisesRegex(ValueError, "duplicate Skill id"):
            parse_skill_manifests([_manifest(), _manifest()])
        with self.assertRaisesRegex(ValueError, "unknown Makers permissions"):
            parse_skill_manifests([
                _manifest(permissions=["makers.unrestricted"]),
            ])
        first = _manifest(id="first-skill", requires=["second-skill"])
        second = _manifest(
            id="second-skill",
            capabilities=["second_capability"],
            tools=[{
                "name": "second_skill_tool",
                "capability": "second_capability",
            }],
            requires=["first-skill"],
        )
        with self.assertRaisesRegex(ValueError, "cyclic required Skill dependency"):
            parse_skill_manifests([first, second])

    def test_runtime_context_enforces_makers_permissions_and_env_allow_list(self):
        manifest = parse_skill_manifests([_manifest()])[0]
        model = object()
        context = SkillRuntimeContext(manifest, {
            "model": model,
            "state_store": object(),
            "conversation_id": "conversation-1",
            "user_id": "private-user",
            "env": {"TEST_VISIBLE": "yes", "SECRET": "hidden"},
        })
        self.assertIs(context.model, model)
        self.assertEqual(context.conversation_id, "conversation-1")
        self.assertEqual(context.user_id, "")
        self.assertEqual(dict(context.env), {"TEST_VISIBLE": "yes"})
        with self.assertRaises(PermissionError):
            _ = context.state_store
        with self.assertRaises(PermissionError):
            _ = context.browser_location

    def test_adapter_can_reuse_makers_model_without_central_registration(self):
        module_name = "agents._skill_adapters._runtime_skill_adapter"
        module = types.ModuleType(module_name)
        observed = {}

        def build_tools(context):
            observed["model"] = context.model
            observed["env"] = dict(context.env)
            return [SimpleNamespace(name="test_skill_tool")]

        module.build_tools = build_tools
        sys.modules[module_name] = module
        manifest = parse_skill_manifests([
            _manifest(adapter=f"{module_name}:build_tools"),
        ])[0]
        model = object()
        try:
            with patch(
                "agents._application.skills.registry.skill_manifests",
                return_value=(manifest,),
            ):
                tools = build_adapter_tools(
                    {
                        "model": model,
                        "env": {"TEST_VISIBLE": "yes", "SECRET": "hidden"},
                    },
                    {"test-skill"},
                )
        finally:
            sys.modules.pop(module_name, None)
        self.assertEqual([tool.name for tool in tools], ["test_skill_tool"])
        self.assertIs(observed["model"], model)
        self.assertEqual(observed["env"], {"TEST_VISIBLE": "yes"})

    def test_every_built_in_tool_has_one_manifest_owner(self):
        tools = build_system_skill_tools(
            object(),
            env={"TENCENT_MEETING_TOKEN": "configured"},
            user_id=TEST_USER_ID,
        )
        names = {tool.name for tool in tools}
        owners = tool_skill_map()
        self.assertEqual(names, set(owners))
        self.assertEqual(len(owners), len(set(owners)))
        self.assertIn("plan_route_between_places", planner_topic_tools()["maps"])

    def test_plugin_capability_requires_its_declared_tool(self):
        plan = {
            "_capabilities": ["papers"],
            "capabilities": ["papers"],
        }
        self.assertIn("search_arxiv", required_tools_for_plan(plan))


class SkillCatalogRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_packaging_entry_point_exposes_the_same_read_only_catalog(self):
        response = await skills_handler(authenticated_namespace(
            request=SimpleNamespace(body={}, headers={}),
            env={},
        ))
        self.assertEqual(
            [item["id"] for item in response["skills"]],
            [manifest.id for manifest in skill_manifests()],
        )

    async def test_cloudbase_user_can_read_the_marketplace_state(self):
        ctx = authenticated_namespace(
            request=SimpleNamespace(body={}, headers={}),
            env={},
        )
        authenticated_context(ctx, auth_type="cloudbase", membership="free")
        response = await skills_handler(ctx)
        self.assertEqual(response["identity"]["auth_type"], "cloudbase")
        self.assertEqual(response["identity"]["membership"], "free")
        self.assertTrue(all(item["eligible"] for item in response["skills"]))


if __name__ == "__main__":
    unittest.main()
