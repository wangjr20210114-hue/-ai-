"""Application boundary for ingesting signals and starting Agent runs."""
from __future__ import annotations

import time
import uuid
from typing import Any

from agent.context import AgentContext
from agent.events import AgentEvent
from agent.orchestrator import AgentOrchestrator
from agent.runtime import PersistentRuntime
from database.repositories import runtime_repo
from database.repositories.conversation_repo import save_message


class AgentApplicationService:
    def __init__(self, *, runtime: PersistentRuntime, orchestrator: AgentOrchestrator) -> None:
        self.runtime = runtime
        self.orchestrator = orchestrator

    async def handle_user_message(
        self,
        *,
        conversation_id: str,
        text: str,
        websocket: Any,
        context: AgentContext,
        payload: dict[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> dict[str, Any]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("message text is required")
        message_id = client_message_id or f"user-{uuid.uuid4().hex[:16]}"

        # Durability invariant: the user message is committed before the Agent run.
        await save_message(
            conversation_id,
            message_id,
            "user",
            clean_text,
            metadata={"source": "websocket", "client_message_id": message_id},
        )
        event, created = await runtime_repo.create_event(
            "user.message",
            {
                "conversation_id": conversation_id,
                "text": clean_text,
                "message_id": message_id,
                "client_payload": payload or {},
            },
            dedup_key=f"user-message:{conversation_id}:{message_id}",
            source="user",
            subject_id=conversation_id,
            occurred_at=time.time(),
        )
        run = await runtime_repo.get_run_for_event(event["id"])
        if run is None:
            run = await self.runtime.start_run(event["id"], execution_lane="interactive")
        elif not created and run["status"] in runtime_repo.TERMINAL_RUN_STATUSES | {
            "waiting_confirmation",
            "queued",
            "executing",
        }:
            return run

        agent_event = AgentEvent(
            type="user_activity",
            session_id=conversation_id,
            text=clean_text,
            payload={**(payload or {}), "message_id": message_id, "event_id": event["id"]},
            ts=float(event["occurred_at"]),
        )
        await self.orchestrator.handle_user_activity(
            websocket,
            agent_event,
            context,
            run_id=run["id"],
        )
        await runtime_repo.mark_event_processed(event["id"])
        latest = await self.runtime.get_run(run["id"])
        if latest is None:
            raise RuntimeError("run disappeared after processing")
        return latest

    async def ingest_external_event(
        self,
        *,
        event_type: str,
        source: str,
        subject_id: str | None,
        payload: dict[str, Any],
        dedup_key: str,
        occurred_at: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        event, created = await runtime_repo.create_event(
            event_type,
            payload,
            dedup_key,
            source=source,
            subject_id=subject_id,
            occurred_at=occurred_at,
        )
        run = await runtime_repo.get_run_for_event(event["id"])
        if run is None:
            run = await self.runtime.start_run(event["id"], execution_lane="background")
        return event, run, created
