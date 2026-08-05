"""Turn-scoped rich-search orchestration.

The capability planner decides whether a turn may search.  This collaborator
then owns the single SearchUseCase execution, progressive media publication,
provider accounting, and the evidence payload returned to the answer graph.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import replace
from typing import Any

from .turn_context import search_request_for_plan
from ..search.search_use_case import SearchUseCase
from ..._infrastructure.makers.evidence_repository import MakerEvidenceRepository
from ..._infrastructure.makers.provider_usage_repository import (
    record_provider_usage,
    record_vision_diagnostics,
)
from ..._application.search.evidence_presenter import evidence_for_model
from ..._infrastructure.providers.searchpro import SearchProGateway
from ..._presenters.chat_stream import search_evidence_payload


def media_observability(metadata: dict | None) -> dict[str, int | str]:
    """Classify an empty media result without weakening source-bound safety."""
    value = metadata if isinstance(metadata, dict) else {}
    diagnostics = (
        value.get("vision_diagnostics")
        if isinstance(value.get("vision_diagnostics"), dict)
        else {}
    )
    media = value.get("media") if isinstance(value.get("media"), list) else []
    count = len(media)

    def number(key: str) -> int:
        try:
            return max(0, int(diagnostics.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    candidates = number("candidates")
    reviewed = number("reviewed")
    approved = number("approved")
    rejected = number("irrelevant") + number("promotional")
    if count:
        reason = "published"
    elif number("timeout"):
        reason = "timeout"
    elif candidates == 0:
        reason = "no_candidates"
    elif rejected and not approved:
        reason = "rejected"
    elif number("missing_api_key"):
        reason = "provider_unavailable"
    elif number("eligible_candidates") == 0:
        reason = "prefiltered"
    elif reviewed and not approved and not rejected:
        reason = "provider_failed"
    else:
        reason = "empty"
    return {
        "reason": reason,
        "count": count,
        "candidates": candidates,
        "reviewed": reviewed,
        "approved": approved,
        "rejected": rejected,
    }


class PlannedSearchRunner:
    """Execute at most one provider-backed rich search for a logical turn."""

    def __init__(
        self,
        *,
        ctx: Any,
        presenter: Any,
        queue: asyncio.Queue,
        capability_plan: dict,
        identity: dict,
        conversation_id: str,
        user_id: str,
        user_message: str,
        current_date: str,
        result_limit: int,
        image_limit: int,
        parallel_queries: bool,
        progressive_media: bool,
        runtime_env: dict,
        run_id: str,
        stage_timings_ms: dict,
        response_language: str,
    ) -> None:
        self._ctx = ctx
        self._presenter = presenter
        self._queue = queue
        self._capability_plan = capability_plan
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._run_id = run_id
        self._stage_timings_ms = stage_timings_ms
        self._response_language = response_language
        self.background_tasks: list[asyncio.Task] = []
        self.latest_enriched_media: dict | None = None
        self.media_diagnostics: dict[str, int | str] = {
            "reason": "not_requested",
            "count": 0,
            "candidates": 0,
            "reviewed": 0,
            "approved": 0,
            "rejected": 0,
        }

        time_sensitive = bool(capability_plan.get("needs_web_search"))
        self.temporal_context = {
            "target_date": current_date if time_sensitive else "",
            "strict_date": bool(capability_plan.get("strict_today_only")),
        }
        self.planned_request = search_request_for_plan(
            capability_plan,
            identity,
            conversation_id=conversation_id,
            user_message=user_message,
            current_date=current_date,
            result_limit=result_limit,
            image_limit=image_limit,
            parallel_queries=parallel_queries,
            # SearchUseCase persists evidence and coalesces a duplicate call
            # inside this turn, while chat never reuses an older turn's facts.
            force_refresh=True,
            progressive_media=progressive_media,
            response_language=response_language,
        )
        if self.planned_request is not None:
            self.planned_request = replace(
                self.planned_request,
                request_id=self._run_id,
            )
        self._use_case = (
            SearchUseCase(
                provider=SearchProGateway(runtime_env),
                repository=MakerEvidenceRepository(ctx.store.langgraph_store),
            )
            if self.planned_request is not None
            else None
        )

    def cancel(self) -> None:
        """Cancel only this turn's optional media work."""
        for task in self.background_tasks:
            if not task.done():
                task.cancel()

    async def finish_media(self, timeout: float = 90) -> str:
        """Drain progressive media before the public stream is marked done."""
        if not self.background_tasks:
            return "not_requested"
        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(*self.background_tasks, return_exceptions=True),
                timeout=timeout,
            )
            media_outcome = "completed"
            for task_outcome in outcomes:
                if isinstance(task_outcome, Exception):
                    logging.warning("rich search media task failed: %s", task_outcome)
                    media_outcome = "completed_with_errors"
                    self.media_diagnostics = {
                        **self.media_diagnostics,
                        "reason": "task_error",
                    }
            return media_outcome
        except asyncio.TimeoutError:
            logging.warning("rich search media task timed out")
            self.cancel()
            self.media_diagnostics = {
                **self.media_diagnostics,
                "reason": "timeout",
            }
            return "timeout"

    async def execute(
        self,
        query: str,
        image_query: str = "",
        depth: str = "standard",
    ) -> str:
        """Return trusted search evidence for the answer graph."""

        if self.planned_request is None or self._use_case is None:
            raise RuntimeError("rich search was not selected for this turn")
        clean_depth = depth if depth in {"basic", "standard", "deep"} else "standard"
        request = replace(
            self.planned_request,
            query=(self.planned_request.query or str(query or "").strip())[:500],
            image_query=(
                self.planned_request.image_query
                or str(image_query or "").strip()[:500]
            ),
            depth=clean_depth,
            force_refresh=True,
        )
        media_context: dict = {}

        async def publish_media(evidence) -> None:
            completed = {
                **media_context,
                **search_evidence_payload(evidence),
                "run_id": self._run_id,
                "conversation_id": self._conversation_id,
                "media_pending": False,
            }
            self.latest_enriched_media = completed
            self.media_diagnostics = media_observability(completed)
            logging.info(
                "rich_search media_audit request_id=%s reason=%s count=%s candidates=%s",
                self._run_id,
                self.media_diagnostics["reason"],
                self.media_diagnostics["count"],
                self.media_diagnostics["candidates"],
            )
            await self._queue.put(self._presenter.media(completed))

        search_started_at = time.monotonic()
        try:
            execution = await self._use_case.execute(
                request,
                on_media=publish_media,
            )
        except Exception as exc:
            self._stage_timings_ms["search"] = round(
                (time.monotonic() - search_started_at) * 1000
            )
            logging.warning(
                "rich_search failed request_id=%s conversation=%s error_type=%s elapsed_ms=%s",
                self._run_id,
                self._conversation_id,
                type(exc).__name__,
                self._stage_timings_ms["search"],
            )
            raise

        self._stage_timings_ms["search"] = round(
            (time.monotonic() - search_started_at) * 1000
        )
        metadata = dict(
            execution.metadata
            or search_evidence_payload(execution.evidence)
        )
        metadata.update({
            "run_id": self._run_id,
            "conversation_id": self._conversation_id,
        })
        media_context.update(metadata)
        search_config = dict(metadata.get("search_config") or {})
        metadata["search_config"] = {
            **search_config,
            "result_limit": request.result_limit,
            "image_limit": request.image_limit,
            "parallel_image_search": request.parallel_queries,
            "media_delivery": request.media_mode,
            "provider_request_count": execution.provider_request_count,
            "turn_provider_calls": execution.provider_request_count,
            "turn_tool_invocations": 1,
        }
        metadata["cache"] = {
            "kind": "evidence_only",
            "hit": execution.cache_hit,
            "coalesced": execution.coalesced,
            "answer_cached": False,
            "bypassed": True,
        }
        timings_ms = dict(metadata.get("timings_ms") or {})
        timings_ms["search"] = max(
            int(timings_ms.get("search") or 0),
            int(self._stage_timings_ms["search"]),
        )
        metadata["timings_ms"] = timings_ms
        media_context.update(metadata)
        self.background_tasks.extend(execution.media_tasks)
        if execution.provider_request_count:
            await record_provider_usage(
                self._ctx.store.langgraph_store,
                self._user_id,
                "wsa",
                "requests",
                execution.provider_request_count,
                source="search_use_case",
            )
        await record_vision_diagnostics(
            self._ctx.store.langgraph_store,
            self._user_id,
            metadata.get("vision_diagnostics"),
            source="rich_search_media",
        )
        logging.info(
            "rich_search turn_audit conversation=%s invocations=1 "
            "provider_calls=%s cache_hit=%s coalesced=%s",
            self._conversation_id,
            execution.provider_request_count,
            execution.cache_hit,
            execution.coalesced,
        )
        return json.dumps({
            "ui_action": "rich_search_results",
            "search_results": metadata,
            "papers": [],
            "evidence": evidence_for_model(
                metadata,
                response_language=self._response_language,
                require_relevant_image=bool(
                    self._capability_plan.get("needs_images")
                ),
            ),
        }, ensure_ascii=False)
