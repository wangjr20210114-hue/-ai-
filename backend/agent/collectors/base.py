"""Collector contracts.

Collectors only observe external/local state and return normalized signals. They
must not create notifications, execute skills, or mutate Agent Run state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CollectedSignal:
    event_type: str
    source: str
    dedup_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    subject_id: str | None = None
    occurred_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "dedup_key": self.dedup_key,
            "payload": self.payload,
            "subject_id": self.subject_id,
            "occurred_at": self.occurred_at,
        }


@dataclass(slots=True)
class CollectionBatch:
    """Atomic collector output.

    ``next_checkpoint`` is committed only after every event in ``events`` has
    been processed successfully. ``next_run_at`` lets a collector request a more
    appropriate next scan without mutating scheduler state directly.
    """

    events: list[CollectedSignal] = field(default_factory=list)
    next_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_run_at: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        """Compatibility for older callers that unpacked ``events, checkpoint``."""
        yield self.events
        yield self.next_checkpoint


class Collector(Protocol):
    name: str

    async def collect(
        self,
        checkpoint: dict[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> CollectionBatch:
        """Return an idempotent collection batch without performing side effects."""
