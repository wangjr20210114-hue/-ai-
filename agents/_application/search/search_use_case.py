"""Deterministic orchestration for one planned web search."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Awaitable, Literal

from agents._domain.search.evidence import SearchEvidence

from .ports import EvidenceRepository, MediaCallback, SearchPort


MediaMode = Literal["disabled", "progressive", "blocking"]
_CURRENT_MARKERS = re.compile(
    r"(今天|今日|现在|当前|最新|刚刚|近期|本周|today|current|latest|breaking|recent)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    tenant_id: str
    user_id: str
    conversation_id: str
    query: str
    image_query: str = ""
    depth: str = "standard"
    result_limit: int = 8
    image_limit: int = 0
    target_date: str = ""
    strict_date: bool = False
    force_refresh: bool = False
    media_mode: MediaMode = "progressive"

    def __post_init__(self) -> None:
        if not str(self.tenant_id or "").strip():
            raise ValueError("tenant_id must not be empty")
        if not str(self.user_id or "").strip():
            raise ValueError("user_id must not be empty")
        if not str(self.query or "").strip():
            raise ValueError("query must not be empty")
        if self.media_mode not in {"disabled", "progressive", "blocking"}:
            raise ValueError(f"unsupported media_mode: {self.media_mode}")
        object.__setattr__(self, "result_limit", max(4, min(18, int(self.result_limit))))
        object.__setattr__(self, "image_limit", max(0, min(8, int(self.image_limit))))
        if self.media_mode == "disabled":
            object.__setattr__(self, "image_limit", 0)

    @property
    def subject_id(self) -> str:
        return json.dumps(
            [self.tenant_id, self.user_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @property
    def cache_key(self) -> str:
        value = {
            "query": " ".join(self.query.casefold().split())[:500],
            "image_query": " ".join(self.image_query.casefold().split())[:500],
            "depth": self.depth,
            "result_limit": self.result_limit,
            "image_limit": self.image_limit,
            "target_date": self.target_date,
            "strict_date": self.strict_date,
            "include_media": self.media_mode != "disabled",
            "provider_version": "searchpro-v1",
        }
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SearchExecution:
    evidence: SearchEvidence
    media_tasks: tuple[Awaitable[SearchEvidence], ...] = ()
    cache_hit: bool = False
    coalesced: bool = False
    provider_request_count: int = 0

    @property
    def initial(self) -> SearchEvidence:
        return self.evidence


def _ttl_seconds(request: SearchRequest) -> int:
    if (
        request.strict_date
        or request.target_date
        or _CURRENT_MARKERS.search(request.query)
    ):
        return 2 * 60
    return 15 * 60 if request.depth == "deep" else 10 * 60


_FLIGHTS: dict[tuple[int, int, str, str], asyncio.Task[SearchExecution]] = {}


def _forget_flight(
    key: tuple[int, int, str, str],
    completed: asyncio.Task[SearchExecution],
) -> None:
    if _FLIGHTS.get(key) is completed:
        _FLIGHTS.pop(key, None)


class SearchUseCase:
    def __init__(
        self,
        *,
        provider: SearchPort,
        repository: EvidenceRepository,
    ) -> None:
        self._provider = provider
        self._repository = repository

    async def execute(
        self,
        request: SearchRequest,
        *,
        on_media: MediaCallback | None = None,
    ) -> SearchExecution:
        cache_key = request.cache_key
        if not request.force_refresh:
            record = await self._repository.get(request.subject_id, cache_key)
            if record is not None:
                return SearchExecution(
                    evidence=record.evidence,
                    cache_hit=record.cache_hit,
                    coalesced=record.coalesced,
                    provider_request_count=0,
                )

        async def persist_media(evidence: SearchEvidence) -> None:
            if not evidence.media_pending:
                await self._repository.put(
                    request.subject_id,
                    cache_key,
                    evidence,
                    ttl_seconds=_ttl_seconds(request),
                )
            if on_media is not None:
                await on_media(evidence)

        async def compute() -> SearchExecution:
            value = await self._provider.search(request, on_media=None)
            value = replace(
                value,
                media_tasks=tuple(
                    asyncio.ensure_future(media_task)
                    for media_task in value.media_tasks
                ),
            )
            if not value.evidence.media_pending:
                await self._repository.put(
                    request.subject_id,
                    cache_key,
                    value.evidence,
                    ttl_seconds=_ttl_seconds(request),
                )
            return value

        loop = asyncio.get_running_loop()
        scope = int(getattr(self._repository, "flight_scope", id(self._repository)))
        flight_cache_key = (
            f"refresh:{cache_key}" if request.force_refresh else cache_key
        )
        flight_key = (id(loop), scope, request.subject_id, flight_cache_key)
        task = _FLIGHTS.get(flight_key)
        coalesced = task is not None and not task.done()
        if not coalesced:
            task = asyncio.create_task(compute())
            _FLIGHTS[flight_key] = task
            task.add_done_callback(
                lambda completed, key=flight_key: _forget_flight(key, completed),
            )
        try:
            execution = await asyncio.shield(task)
        finally:
            if task.done() and _FLIGHTS.get(flight_key) is task:
                _FLIGHTS.pop(flight_key, None)

        media_tasks = tuple(
            asyncio.create_task(self._observe_media(task, persist_media))
            for task in execution.media_tasks
        )
        return replace(
            execution,
            media_tasks=media_tasks,
            cache_hit=False,
            coalesced=coalesced,
            provider_request_count=(
                0 if coalesced else execution.provider_request_count
            )
        )

    @staticmethod
    async def _observe_media(
        task: Awaitable[SearchEvidence],
        callback: MediaCallback,
    ) -> SearchEvidence:
        evidence = await task
        await callback(evidence)
        return evidence
