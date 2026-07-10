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