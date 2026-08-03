"""Ports consumed by the search application use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol, TYPE_CHECKING

from agents._domain.search.evidence import SearchEvidence

if TYPE_CHECKING:
    from .search_use_case import SearchExecution, SearchRequest


MediaCallback = Callable[[SearchEvidence], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence: SearchEvidence
    cache_hit: bool
    coalesced: bool
    metadata: Mapping[str, Any] | None = None


class SearchPort(Protocol):
    async def search(
        self,
        request: "SearchRequest",
        *,
        on_media: MediaCallback | None = None,
    ) -> "SearchExecution": ...


class EvidenceRepository(Protocol):
    async def get(
        self,
        subject_id: str,
        cache_key: str,
    ) -> EvidenceRecord | None: ...

    async def put(
        self,
        subject_id: str,
        cache_key: str,
        evidence: SearchEvidence,
        *,
        ttl_seconds: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> None: ...
