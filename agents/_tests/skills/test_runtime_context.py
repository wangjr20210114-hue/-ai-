from __future__ import annotations

import unittest

from agents._application.skills.component_api import COMPONENT_API_VERSION
from agents._application.skills.registry import parse_skill_manifests
from agents._application.skills.runtime import SkillRuntimeContext


def runtime_manifest():
    return parse_skill_manifests([
        {
            "schema_version": 2,
            "id": "runtime-test",
            "kind": "system",
            "capabilities": ["runtime_capability"],
            "permissions": [
                "user.read",
                "components.search",
            ],
            "env_keys": ["VISIBLE"],
            "component_actions": ["search.evidence.publish"],
        },
    ])[0]


class SkillRuntimeContextTests(unittest.TestCase):
    def test_context_denies_undeclared_service_and_component(self):
        context = SkillRuntimeContext(runtime_manifest(), {})

        with self.assertRaises(PermissionError):
            context.service("calendar")
        with self.assertRaises(PermissionError):
            context.component("calendar.change.propose")

    def test_permission_does_not_bypass_manifest_component_action_allowlist(self):
        manifest = parse_skill_manifests([
            {
                "schema_version": 2,
                "id": "allowlist-test",
                "kind": "system",
                "capabilities": ["runtime_capability"],
                "permissions": ["components.search"],
                "component_actions": ["search.evidence.publish"],
            },
        ])[0]
        context = SkillRuntimeContext(
            manifest,
            {
                "components": {
                    "search.evidence.publish": lambda value: value,
                    "search.media.publish": lambda value: value,
                },
            },
        )

        with self.assertRaisesRegex(PermissionError, "did not declare component action"):
            context.component("search.media.publish")

    def test_context_filters_env_and_returns_only_declared_service(self):
        search = object()
        context = SkillRuntimeContext(
            runtime_manifest(),
            {
                "env": {"VISIBLE": "yes", "SECRET": "no"},
                "services": {"search": search, "calendar": object()},
            },
        )

        self.assertEqual(dict(context.env), {"VISIBLE": "yes"})
        self.assertIs(context.service("search"), search)
        with self.assertRaises(PermissionError):
            context.service("calendar")

    def test_component_envelope_uses_signed_identity(self):
        received = []
        context = SkillRuntimeContext(
            runtime_manifest(),
            {
                "request_id": "request-1",
                "identity": {
                    "tenant_id": "tenant-signed",
                    "subject_id": "user-signed",
                },
                "components": {
                    "search.evidence.publish": received.append,
                },
            },
        )

        publish = context.component("search.evidence.publish")
        publish({
            "source_id": "source-1",
            "title": "Evidence",
            "url": "https://example.test/evidence",
        })

        self.assertEqual(received[0]["version"], COMPONENT_API_VERSION)
        self.assertEqual(received[0]["request_id"], "request-1")
        self.assertEqual(received[0]["tenant_id"], "tenant-signed")
        self.assertEqual(received[0]["user_id"], "user-signed")
        with self.assertRaisesRegex(ValueError, "cannot override"):
            publish({
                "source_id": "source-1",
                "title": "Evidence",
                "url": "https://example.test/evidence",
                "tenant_id": "model-supplied",
            })

    def test_component_validates_required_payload(self):
        context = SkillRuntimeContext(
            runtime_manifest(),
            {
                "components": {
                    "search.evidence.publish": lambda value: value,
                },
            },
        )

        with self.assertRaisesRegex(ValueError, "requires fields"):
            context.component("search.evidence.publish")({
                "source_id": "source-1",
            })


if __name__ == "__main__":
    unittest.main()
