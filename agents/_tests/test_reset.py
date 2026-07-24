import unittest
from types import SimpleNamespace

from agents._shared.data_version import namespace
from agents._shared.intelligence import DEFAULT_SKILL_PREFERENCES
from agents.reset.index import handler


class FakeLangGraphStore:
    def __init__(self):
        self.values = {
            (namespace("intelligence", "local-user"), "state"): {
                "skill_preferences": {
                    **DEFAULT_SKILL_PREFERENCES,
                    "web-search": False,
                    "calendar": False,
                },
                "memories": {"memory-1": {"value": "remove"}},
            },
            (namespace("workspace", "local-user"), "state"): {
                "schedules": {"schedule-1": {"title": "remove"}},
            },
            (namespace("proactive", "local-user"), "state"): {
                "notifications": {"notification-1": {"title": "remove"}},
            },
        }

    async def aget(self, namespace_value, key):
        value = self.values.get((tuple(namespace_value), key))
        return {"value": value} if value is not None else None

    async def abatch(self, _operations):
        return []

    async def aput(self, namespace_value, key, value):
        self.values[(tuple(namespace_value), key)] = value

    async def alist_namespaces(self, *, limit=100, offset=0):
        namespaces = sorted({item[0] for item in self.values})
        return namespaces[offset:offset + limit]

    async def asearch(self, namespace_prefix, *, limit=100, **_kwargs):
        output = []
        for (namespace_value, key), value in self.values.items():
            if namespace_value[:len(namespace_prefix)] == tuple(namespace_prefix):
                output.append(SimpleNamespace(namespace=namespace_value, key=key, value=value))
        return output[:limit]

    async def adelete(self, namespace_value, key):
        self.values.pop((tuple(namespace_value), key), None)


class FakeCheckpointer:
    def __init__(self):
        self.deleted = []

    async def adelete_thread(self, conversation_id):
        self.deleted.append(conversation_id)


class FakeConversationStore:
    def __init__(self, langgraph_store):
        self.langgraph_store = langgraph_store
        self.langgraph_checkpointer = FakeCheckpointer()
        self.conversations = ["yb7_first", "yb7_second"]


def context(password):
    langgraph_store = FakeLangGraphStore()
    store = FakeConversationStore(langgraph_store)
    return SimpleNamespace(
        env={"DATA_CLEAR_PASSWORD": "configured-secret"},
        request=SimpleNamespace(body={
            "password": password,
            "conversation_ids": ["yb7_first", "yb7_second"],
        }),
        store=store,
    )


class ResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_password_changes_nothing(self):
        ctx = context("wrong")
        response = await handler(ctx)
        self.assertEqual(response["status_code"], 403)
        self.assertEqual(response["body"]["code"], "INVALID_PASSWORD")
        self.assertEqual(ctx.store.conversations, ["yb7_first", "yb7_second"])

    async def test_reset_clears_data_and_preserves_only_skill_preferences(self):
        ctx = context("configured-secret")
        response = await handler(ctx)
        self.assertTrue(response["ok"])
        self.assertIn("asyncio", FakeLangGraphStore.abatch.__globals__)
        self.assertEqual(response["checkpoints_deleted"], 2)
        self.assertEqual(set(ctx.store.langgraph_checkpointer.deleted), {"yb7_first", "yb7_second"})

        intelligence_item = await ctx.store.langgraph_store.aget(
            namespace("intelligence", "local-user"), "state",
        )
        intelligence = intelligence_item["value"]
        self.assertFalse(intelligence["skill_preferences"]["web-search"])
        self.assertFalse(intelligence["skill_preferences"]["calendar"])
        self.assertEqual(intelligence["memories"], {})
        self.assertEqual(intelligence["feedback"], [])
        self.assertEqual(
            len(ctx.store.langgraph_store.values),
            1,
            "only the rebuilt intelligence state should remain",
        )

    async def test_reset_deletes_checkpoints_for_large_history(self):
        ctx = context("configured-secret")
        conversation_ids = [f"yb7_conversation_{index}" for index in range(20)]
        ctx.request.body["conversation_ids"] = conversation_ids
        response = await handler(ctx)
        self.assertEqual(response["checkpoints_deleted"], 20)
        self.assertEqual(ctx.store.langgraph_checkpointer.deleted, conversation_ids)


if __name__ == "__main__":
    unittest.main()
