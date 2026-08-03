"""Deterministic fake for the planned-search critical-path contract."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from agents._application.search.ports import EvidenceRecord
from agents._application.search.search_use_case import (
    SearchExecution,
    SearchRequest,
    SearchUseCase,
)
from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)


@dataclass(frozen=True, slots=True)
class FakeLatency:
    plan_ms: int = 50
    search_ms: int = 250
    answer_first_token_ms: int = 100
    media_review_ms: int = 1500


@dataclass(frozen=True, slots=True)
class CriticalPathMetrics:
    plan_ms: float
    sources_ms: float
    first_token_ms: float
    media_complete_ms: float
    provider_requests: int
    graph_tool_names: tuple[str, ...]
    event_order: tuple[str, ...]


class _Repository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], SearchEvidence] = {}

    async def get(
        self,
        subject_id: str,
        cache_key: str,
    ) -> EvidenceRecord | None:
        value = self.records.get((subject_id, cache_key))
        return EvidenceRecord(value, cache_hit=True, coalesced=False) if value else None

    async def put(
        self,
        subject_id: str,
        cache_key: str,
        evidence: SearchEvidence,
        *,
        ttl_seconds: int,
        metadata=None,
    ) -> None:
        del ttl_seconds, metadata
        self.records[(subject_id, cache_key)] = evidence


class _Provider:
    def __init__(self, latency: FakeLatency) -> None:
        self._latency = latency
        self.calls = 0

    async def search(self, request: SearchRequest, *, on_media=None) -> SearchExecution:
        del on_media
        self.calls += 1
        await asyncio.sleep(self._latency.search_ms / 1000)
        source = SearchSource(
            id="source-1",
            title="redacted benchmark source",
            url="https://example.invalid/source-1",
            snippet="redacted evidence",
        )

        async def review_media() -> SearchEvidence:
            await asyncio.sleep(self._latency.media_review_ms / 1000)
            return SearchEvidence(
                query=request.query,
                sources=(source,),
                media=(
                    ReviewedMedia(
                        id="media-1",
                        url="https://example.invalid/media-1.jpg",
                        source_id=source.id,
                        source_url=source.url,
                        vision_reviewed=True,
                    ),
                ),
                total=1,
            )

        if request.media_mode == "blocking":
            return SearchExecution(
                evidence=await review_media(),
                provider_request_count=1,
            )
        return SearchExecution(
            evidence=SearchEvidence(
                query=request.query,
                sources=(source,),
                total=1,
                media_pending=True,
            ),
            media_tasks=(review_media(),),
            provider_request_count=1,
        )


async def run_fake_critical_path(
    turn_index: int,
    *,
    latency: FakeLatency = FakeLatency(),
) -> CriticalPathMetrics:
    """Run one fake turn without retaining its query or any credentials."""
    started_at = time.perf_counter()
    events: list[str] = []
    await asyncio.sleep(latency.plan_ms / 1000)
    plan_ms = (time.perf_counter() - started_at) * 1000
    events.append("plan")

    provider = _Provider(latency)
    media_completed_ms = 0.0

    async def on_media(_evidence: SearchEvidence) -> None:
        nonlocal media_completed_ms
        media_completed_ms = (time.perf_counter() - started_at) * 1000
        events.append("media")

    execution = await SearchUseCase(
        provider=provider,
        repository=_Repository(),
    ).execute(
        SearchRequest(
            tenant_id="benchmark",
            user_id=f"user-{turn_index}",
            conversation_id=f"turn-{turn_index}",
            query=f"redacted-query-{turn_index}",
            image_query="redacted-image-query",
            result_limit=8,
            image_limit=2,
            force_refresh=True,
            media_mode="blocking",
        ),
        on_media=on_media,
    )
    if execution.evidence.media:
        media_completed_ms = (time.perf_counter() - started_at) * 1000
        events.append("media")
    sources_ms = (time.perf_counter() - started_at) * 1000
    events.append("sources")

    tools = ("rich_search",)
    await asyncio.sleep(latency.answer_first_token_ms / 1000)
    first_token_ms = (time.perf_counter() - started_at) * 1000
    events.append("token")

    await asyncio.gather(*execution.media_tasks)
    return CriticalPathMetrics(
        plan_ms=plan_ms,
        sources_ms=sources_ms,
        first_token_ms=first_token_ms,
        media_complete_ms=media_completed_ms,
        provider_requests=provider.calls,
        graph_tool_names=tools,
        event_order=tuple(events),
    )
