"""Makers Store adapter for typed search evidence."""

from __future__ import annotations

from collections.abc import Mapping

from agents._application.search.ports import EvidenceRecord
from agents._domain.search.evidence import SearchEvidence
from agents._infrastructure.makers.evidence_cache import (
    load_search_evidence,
    save_search_evidence,
)


def _to_cache_value(evidence: SearchEvidence) -> dict:
    return {
        "schema_version": 2,
        "query": evidence.query,
        "results": [source.to_dict() for source in evidence.sources],
        "media": [item.to_dict() for item in evidence.media],
        "preview_media": [],
        "images": [item.url for item in evidence.media],
        "sources_used": ["wsa"] if evidence.sources else [],
        "total": evidence.total,
        "media_pending": evidence.media_pending,
    }


class MakerEvidenceRepository:
    def __init__(self, store) -> None:
        self._store = store

    @property
    def flight_scope(self) -> int:
        return id(self._store)

    async def get(
        self,
        subject_id: str,
        cache_key: str,
    ) -> EvidenceRecord | None:
        value = await load_search_evidence(self._store, subject_id, cache_key)
        if value is None:
            return None
        return EvidenceRecord(
            evidence=SearchEvidence.from_dict(value),
            cache_hit=True,
            coalesced=False,
            metadata=value,
        )

    async def put(
        self,
        subject_id: str,
        cache_key: str,
        evidence: SearchEvidence,
        *,
        ttl_seconds: int,
        metadata: Mapping | None = None,
    ) -> None:
        await save_search_evidence(
            self._store,
            subject_id,
            cache_key,
            dict(metadata) if metadata is not None else _to_cache_value(evidence),
            ttl_seconds=ttl_seconds,
        )
