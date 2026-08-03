from __future__ import annotations

import json
import unittest

from agents._application.skills.component_api import (
    COMPONENT_API_VERSION,
    ComponentPublicationJournal,
)
from agents._infrastructure.skills.builtin_operations import (
    build_system_skill_tools,
)
from agents._skill_adapters._component_output import component_payloads
from agents._tests.support.fakes import FakeStore


class ComponentPublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_adapter_publishes_signed_component_out_of_band(self):
        journal = ComponentPublicationJournal()
        tools = build_system_skill_tools(
            object(),
            store=FakeStore(),
            conversation_id="component-conversation",
            request_id="component-run",
            user_id="component-user",
            identity={
                "auth_type": "guest",
                "membership": "guest",
                "tenant_id": "component-tenant",
                "user_id": "component-user",
            },
            component_journal=journal,
        )
        tool = next(
            value for value in tools
            if value.name == "ask_user_clarification"
        )

        raw_result = await tool.ainvoke({
            "title": "需要地点",
            "prompt": "请补充出发地",
            "fields": [{
                "id": "origin",
                "label": "出发地",
                "type": "text",
                "required": True,
            }],
        })

        self.assertNotIn("component-tenant", raw_result)
        self.assertNotIn("component-user", raw_result)
        signed = journal.signed_snapshot()
        self.assertEqual(len(signed), 1)
        self.assertEqual(signed[0]["version"], COMPONENT_API_VERSION)
        self.assertEqual(signed[0]["action"], "clarification.request")
        self.assertEqual(signed[0]["request_id"], "component-run")
        self.assertEqual(signed[0]["tenant_id"], "component-tenant")
        self.assertEqual(signed[0]["user_id"], "component-user")
        self.assertEqual(
            signed[0]["publication_key"],
            "ask_user_clarification",
        )

        self.assertEqual(journal.drain_public("other-tool"), [])
        self.assertEqual(len(journal.signed_snapshot()), 1)
        public = journal.drain_public("ask_user_clarification")
        self.assertEqual(public[0]["action"], "clarification.request")
        self.assertNotIn("tenant_id", public[0])
        self.assertNotIn("user_id", public[0])
        self.assertNotIn("publication_key", public[0])
        self.assertEqual(journal.signed_snapshot(), ())

    def test_search_publications_preserve_source_id_binding(self):
        result = json.dumps({
            "ui_action": "rich_search_results",
            "search_results": {
                "results": [{
                    "id": "source-1",
                    "title": "Verified source",
                    "url": "https://example.test/source",
                }],
                "media": [{
                    "id": "media-1",
                    "source_id": "source-1",
                    "url": "https://example.test/image.jpg",
                }, {
                    "id": "unbound-media",
                    "source_id": "missing-source",
                    "url": "https://example.test/unbound.jpg",
                }],
            },
        })

        evidence = component_payloads("search.evidence.publish", result)
        media = component_payloads("search.media.publish", result)

        self.assertEqual(evidence[0]["source_id"], "source-1")
        self.assertEqual(media[0]["source_id"], "source-1")
        self.assertEqual(media[0]["media"][0]["id"], "media-1")
        self.assertEqual(len(media), 1)

    def test_map_publication_uses_verified_action_payload(self):
        result = {
            "ui_action": "map_action",
            "action": {
                "payload": {
                    "places": [{"place_id": "place-1", "name": "Museum"}],
                },
            },
            "route": {"provider": "tencent", "legs": []},
        }

        publications = component_payloads("maps.place.select", result)

        self.assertEqual(publications[0]["places"][0]["place_id"], "place-1")
        self.assertEqual(publications[0]["route"]["provider"], "tencent")


if __name__ == "__main__":
    unittest.main()
