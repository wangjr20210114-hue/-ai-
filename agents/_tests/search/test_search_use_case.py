from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from agents._application.search.ports import EvidenceRecord
from agents._application.search.search_use_case import (
    SearchExecution,
    SearchRequest,
    SearchUseCase,
)
from agents._domain.search.evidence import SearchEvidence, SearchSource


def evidence(query: str = "Floris 架构") -> SearchEvidence:
    return SearchEvidence(
        query=query,
        sources=(
            SearchSource(
                id="source-1",
                title="架构资料",
                url="https://example.test/architecture",
                snippet="经过检索的事实",
            ),
        ),
        total=1,
    )


class FakeSearchPort:
    def __init__(self, *, delay: float = 0):
        self.calls = 0
        self.requests: list[SearchRequest] = []
        self.delay = delay

    async def search(self, request, *, on_media=None):
        self.calls += 1
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        return SearchExecution(
            evidence=evidence(request.query),
            provider_request_count=1,
        )


class InMemoryEvidenceRepository:
    def __init__(self):
        self.records: dict[tuple[str, str], SearchEvidence] = {}

    async def get(self, subject_id, cache_key):
        value = self.records.get((subject_id, cache_key))
        return EvidenceRecord(value, cache_hit=True, coalesced=False) if value else None

    async def put(self, subject_id, cache_key, value, *, ttl_seconds):
        self.records[(subject_id, cache_key)] = value


def request(*, force_refresh: bool = False) -> SearchRequest:
    return SearchRequest(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        query="Floris 架构",
        image_query="Floris 架构图",
        depth="standard",
        result_limit=8,
        image_limit=0,
        force_refresh=force_refresh,
        media_mode="disabled",
    )


class SearchUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_calls_provider_once_and_never_caches_answer(self):
        provider = FakeSearchPort()
        repository = InMemoryEvidenceRepository()
        use_case = SearchUseCase(provider=provider, repository=repository)

        first = await use_case.execute(request())
        second = await use_case.execute(request())

        self.assertEqual(provider.calls, 1)
        self.assertIsNot(first, second)
        self.assertEqual(first.evidence, second.evidence)
        self.assertFalse(hasattr(first, "answer"))
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)

    async def test_explicit_refresh_bypasses_cached_evidence(self):
        provider = FakeSearchPort()
        use_case = SearchUseCase(
            provider=provider,
            repository=InMemoryEvidenceRepository(),
        )

        await use_case.execute(request())
        refreshed = await use_case.execute(request(force_refresh=True))

        self.assertEqual(provider.calls, 2)
        self.assertFalse(refreshed.cache_hit)

    async def test_cache_is_scoped_by_tenant_and_user(self):
        provider = FakeSearchPort()
        use_case = SearchUseCase(
            provider=provider,
            repository=InMemoryEvidenceRepository(),
        )
        other_tenant = replace(request(), tenant_id="tenant-b")

        await use_case.execute(request())
        await use_case.execute(other_tenant)

        self.assertEqual(provider.calls, 2)

    def test_subject_scope_cannot_collide_on_colon_delimited_ids(self):
        first = replace(request(), tenant_id="tenant:a", user_id="user")
        second = replace(request(), tenant_id="tenant", user_id="a:user")

        self.assertNotEqual(first.subject_id, second.subject_id)

    def test_blocking_and_progressive_media_share_completed_evidence_key(self):
        progressive = replace(request(), image_limit=2, media_mode="progressive")
        blocking = replace(request(), image_limit=2, media_mode="blocking")

        self.assertEqual(progressive.cache_key, blocking.cache_key)

    async def test_identical_inflight_requests_share_one_provider_call(self):
        provider = FakeSearchPort(delay=0.01)
        use_case = SearchUseCase(
            provider=provider,
            repository=InMemoryEvidenceRepository(),
        )

        first, second = await asyncio.gather(
            use_case.execute(request()),
            use_case.execute(request()),
        )

        self.assertEqual(provider.calls, 1)
        self.assertTrue(first.coalesced or second.coalesced)
        self.assertEqual(
            first.provider_request_count + second.provider_request_count,
            1,
        )


if __name__ == "__main__":
    unittest.main()
