from __future__ import annotations

import unittest

from agents._tests.support import (
    FakeComponentPublisher,
    FakeMakerStore,
    FakeModel,
    FakeSearchPort,
    assert_no_side_effect,
    deterministic_clock,
    deterministic_ids,
    signed_identity,
)


class SupportContractTests(unittest.IsolatedAsyncioTestCase):
    def test_clock_and_ids_are_deterministic(self):
        clock = deterministic_clock()
        identifiers = deterministic_ids("run")
        self.assertEqual(clock(), clock())
        self.assertEqual([next(identifiers), next(identifiers)], ["run-0001", "run-0002"])

    def test_signed_identity_is_explicit_and_tenant_scoped(self):
        identity = signed_identity(tenant_id="tenant-b", user_id="user-2", membership="plus")
        self.assertTrue(identity.trusted)
        self.assertEqual(identity.subject_id, "tenant-b:user-2")
        self.assertEqual(identity.membership, "plus")

    async def test_fake_model_and_search_port_record_async_calls(self):
        model = FakeModel(output={"content": "ok"})
        search = FakeSearchPort(results=[{"id": "source-1"}])
        self.assertEqual(await model.ainvoke(["hello"]), {"content": "ok"})
        self.assertEqual(await search.search("query", limit=3), [{"id": "source-1"}])
        self.assertEqual(model.calls, [["hello"]])
        self.assertEqual(search.calls[0]["options"], {"limit": 3})

    async def test_fake_maker_store_never_crosses_tenants(self):
        store = FakeMakerStore()
        await store.put("tenant-a", "workspace", {"revision": 1})
        self.assertEqual(await store.get("tenant-a", "workspace"), {"revision": 1})
        self.assertIsNone(await store.get("tenant-b", "workspace"))

    async def test_component_publisher_records_trusted_boundary(self):
        publisher = FakeComponentPublisher()
        record = await publisher.publish("tenant-a", "calendar.propose", {"title": "Review"})
        self.assertEqual(record["tenant_id"], "tenant-a")
        self.assertEqual(publisher.calls, [record])

    def test_no_side_effect_assertion_checks_recorded_calls(self):
        assert_no_side_effect(self, FakeComponentPublisher())


if __name__ == "__main__":
    unittest.main()
