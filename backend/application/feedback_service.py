"""Feedback loop for actions, notifications, and Agent runs."""
from __future__ import annotations

import time
from typing import Any

from database.repositories import feedback_repo


class FeedbackService:
    async def record_feedback(
        self,
        *,
        run_id: str | None,
        action_id: str | None,
        action: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_feedback_id: str = "",
    ) -> dict[str, Any]:
        record = await feedback_repo.record_feedback(
            run_id=run_id,
            action_id=action_id,
            feedback_action=action,
            reason=reason or "",
            metadata=metadata,
            client_feedback_id=client_feedback_id,
        )
        return {
            "feedback": record,
            "adjustment": await self.apply_adjustments(record),
        }

    async def apply_adjustments(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Create explainable suggestions; never silently rewrite user policy."""
        action = feedback.get("feedback_action")
        metadata = dict(feedback.get("metadata") or {})
        source_label = str(metadata.get("source_label") or "")
        suggestions: list[dict[str, Any]] = []
        if action in {"dismissed", "unhelpful"}:
            suggestions.extend(
                [
                    {
                        "type": "increase_cooldown",
                        "reason": "negative_feedback",
                        "requires_confirmation": True,
                    },
                    {
                        "type": "lower_source_priority",
                        "source_label": source_label,
                        "reason": "negative_feedback",
                        "requires_confirmation": True,
                    },
                ]
            )
            if source_label:
                count = await feedback_repo.count_recent_negative_feedback(
                    source_label, time.time() - 30 * 86400
                )
                if count >= 3:
                    suggestions.append(
                        {
                            "type": "pause_source_automation",
                            "source_label": source_label,
                            "reason": "three_negative_feedback_items_in_30_days",
                            "requires_confirmation": True,
                        }
                    )
        if action == "corrected":
            suggestions.append(
                {
                    "type": "propose_memory_correction",
                    "reason": "user_corrected_agent",
                    "requires_confirmation": True,
                }
            )
        return {
            "applied": False,
            "requires_user_confirmation": bool(suggestions),
            "suggestions": suggestions,
        }

    async def list_feedback(
        self,
        *,
        run_id: str | None = None,
        action_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await feedback_repo.list_feedback(
            run_id=run_id,
            action_id=action_id,
            limit=limit,
        )
