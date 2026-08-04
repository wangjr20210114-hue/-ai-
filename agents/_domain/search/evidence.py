"""Immutable, provider-independent search evidence values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class SearchSource:
    id: str
    title: str
    url: str
    snippet: str
    published_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required(self.id, "source id"))
        object.__setattr__(self, "url", _required(self.url, "source url"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "published_at": self.published_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SearchSource":
        return cls(
            id=str(value.get("id") or ""),
            title=str(value.get("title") or ""),
            url=str(value.get("url") or ""),
            snippet=str(value.get("snippet") or ""),
            published_at=str(value.get("published_at") or value.get("date") or ""),
        )


@dataclass(frozen=True, slots=True)
class ReviewedMedia:
    id: str
    url: str
    source_id: str
    source_url: str
    vision_reviewed: bool
    caption: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required(self.id, "media id"))
        object.__setattr__(self, "url", _required(self.url, "media url"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "vision_reviewed": self.vision_reviewed,
            "caption": self.caption,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewedMedia":
        return cls(
            id=str(value.get("id") or ""),
            url=str(value.get("url") or ""),
            source_id=str(value.get("source_id") or ""),
            source_url=str(value.get("source_url") or ""),
            vision_reviewed=value.get("vision_reviewed") is True,
            caption=str(value.get("caption") or value.get("alt") or ""),
        )


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    query: str
    sources: tuple[SearchSource, ...] = ()
    media: tuple[ReviewedMedia, ...] = ()
    total: int = 0
    media_pending: bool = False

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        media = tuple(self.media)
        source_ids = [source.id for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source id in search evidence")
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "media", media)
        object.__setattr__(self, "total", max(0, int(self.total or len(sources))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sources": [source.to_dict() for source in self.sources],
            "media": [item.to_dict() for item in self.media],
            "total": self.total,
            "media_pending": self.media_pending,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SearchEvidence":
        sources = value.get("sources")
        if not isinstance(sources, (list, tuple)):
            sources = value.get("results")
        media = value.get("media")
        return cls(
            query=str(value.get("query") or ""),
            sources=tuple(
                SearchSource.from_dict(item)
                for item in (sources or ())
                if isinstance(item, Mapping)
            ),
            media=tuple(
                ReviewedMedia.from_dict(item)
                for item in (media or ())
                if isinstance(item, Mapping)
            ),
            total=int(value.get("total") or 0),
            media_pending=value.get("media_pending") is True,
        )
