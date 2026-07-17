"""Notification inbox use cases with quiet hours, caps, and cooldown policy."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from database.repositories import notification_repo
from agent.policy import QuietHoursRule

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


class NotificationService:
    def __init__(self) -> None:
        self.quiet_hours_rule = QuietHoursRule()

    async def create_notification(self, **kwargs: Any) -> dict[str, Any]:
        preferences = await notification_repo.get_preferences()
        priority = int(kwargs.get("priority") or 0)
        notification_type = str(kwargs.get("notification_type") or "")
        source_label = str(kwargs.get("source_label") or "Agent")

        # Critical reconciliation/error notifications are never suppressed.
        bypass_limits = priority >= 90
        if not bool(preferences.get("enabled", 1)) and not bypass_limits:
            return {"suppressed": True, "reason": "notifications_disabled"}

        now = time.time()
        local_now = datetime.fromtimestamp(now, LOCAL_TZ)
        start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        if not bypass_limits:
            daily_limit = max(0, int(preferences.get("daily_limit") or 0))
            if daily_limit and await notification_repo.count_notifications_since(start_of_day) >= daily_limit:
                return {"suppressed": True, "reason": "daily_limit"}
            cooldown = max(0, int(preferences.get("cooldown_seconds") or 0))
            if (
                notification_type.startswith("proactive.")
                and cooldown
                and await notification_repo.has_recent_notification(
                    notification_type, source_label, now - cooldown
                )
            ):
                return {"suppressed": True, "reason": "cooldown"}

        snoozed_until = None
        if not bypass_limits:
            _, snoozed_until, _ = self.quiet_hours_rule.evaluate(
                now=local_now, preferences=preferences
            )
        notification, _ = await notification_repo.create_notification(
            **kwargs,
            snoozed_until=snoozed_until.timestamp() if snoozed_until else None,
        )
        return notification


    async def list_since(self, since: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return await notification_repo.list_notifications(since=since, limit=limit)

    async def mark_read(self, notification_id: str) -> dict[str, Any] | None:
        return await notification_repo.mark_read(notification_id)

    async def dismiss(self, notification_id: str) -> dict[str, Any] | None:
        return await notification_repo.dismiss(notification_id)

    async def snooze(self, notification_id: str, until: float) -> dict[str, Any] | None:
        return await notification_repo.snooze(notification_id, until)

    async def get_preferences(self) -> dict[str, Any]:
        return await notification_repo.get_preferences()

    async def update_preferences(self, **changes: Any) -> dict[str, Any]:
        return await notification_repo.update_preferences(**changes)
