from __future__ import annotations

import json
import unittest

from agents._views.chat_progress import progress_event, tool_progress_event


class TrustedChatProgressTests(unittest.TestCase):
    def test_progress_is_controller_owned_fixed_schema(self):
        event = progress_event(
            "retrieval",
            "active",
            activity="web_search",
        )
        self.assertEqual(event["type"], "progress_event")
        self.assertEqual(event["payload"]["source"], "controller")
        serialized = json.dumps(event)
        for forbidden in (
            "reasoning",
            "chain_of_thought",
            "prompt",
            "tool_arguments",
            "model_output",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_tool_names_map_to_bounded_public_activities(self):
        self.assertEqual(
            tool_progress_event("rich_search", "active")["payload"],
            {
                "schema_version": 1,
                "stage": "retrieval",
                "status": "active",
                "activity": "web_search",
                "source": "controller",
            },
        )
        self.assertEqual(
            tool_progress_event("unknown_private_tool", "active")["payload"][
                "activity"
            ],
            "component_action",
        )

    def test_free_form_progress_values_are_rejected(self):
        with self.assertRaises(ValueError):
            progress_event("thinking about the user", "active")
        with self.assertRaises(ValueError):
            progress_event("planning", "model prose")


if __name__ == "__main__":
    unittest.main()
