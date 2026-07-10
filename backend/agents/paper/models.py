"""Paper domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PaperSearchRequest:
    topic: str
    user_message: str = ""
    max_results: int = 5
    year_from: int | None = None


@dataclass(slots=True)
class PaperBundle:
    topic: str
    papers: list[dict[str, Any]] = field(default_factory=list)
    source: str = "arxiv"