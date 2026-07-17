"""Process collector signals through persistent run state and notification policy."""
from __future__ import annotations

from typing import Any

from agent.opportunity import OpportunityDetector
from agent.runtime import PersistentRuntime
from application.notification_service import NotificationService
from database.repositories import runtime_repo


class ProactiveEventService:
    def __init__(
        self,
        *,
        runtime: PersistentRuntime,
        notifications: NotificationService,
        detector: OpportunityDetector | None = None,
    ) -> None:
        self.runtime = runtime
        self.notifications = notifications
        self.detector = detector or OpportunityDetector()

    async def process_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        event, created = await runtime_repo.create_event(
            str(signal["event_type"]),
            dict(signal.get("payload") or {}),
            str(signal["dedup_key"]),
            source=str(signal.get("source") or "collector"),
            subject_id=signal.get("subject_id"),
            occurred_at=signal.get("occurred_at"),
        )
        run = await runtime_repo.get_run_for_event(event["id"])
        if run is None:
            run = await self.runtime.start_run(event["id"], execution_lane="background")
        if not created and run["status"] in runtime_repo.TERMINAL_RUN_STATUSES:
            return run

        opportunity = self.detector.detect(event)
        if opportunity is None:
            if run["status"] == "created":
                await self.runtime.set_classification(run["id"], "none", {"matched": False})
                await self.runtime.set_plan(
                    run["id"],
                    {"schema_version": 1, "intent": "none", "steps": ["ignore"]},
                    execution_lane="background",
                    max_attempts=1,
                )
                await self.runtime.transition(
                    run["id"], "planned", "policy_checked", step="proactive_policy_checked"
                )
                await self.runtime.transition(
                    run["id"], "policy_checked", "skipped", step="no_opportunity"
                )
            await runtime_repo.mark_event_processed(event["id"])
            latest = await self.runtime.get_run(run["id"])
            return latest or run

        if run["status"] == "created":
            await self.runtime.set_classification(
                run["id"], opportunity.intent, {"detector": "deterministic", "matched": True}
            )
            await self.runtime.set_plan(
                run["id"],
                {
                    "schema_version": 1,
                    "intent": opportunity.intent,
                    "event_type": event["type"],
                    "steps": ["evaluate_notification_policy", "deliver_notification"],
                    "opportunity": {
                        "title": opportunity.title,
                        "body": opportunity.body,
                        "reason": opportunity.reason,
                        "source_label": opportunity.source_label,
                        "priority": opportunity.priority,
                        "metadata": opportunity.metadata,
                    },
                },
                execution_lane="background",
                max_attempts=1,
            )
            await self.runtime.transition(
                run["id"],
                "planned",
                "policy_checked",
                step="proactive_policy_checked",
                payload={"allowed": True, "requires_confirmation": False},
            )
            await self.runtime.transition(
                run["id"],
                "policy_checked",
                "queued",
                step="notification_queued",
            )

        claimed = await self.runtime.claim_run(run["id"], "proactive-event-service", 30)
        if claimed is None:
            latest = await self.runtime.get_run(run["id"])
            return latest or run
        notification = await self.notifications.create_notification(
            notification_type=f"proactive.{opportunity.intent}",
            title=opportunity.title,
            body=opportunity.body,
            dedup_key=f"notification:{event['dedup_key']}",
            run_id=run["id"],
            event_id=event["id"],
            reason=opportunity.reason,
            source_label=opportunity.source_label,
            priority=opportunity.priority,
            metadata=opportunity.metadata,
        )
        await self.runtime.complete(
            run["id"],
            {"notification_id": notification.get("id"), "suppressed": notification.get("suppressed", False)},
        )
        await runtime_repo.mark_event_processed(event["id"])
        latest = await self.runtime.get_run(run["id"])
        return latest or run
