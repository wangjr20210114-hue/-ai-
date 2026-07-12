"""Search domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchRequest:
    query: str
    intent: str = "general"
    time_sensitive: bool = False
    depth: str = "standard"
    media_required: bool = True


@dataclass(slots=True)
class SearchBundle:
    query: str
    results: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    image_descriptions: list[dict[str, str]] = field(default_factory=list)
    media: list[dict[str, Any]] = field(default_factory=list)
    source_references: list[dict[str, Any]] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    total: int = 0

    def travel_candidates(self) -> list[dict[str, Any]]:
        candidates = []
        for r in self.results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if any(word in title + snippet for word in ["展", "博物馆", "景区", "餐厅", "酒店", "地址", "门票"]):
                candidates.append(r)
        return candidates
