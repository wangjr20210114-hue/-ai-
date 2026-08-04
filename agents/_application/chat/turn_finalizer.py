"""Turn completion orchestration after public answer streaming finishes."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .turn_context import experience_hints_for_plan
from .turn_policy import empty_generation_error, run_cancelled
from ...chat._followups import generate_followups
from ..._application.intelligence.service import (
    apply_automatic_memory_candidates,
    load_intelligence_state,
    record_usage,
    save_intelligence_state,
)
from ..._application.proactive.opportunities import (
    detect_opportunity,
    opportunity_signal,
)
from ..._application.proactive.service import (
    load_proactive_state,
    process_schedule_signals,
    public_proactive_state,
    save_proactive_state,
)
from ..._infrastructure.makers.conversation_repository import (
    read_chat_run,
    write_chat_run,
)
from ..._infrastructure.makers.data_version import namespace as data_namespace


class TurnFinalizer:
    """Publish and persist one turn's terminal protocol in a stable order."""

    def __init__(
        self,
        *,
        ctx: Any,
        presenter: Any,
        queue: asyncio.Queue,
        completion_sentinel: object,
        search_runner: Any,
        fast_model: Any,
        message: str,
        response_language: str,
        conversation_id: str,
        user_id: str,
        run_id: str,
        body: dict[str, Any],
        identity: dict[str, Any],
        capability_plan: dict[str, Any],
        answer_capability_plan: dict[str, Any],
        memory_context: str,
        pending_actions: list[dict[str, Any]],
        followups_enabled: bool,
        memory_task: asyncio.Task | None,
        recent_questions_task: asyncio.Task | None,
        opportunity_enabled: bool,
        telemetry: Any,
    ) -> None:
        self._ctx = ctx
        self._presenter = presenter
        self._queue = queue
        self._completion_sentinel = completion_sentinel
        self._search_runner = search_runner
        self._fast_model = fast_model
        self._message = message
        self._response_language = response_language
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._run_id = run_id
        self._body = body
        self._identity = identity
        self._capability_plan = capability_plan
        self._answer_capability_plan = answer_capability_plan
        self._memory_context = memory_context
        self._pending_actions = pending_actions
        self._followups_enabled = followups_enabled
        self._memory_task = memory_task
        self._recent_questions_task = recent_questions_task
        self._opportunity_enabled = opportunity_enabled
        self._telemetry = telemetry

    def _experience_hints(self) -> list[dict[str, Any]]:
        return experience_hints_for_plan(
            self._answer_capability_plan,
            auth_type=str(self._identity.get("auth_type") or "guest"),
        )

    async def _persist_answer_extras(
        self,
        answer: str,
        follow_ups: list[str] | None = None,
    ) -> None:
        """Persist terminal UI data through the Makers message namespace."""
        store = self._ctx.store.langgraph_store
        hints = self._experience_hints()
        search_results = self._search_runner.latest_enriched_media
        if not answer or store is None or not (follow_ups or search_results or hints):
            return
        await store.aput(
            data_namespace("message_meta", self._conversation_id),
            "latest_extras",
            {
                "original_content": answer,
                "content": answer,
                "follow_ups": follow_ups or [],
                "experience_hints": hints,
                **(
                    {"search_results": search_results}
                    if search_results
                    else {}
                ),
            },
        )

    async def _publish_answer_completion(
        self,
        answer: str,
        *,
        clarification_emitted: bool,
        run_error: str,
    ) -> list[str]:
        for stage in ("synthesis", "finalizing", "complete"):
            await self._queue.put(self._presenter.progress(stage, "completed"))
        hints = self._experience_hints()
        if hints:
            await self._queue.put(self._presenter.experience_hints(hints))
        # End the visible answer cursor before optional chips are generated.
        await self._queue.put(self._presenter.done(self._run_id))

        follow_ups: list[str] = []
        if self._followups_enabled and not clarification_emitted and not run_error:
            try:
                follow_ups = await asyncio.wait_for(
                    generate_followups(
                        self._fast_model,
                        self._message,
                        answer=answer,
                        response_language=self._response_language,
                    ),
                    timeout=3,
                )
            except Exception as exc:
                logging.warning("grounded follow-up generation failed: %s", exc)
        if follow_ups:
            await self._queue.put(self._presenter.follow_ups(follow_ups))
        try:
            await self._persist_answer_extras(answer, follow_ups)
        except Exception as exc:
            logging.warning("answer follow-up persistence failed: %s", exc)
        return follow_ups

    async def _apply_optional_intelligence(self, answer: str) -> None:
        recent_questions: list[str] = []
        if self._recent_questions_task is not None:
            try:
                recent_questions = await asyncio.wait_for(
                    asyncio.shield(self._recent_questions_task),
                    timeout=1.5,
                )
            except Exception:
                recent_questions = []
        opportunity_task = (
            asyncio.create_task(detect_opportunity(
                self._fast_model,
                user_message=self._message,
                answer=answer,
                capability_plan=self._capability_plan,
                memory_context=(
                    self._memory_context
                    if self._capability_plan.get("use_memory_context")
                    else ""
                ),
                recent_questions=recent_questions,
                has_pending_action=any(
                    action.get("action", {}).get("status")
                    in {"awaiting_confirmation", "ready"}
                    for action in self._pending_actions
                ),
                timeout_seconds=float(
                    self._ctx.env.get("OPPORTUNITY_PLAN_TIMEOUT_SECONDS") or 6
                ),
                response_language=self._response_language,
            ))
            if self._opportunity_enabled
            else None
        )
        optional_jobs = [
            task
            for task in (self._memory_task, opportunity_task)
            if task is not None
        ]
        optional_results = await asyncio.wait_for(
            asyncio.gather(*optional_jobs),
            timeout=8,
        )
        result_index = 0
        memory_candidates = []
        opportunity = None
        if self._memory_task is not None:
            memory_candidates = optional_results[result_index]
            result_index += 1
        if opportunity_task is not None:
            opportunity = optional_results[result_index]

        if memory_candidates:
            intelligence = await load_intelligence_state(
                self._ctx.store.langgraph_store,
                self._user_id,
            )
            if apply_automatic_memory_candidates(
                intelligence,
                memory_candidates,
                source_message_id=str(self._body.get("client_message_id") or ""),
            ):
                await save_intelligence_state(
                    self._ctx.store.langgraph_store,
                    intelligence,
                    self._user_id,
                )
        if opportunity and self._ctx.store.langgraph_store is not None:
            now = int(time.time())
            proactive_state = await load_proactive_state(
                self._ctx.store.langgraph_store,
                self._user_id,
            )
            source_id = str(
                self._body.get("client_message_id") or self._run_id
            )
            stats = process_schedule_signals(
                proactive_state,
                [opportunity_signal(opportunity, source_id=source_id, now=now)],
                now,
            )
            if stats.get("notifications_created"):
                proactive_state.setdefault("checkpoints", {})[
                    "semantic_opportunity"
                ] = {
                    "last_detected_at": now,
                    "type": opportunity.get("type"),
                    "source_id": source_id,
                }
                proactive_state = await save_proactive_state(
                    self._ctx.store.langgraph_store,
                    proactive_state,
                    self._user_id,
                )
                await self._queue.put(self._presenter.proactive_update(
                    public_proactive_state(proactive_state),
                ))

    async def _finish_run(
        self,
        run_error: str,
        cancelled: bool,
        run_diagnostics: dict[str, Any],
    ) -> None:
        latest_run = await read_chat_run(self._ctx.store, self._conversation_id)
        owns_run = not (
            isinstance(latest_run, dict)
            and latest_run.get("run_id")
            and str(latest_run.get("run_id")) != self._run_id
        )
        if owns_run:
            cancelled = cancelled or run_cancelled(latest_run)
            await write_chat_run(
                self._ctx.store,
                self._conversation_id,
                run_id=self._run_id,
                status=(
                    "cancelled"
                    if cancelled
                    else "failed"
                    if run_error
                    else "completed"
                ),
                error=run_error,
                diagnostics=run_diagnostics,
            )

    async def _persist_usage(self, usage: list[int]) -> None:
        if not any(usage):
            return
        try:
            intelligence = await load_intelligence_state(
                self._ctx.store.langgraph_store,
                self._user_id,
            )
            total = usage[2] or usage[0] + usage[1]
            record_usage(intelligence, usage[0], usage[1], total, "chat")
            await save_intelligence_state(
                self._ctx.store.langgraph_store,
                intelligence,
                self._user_id,
            )
        except Exception as exc:
            logging.warning("usage persistence failed: %s", exc)
        await self._queue.put(self._presenter.usage(
            usage[0],
            usage[1],
            usage[2] or usage[0] + usage[1],
        ))

    async def finish(
        self,
        *,
        answer: str,
        run_error: str,
        run_diagnostics: dict[str, Any],
        cancelled: bool,
        clarification_emitted: bool,
        pending_search_results: dict[str, Any] | None,
        pending_papers: dict[str, Any] | None,
        usage: list[int],
    ) -> None:
        """Finish media, UI events, durable state, and usage exactly once."""
        terminal_outcome = (
            "cancelled" if cancelled else "failed" if run_error else "completed"
        )
        try:
            empty_error = empty_generation_error(
                answer,
                has_actions=bool(self._pending_actions),
                clarification_emitted=clarification_emitted,
                run_error=run_error,
                cancelled=cancelled,
                response_language=self._response_language,
            )
            if empty_error:
                run_error = empty_error
                terminal_outcome = "failed"
                await self._queue.put(self._presenter.error(
                    "empty_generation",
                    run_error,
                ))
            media_outcome = await self._search_runner.finish_media()
            if media_outcome != "not_requested":
                self._telemetry.media_completed(
                    media_outcome,
                    self._search_runner.media_diagnostics,
                )
            if answer and self._search_runner.latest_enriched_media:
                try:
                    await self._persist_answer_extras(answer)
                except Exception as exc:
                    logging.warning("answer media persistence failed: %s", exc)

            if answer:
                await self._publish_answer_completion(
                    answer,
                    clarification_emitted=clarification_emitted,
                    run_error=run_error,
                )
            else:
                for task in (self._memory_task, self._recent_questions_task):
                    if task is not None and not task.done():
                        task.cancel()

            if answer and (
                self._memory_task is not None or self._opportunity_enabled
            ):
                try:
                    await self._apply_optional_intelligence(answer)
                except Exception as exc:
                    logging.warning("answer extras generation failed: %s", exc)
            if pending_search_results is not None:
                await self._queue.put(
                    self._presenter.sources(pending_search_results)
                )
            if pending_papers is not None:
                await self._queue.put(self._presenter.papers(pending_papers))
            await self._finish_run(run_error, cancelled, run_diagnostics)
            await self._persist_usage(usage)
        except Exception:
            terminal_outcome = "failed"
            raise
        finally:
            self._telemetry.settle(terminal_outcome)
            if bool(self._body.get("_diagnostics")):
                await self._queue.put(
                    self._presenter.stage_timing(self._telemetry.timings_ms)
                )
            await self._queue.put(self._completion_sentinel)
