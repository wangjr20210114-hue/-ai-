"""Pure cooldown policy rule."""
from __future__ import annotations


class CooldownRule:
    def evaluate(
        self,
        *,
        now: float,
        last_sent_at: float | None,
        cooldown_seconds: int,
        bypass: bool = False,
    ) -> tuple[bool, str]:
        if bypass or last_sent_at is None or cooldown_seconds <= 0:
            return True, "cooldown_not_applicable"
        if now - last_sent_at < cooldown_seconds:
            return False, "cooldown_active"
        return True, "cooldown_elapsed"
