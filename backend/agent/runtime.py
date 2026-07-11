"""Agent runtime and audit trail."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.contracts import AgentObservation, AgentPlan, ExecutionStatus, new_id
from agent.events import AgentEvent


@dataclass(slots=True)
class AgentRun:
    run_id: str
    session_id: str
    event_type: str
    status: ExecutionStatus = ExecutionStatus.CREATED
    intent: str = ""
    plan: AgentPlan | None = None
    observations: list[AgentObservation] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class AgentRuntime:
    """In-memory run registry.

    It is intentionally isolated behind a class so it can later be replaced by a
    database-backed audit table without changing the orchestrator.
    """

    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._session_index: dict[str, list[str]] = {}

    def start_run(self, event: AgentEvent) -> AgentRun:
        run = AgentRun(
            run_id=new_id("run"),
            session_id=event.session_id,
            event_type=event.type,
        )
        self._runs[run.run_id] = run
        self._session_index.setdefault(event.session_id, []).append(run.run_id)
        self.observe(run, ExecutionStatus.CREATED, step="event_received", payload={"text": event.text[:120]})
        return run

    def attach_plan(self, run: AgentRun, plan: AgentPlan) -> None:
        run.plan = plan
        run.intent = plan.intent
        self.observe(
            run,
            ExecutionStatus.PLANNED,
            intent=plan.intent,
            step="plan_created",
            payload={
                "params": plan.params,
                "permission_level": plan.permission_level.value,
                "risk_level": plan.risk_level.value,
                "steps": plan.steps,
            },
        )

    def observe(
        self,
        run: AgentRun,
        status: ExecutionStatus,
        *,
        intent: str = "",
        step: str = "",
        message: str = "",
        payload: dict[str, Any] | None = None,
        error: str = "",
    ) -> AgentObservation:
        run.status = status
        item = AgentObservation(
            run_id=run.run_id,
            session_id=run.session_id,
            status=status,
            intent=intent or run.intent,
            step=step,
            message=message,
            payload=payload or {},
            error=error,
        )
        run.observations.append(item)
        return item

    def finish(self, run: AgentRun, status: ExecutionStatus, *, error: str = "") -> None:
        run.status = status
        run.ended_at = time.time()
        self.observe(run, status, step="run_finished", error=error)

    def get_run(self, run_id: str) -> AgentRun | None:
        return self._runs.get(run_id)

    def get_session_runs(self, session_id: str, limit: int = 50) -> list[AgentRun]:
        ids = self._session_index.get(session_id, [])[-limit:]
        return [self._runs[i] for i in ids if i in self._runs]

class PersistentRuntime:
    """Async facade over the persistent runtime repository.

    The legacy ``AgentRuntime`` above remains available for isolated unit tests and
    compatibility, while production orchestration uses this class exclusively.
    """

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        from database.repositories import runtime_repo

        return await runtime_repo.get_run(run_id)

    async def start_run(
        self,
        event_id: str,
        *,
        max_attempts: int = 1,
        execution_lane: str = "interactive",
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.create_run(
            event_id,
            max_attempts=max_attempts,
            execution_lane=execution_lane,
        )

    async def set_classification(
        self,
        run_id: str,
        intent: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.set_run_classification(run_id, intent, payload)

    async def set_plan(
        self,
        run_id: str,
        plan: dict[str, Any],
        *,
        execution_lane: str,
        max_attempts: int,
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.set_run_plan(
            run_id,
            plan,
            execution_lane=execution_lane,
            max_attempts=max_attempts,
        )

    async def transition(
        self,
        run_id: str,
        expected_status: str,
        new_status: str,
        *,
        step: str,
        payload: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.transition_run(
            run_id,
            new_status,
            expected_status=expected_status,
            step=step,
            payload=payload,
            error=error,
        )

    async def append_observation(
        self,
        run_id: str,
        *,
        step: str,
        payload: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.append_observation(
            run_id,
            step=step,
            payload=payload,
            error=error,
        )

    async def claim_run(
        self,
        run_id: str,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> dict[str, Any] | None:
        from database.repositories import runtime_repo

        return await runtime_repo.claim_run(run_id, worker_id, lease_seconds)

    async def claim_queued_run(
        self,
        worker_id: str,
        lease_seconds: int = 60,
        *,
        execution_lane: str = "background",
    ) -> dict[str, Any] | None:
        from database.repositories import runtime_repo

        return await runtime_repo.claim_queued_run(
            worker_id,
            lease_seconds,
            execution_lane=execution_lane,
        )

    async def complete(self, run_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.complete_run(run_id, result)

    async def fail(
        self,
        run_id: str,
        error: str,
        *,
        retryable: bool = False,
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.fail_run(run_id, error, retryable=retryable)

    async def cancel(
        self,
        run_id: str,
        *,
        reason: str = "cancelled_by_user",
    ) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.cancel_run(run_id, reason=reason)

    async def fail_if_possible(self, run_id: str, error: str) -> dict[str, Any] | None:
        from database.repositories import runtime_repo

        run = await runtime_repo.get_run(run_id)
        if run is None or run["status"] in runtime_repo.TERMINAL_RUN_STATUSES:
            return run
        if "failed" not in runtime_repo.RUN_TRANSITIONS.get(run["status"], set()):
            return await runtime_repo.append_observation(run_id, step="unhandled_error", error=error)
        return await runtime_repo.transition_run(
            run_id,
            "failed",
            expected_status=run["status"],
            step="run_failed",
            error=error,
        )

    async def recover_expired_runs(self, *, now: float | None = None) -> dict[str, Any]:
        from database.repositories import runtime_repo

        return await runtime_repo.recover_expired_runs(now=now)
