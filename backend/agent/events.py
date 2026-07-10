"""Agent event models.

The current app only sends user_activity through WebSocket, but the event model is
kept generic so future proactive sources can plug in without changing the
orchestrator contract.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


class EventType:
    USER_ACTIVITY = "user_activity"
    SCHEDULE_TICK = "schedule_tick"
    FILE_UPLOADED = "file_uploaded"
    WEATHER_CHANGED = "weather_changed"
    WEBPAGE_OBSERVED = "webpage_observed"


@dataclass(slots=True)
class AgentEvent:
    type: str
    session_id: str
    text: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    @classmethod
    def user_activity(
        cls, session_id: str, text: str, payload: dict[str, Any] | None = None
    ) -> "AgentEvent":
        return cls(
            type=EventType.USER_ACTIVITY,
            session_id=session_id,
            text=text,
            payload=payload or {},
        )