"""Pure quiet-hours deferral rule."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class QuietHoursRule:
    def evaluate(
        self,
        *,
        now: datetime,
        preferences: dict[str, Any],
        bypass: bool = False,
    ) -> tuple[bool, datetime | None, str]:
        if bypass:
            return True, None, "priority_bypass"
        try:
            start_hour, start_minute = map(
                int, str(preferences.get("quiet_hours_start") or "23:00").split(":", 1)
            )
            end_hour, end_minute = map(
                int, str(preferences.get("quiet_hours_end") or "08:00").split(":", 1)
            )
        except (TypeError, ValueError):
            return True, None, "invalid_quiet_hours_configuration"
        start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if start == end:
            return True, None, "quiet_hours_disabled"
        if start < end:
            if start <= now < end:
                return False, end, "quiet_hours"
            return True, None, "outside_quiet_hours"
        if now >= start:
            return False, end + timedelta(days=1), "quiet_hours"
        if now < end:
            return False, end, "quiet_hours"
        return True, None, "outside_quiet_hours"
