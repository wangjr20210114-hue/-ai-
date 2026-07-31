from __future__ import annotations

import asyncio
import unittest

from agents._models.search_evidence import (
    assert_evidence_only,
    cacheable_evidence,
    evidence_ttl_seconds,
    force_refresh_requested,
    search_evidence_key,
)
from agents._shared.evidence_cache import (
    get_or_compute_search_evidence,
    load_search_evidence,
    save_search_evidence,
)


class FakeStore:
    def __init__(self):
        self.items = {}

    async def aget(self, namespace, key):
        value = self.items.get((tuple(namespace), key))
        return {"value": value} if value is not None else None

    async def aput(self, namespace, key, value):
        self.items[(tuple(namespace), key)] = value


def _key(query="稳定事实"):
    return search_evidence_key(
        query=query,
        image_query="",
        depth="standard",
        result_limit=8,
        image_limit=0,
        parallel_queries=True,
        target_date="",
        strict_date=False,
        include_media=False,
    )


def _metadata():
    return {
        "schema_version": 2,
        "query": "稳定事实",
        "results": [{
            "id": "source-1",
            "title": "来源",
            "url": "https://example.com/source",
            "snippet": "可复用事实证据",
        }],
        "media": [],
        "media_pending": False,
        "total": 1,
    }


class SearchEvidenceModelTests(unittest.TestCase):
    def test_cache_projection_never_accepts_answer_or_reasoning_fields(self):
        with self.assertRaisesRegex(ValueError, "final_answer"):
            assert_evidence_only({
                "results": [],
                "nested": {"final_answer": "固定回答"},
            })
        projected = cacheable_evidence({
            **_metadata(),
            "unrelated_runtime_handle": "not persisted",
        })
        self.assertNotIn("unrelated_runtime_handle", projected)
        self.assertNotIn("answer", projected)

    def test_volatile_evidence_uses_shorter_ttl(self):
        self.assertEqual(evidence_ttl_seconds("今天的最新新闻"), 120)
        self.assertEqual(evidence_ttl_seconds("稳定事实"), 600)
        self.assertEqual(evidence_ttl_seconds("稳定事实", depth="deep"), 900)

    def test_cache_key_tracks_evidence_constraints(self):
        self.assertNotEqual(_key("问题甲"), _key("问题乙"))

    def test_refresh_bypass_is_explicit_and_controller_deterministic(self):
        self.assertTrue(force_refresh_requested("请重新搜索，不要使用缓存"))
        self.assertTrue(force_refresh_requested("search again with fresh results"))
        self.assertFalse(force_refresh_requested("介绍一下浏览器缓存的原理"))


class SearchEvidenceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_evidence_is_scoped_by_user_and_expires(self):
        store = FakeStore()
        await save_search_evidence(
            store, "tenant:user-a", _key(), _metadata(),
            ttl_seconds=600, now=100,
        )
        self.assertEqual(
            (await load_search_evidence(
                store, "tenant:user-a", _key(), now=101,
            ))["total"],
            1,
        )
        self.assertIsNone(await load_search_evidence(
            store, "tenant:user-b", _key(), now=101,
        ))
        self.assertIsNone(await load_search_evidence(
            store, "tenant:user-a", _key(), now=701,
        ))

    async def test_identical_inflight_requests_share_one_provider_call(self):
        store = FakeStore()
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return _metadata()

        first, second = await asyncio.gather(
            get_or_compute_search_evidence(
                store, "tenant:user", _key(), compute, ttl_seconds=600,
            ),
            get_or_compute_search_evidence(
                store, "tenant:user", _key(), compute, ttl_seconds=600,
            ),
        )
        self.assertEqual(calls, 1)
        self.assertFalse(first.cache_hit)
        self.assertTrue(first.coalesced or second.coalesced)
        cached = await get_or_compute_search_evidence(
            store, "tenant:user", _key(), compute, ttl_seconds=600,
        )
        self.assertTrue(cached.cache_hit)
        self.assertEqual(calls, 1)

    async def test_pending_media_is_not_cached_without_a_background_job(self):
        store = FakeStore()
        pending = {**_metadata(), "media_pending": True}
        await save_search_evidence(
            store, "tenant:user", _key(), pending, ttl_seconds=600,
        )
        self.assertIsNone(await load_search_evidence(
            store, "tenant:user", _key(),
        ))

    async def test_explicit_refresh_bypasses_a_fresh_evidence_entry(self):
        store = FakeStore()
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            return {**_metadata(), "query": f"refresh-{calls}"}

        first = await get_or_compute_search_evidence(
            store, "tenant:user", _key(), compute, ttl_seconds=600,
        )
        refreshed = await get_or_compute_search_evidence(
            store, "tenant:user", _key(), compute, ttl_seconds=600,
            bypass_cache=True,
        )
        cached = await get_or_compute_search_evidence(
            store, "tenant:user", _key(), compute, ttl_seconds=600,
        )
        self.assertEqual(calls, 2)
        self.assertFalse(first.cache_hit)
        self.assertFalse(refreshed.cache_hit)
        self.assertEqual(cached.metadata["query"], "refresh-2")


if __name__ == "__main__":
    unittest.main()
