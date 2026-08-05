"""Optional work that runs beside the public answer stream."""

from __future__ import annotations

import asyncio
from typing import Any

from .turn_io import _recent_user_questions
from ...chat._followups import (
    generate_followups,
    has_early_followup_grounding,
    should_generate_followups,
)
from ..._application.intelligence.service import extract_automatic_memory_candidates


class FollowupPrefetch:
    """Start suggestions once the public answer has enough grounding."""

    def __init__(
        self,
        model: Any,
        user_message: str,
        response_language: str,
        *,
        enabled: bool,
    ) -> None:
        self._model = model
        self._user_message = user_message
        self._response_language = response_language
        self.enabled = enabled
        self.task: asyncio.Task | None = None

    def maybe_start(self, answer: str, *, clarification_emitted: bool) -> None:
        if (
            self.task is not None
            or not self.enabled
            or clarification_emitted
            or not has_early_followup_grounding(answer)
        ):
            return
        self.task = asyncio.create_task(generate_followups(
            self._model,
            self._user_message,
            answer=answer,
            response_language=self._response_language,
        ))

    def discard(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = None


class TurnBackgroundWork:
    """Own optional latency work and expose its tasks to finalization."""

    def __init__(
        self,
        followups: FollowupPrefetch,
        memory_task: asyncio.Task | None,
        recent_questions_task: asyncio.Task | None,
        opportunity_enabled: bool,
    ) -> None:
        self.followups = followups
        self.memory_task = memory_task
        self.recent_questions_task = recent_questions_task
        self.opportunity_enabled = opportunity_enabled

    @classmethod
    def start(
        cls,
        *,
        model: Any,
        message: str,
        response_language: str,
        capability_plan: dict[str, Any],
        blocked_skill: str,
        intelligence: dict[str, Any],
        enabled_capabilities: set[str],
        store: Any,
        conversation_id: str,
        run_state: dict[str, Any],
    ) -> "TurnBackgroundWork":
        followups = FollowupPrefetch(
            model,
            message,
            response_language,
            enabled=should_generate_followups(
                capability_plan,
                blocked_skill=blocked_skill,
            ),
        )
        memory_enabled = bool(
            (intelligence.get("memory_preferences") or {}).get("enabled", True)
        )
        memory_task = (
            asyncio.create_task(extract_automatic_memory_candidates(
                model,
                message,
                response_language=response_language,
            ))
            if memory_enabled and capability_plan.get("needs_memory_extraction")
            else None
        )
        opportunity_enabled = bool(
            "workflow_action" in enabled_capabilities
            and capability_plan.get("needs_opportunity_review")
        )
        recent_questions_task = (
            asyncio.create_task(_recent_user_questions(
                store,
                conversation_id,
                message,
                run_state,
            ))
            if opportunity_enabled
            else None
        )
        return cls(
            followups,
            memory_task,
            recent_questions_task,
            opportunity_enabled,
        )
