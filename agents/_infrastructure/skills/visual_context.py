"""Turn-local visual references shared by trusted search and image adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(slots=True)
class TurnVisualContext:
    """Keep reviewed visual handoffs explicit and bounded to one chat turn."""

    references: list[str] = field(default_factory=list)
    image_group_id: str = ""

    @classmethod
    def from_initial(cls, values: Iterable[str] | None) -> "TurnVisualContext":
        context = cls()
        context.add(values or (), allow_data_urls=True)
        return context

    def add(
        self,
        values: Iterable[str],
        *,
        allow_data_urls: bool = False,
    ) -> None:
        allowed_prefixes = ("https://", "data:image/") if allow_data_urls else ("https://",)
        reviewed = [
            str(value)
            for value in values
            if str(value).startswith(allowed_prefixes)
        ]
        self.references = list(dict.fromkeys([
            *self.references,
            *reviewed,
        ]))[:3]


__all__ = ("TurnVisualContext",)
