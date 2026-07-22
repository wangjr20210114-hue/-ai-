from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents.conversation.index import handler
from agents._shared.data_version import CONVERSATION_PREFIX


class FakeConversationStore:
    def __init__(self):
        self.messages = []
        self.metadata = {}

    async def append_message(self, **value):
        self.messages.append(value)
        return "native-message-1"

    async def get_conversation(self, **_value):
        return SimpleNamespace(metadata=self.metadata)

    async def update_conversation(self, **value):
        self.metadata.update(value["metadata"])


class ConversationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_append_uses_native_makers_message_shape(self):
        store = FakeConversationStore()
        ctx = SimpleNamespace(
            conversation_id="conversation-role", env={},
            request=SimpleNamespace(body={"role": "ai", "content": "已恢复回答", "metadata": {"id": "client-ai-1"}}, headers={}),
            store=store,
        )
        response = await handler(ctx)
        self.assertEqual(response, {"message_id": "native-message-1"})
        self.assertEqual(store.messages[0]["role"], "assistant")
        self.assertEqual(store.messages[0]["conversation_id"], f"{CONVERSATION_PREFIX}conversation-role")
        self.assertEqual(store.messages[0]["metadata"]["client_message_id"], "client-ai-1")

    async def test_first_user_message_sets_native_conversation_title(self):
        store = FakeConversationStore()
        ctx = SimpleNamespace(
            conversation_id="conversation-title", env={},
            request=SimpleNamespace(body={"role": "user", "content": "最近AI有什么新进展", "metadata": {"id": "client-user-1"}}, headers={}),
            store=store,
        )
        await handler(ctx)
        self.assertEqual(store.metadata["title"], "最近AI有什么新进展")


if __name__ == "__main__":
    unittest.main()
