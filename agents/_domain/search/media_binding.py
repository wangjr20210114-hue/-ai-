"""Fail-closed binding of reviewed media to deterministic source identities."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import ReviewedMedia, SearchEvidence, SearchSource


@dataclass(frozen=True, slots=True)
class MediaBinding:
    media: ReviewedMedia
    source: SearchSource

    @property
    def source_id(self) -> str:
        return self.source.id


def bind_reviewed_media(evidence: SearchEvidence) -> tuple[MediaBinding, ...]:
    """Bind only trusted media whose source ID and URL agree exactly."""
    sources = {source.id: source for source in evidence.sources}
    return tuple(
        MediaBinding(media=item, source=sources[item.source_id])
        for item in evidence.media
        if item.trusted_for_display
        and item.source_id in sources
        and item.source_url == sources[item.source_id].url
    )
