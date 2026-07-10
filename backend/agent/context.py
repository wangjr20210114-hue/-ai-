"""Session context passed through the Agent runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentContext:
    session_id: str
    history: list[str]
    user_profile: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def last_user_messages(self, limit: int = 8) -> list[str]:
        return [item for item in self.history if item.startswith("用户: ")][-limit:]