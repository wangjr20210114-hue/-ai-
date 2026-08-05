import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents._application.chat.turn_control import (
    committed_checkpoint_messages,
    turn_projection,
)


class TurnControlTests(unittest.TestCase):
    def test_projection_commits_only_a_completed_current_turn(self):
        current = {
            "client_message_id": "client-current",
            "status": "running",
            "discarded_client_message_ids": ["client-stopped"],
        }
        self.assertEqual(turn_projection(current, "client-old"), "committed")
        self.assertEqual(turn_projection(current, "client-current"), "pending")
        self.assertEqual(turn_projection(current, "client-stopped"), "discarded")
        self.assertEqual(
            turn_projection({**current, "status": "completed"}, "client-current"),
            "committed",
        )

    def test_model_history_excludes_every_stopped_turn_message(self):
        messages = [
            HumanMessage(
                content="old question",
                id="u-old",
                additional_kwargs={"floris_client_message_id": "client-old"},
            ),
            AIMessage(content="old answer", id="a-old"),
            HumanMessage(
                content="stopped question",
                id="u-stopped",
                additional_kwargs={"floris_client_message_id": "client-stopped"},
            ),
            ToolMessage(content="stopped tool", tool_call_id="tool-stopped"),
            AIMessage(content="stopped answer", id="a-stopped"),
            HumanMessage(
                content="next question",
                id="u-next",
                additional_kwargs={"floris_client_message_id": "client-next"},
            ),
        ]
        visible = committed_checkpoint_messages(messages, {
            "client_message_id": "client-next",
            "status": "running",
            "discarded_client_message_ids": ["client-stopped"],
        })
        self.assertEqual([item.id for item in visible], ["u-old", "a-old"])


if __name__ == "__main__":
    unittest.main()
