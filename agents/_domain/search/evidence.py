"""Immutable, provider-independent search evidence values."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _relevance_score(value: Any) -> float:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score)) if math.isfinite(score) else 0.0


@dataclass(frozen=True, slots=True)
class SearchSource:
    id: str
    title: str
    url: str
    snippet: str
    published_at: str = ""
    publisher: str = ""
    relevance_score: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required(self.id, "source id"))
        object.__setattr__(self, "url", _required(self.url, "source url"))
        object.__setattr__(self, "publisher", str(self.publisher or "").strip())
        object.__setattr__(
            self, "relevance_score", _relevance_score(self.relevance_score),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "publisher": self.publisher,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SearchSource":
        return cls(
            id=str(value.get("id") or ""),
            title=str(value.get("title") or ""),
            url=str(value.get("url") or ""),
            snippet=str(value.get("snippet") or ""),
            published_at=str(value.get("published_at") or value.get("date") or ""),
            publisher=str(value.get("publisher") or value.get("site") or ""),
            relevance_score=_relevance_score(
                value.get("relevance_score") or value.get("score") or 0
            ),
        )


@dataclass(frozen=True, slots=True)
class ReviewedMedia:
    id: str
    url: str
    source_id: str
    source_url: str
    vision_reviewed: bool
    caption: str = ""
    source_bound_fallback: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required(self.id, "media id"))
        object.__setattr__(self, "url", _required(self.url, "media url"))

    def to_dict(self) -> dict[str, Any]:
        value = {
            "id": self.id,
            "url": self.url,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "vision_reviewed": self.vision_reviewed,
            "caption": self.caption,
        }
        if self.source_bound_fallback:
            value["source_bound_fallback"] = True
        return value

    @property
    def trusted_for_display(self) -> bool:
        """Allow pixel-reviewed media or an exact provider source hero."""
        return self.vision_reviewed or self.source_bound_fallback

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewedMedia":
        return cls(
            id=str(value.get("id") or ""),
            url=str(value.get("url") or ""),
            source_id=str(value.get("source_id") or ""),
            source_url=str(value.get("source_url") or ""),
            vision_reviewed=value.get("vision_reviewed") is True,
            caption=str(value.get("caption") or value.get("alt") or ""),
            source_bound_fallback=value.get("source_bound_fallback") is True,
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
