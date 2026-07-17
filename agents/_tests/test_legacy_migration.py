from __future__ import annotations

import unittest

from agents._shared.legacy_migration import import_message_batch, import_state_bundle
from agents._shared.workspace import load_user_workspace, save_user_workspace


EXPORT_ID = "sqlite_0123456789abcdef01234567"


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeConversationStore:
    def __init__(self):
        self.messages = []
        self.conversations = {}

    async def append_message(self, **value):
        self.messages.append(value)
        return f"msg_{len(self.messages)}"

    async def update_conversation(self, **value):
        self.conversations[value["conversation_id"]] = value["metadata"]


class LegacyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_import_is_non_destructive_and_idempotent(self):
        store = FakeStore()
        current = await load_user_workspace(store, user_id="local-user")
        current["schedules"]["current"] = {"id": "current", "title": "保留"}
        await save_user_workspace(store, current, "local-user")
        bundle = {
            "user_id": "local-user",
            "workspace": {"schedules": {"legacy": {"id": "legacy", "title": "迁移"}}},
            "proactive": {"events": {}, "runs": {}, "notifications": {}, "observations": []},
            "intelligence": {"memories": {}, "memory_proposals": {}, "feedback": [], "usage": []},
        }
        first = await import_state_bundle(store, "local-user", EXPORT_ID, bundle)
        second = await import_state_bundle(store, "local-user", EXPORT_ID, bundle)
        restored = await load_user_workspace(store, user_id="local-user")
        self.assertEqual(first["status"], "done")
        self.assertTrue(second["idempotent"])
        self.assertEqual(set(restored["schedules"]), {"current", "legacy"})

    async def test_conflicting_state_is_not_overwritten(self):
        store = FakeStore()
        current = await load_user_workspace(store, user_id="local-user")
        current["schedules"]["same"] = {"id": "same", "title": "当前"}
        await save_user_workspace(store, current, "local-user")
        result = await import_state_bundle(store, "local-user", EXPORT_ID, {
            "user_id": "local-user",
            "workspace": {"schedules": {"same": {"id": "same", "title": "旧值"}}},
        })
        restored = await load_user_workspace(store, user_id="local-user")
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(restored["schedules"]["same"]["title"], "当前")

    async def test_message_import_uses_conversation_store_once(self):
        state_store = FakeStore()
        conversations = FakeConversationStore()
        batch = [{"id": "m1", "role": "ai", "content": "历史回答", "metadata": {}}]
        first = await import_message_batch(
            conversations, state_store, user_id="local-user", export_id=EXPORT_ID,
            conversation_id="c1", messages=batch, title="历史会话",
        )
        second = await import_message_batch(
            conversations, state_store, user_id="local-user", export_id=EXPORT_ID,
            conversation_id="c1", messages=batch, title="历史会话",
        )
        self.assertEqual(first["imported"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(len(conversations.messages), 1)
        self.assertEqual(conversations.messages[0]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
