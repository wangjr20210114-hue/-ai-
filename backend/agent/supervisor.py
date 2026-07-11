"""Background supervisor for durable Agent execution."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from agent.executor import AgentExecutor
from agent.runtime import PersistentRuntime
from agent.scheduler import AgentScheduler
from database.repositories import job_repo, runtime_repo

logger = logging.getLogger(__name__)


class AgentSupervisor:
    def __init__(
        self,
        *,
        runtime: PersistentRuntime,
        executor: AgentExecutor,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 120,
        scheduler: AgentScheduler | None = None,
        maintenance_interval_seconds: float = 30.0,
    ) -> None:
        self.runtime = runtime
        self.executor = executor
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.lease_seconds = max(10, lease_seconds)
        self.scheduler = scheduler
        self.maintenance_interval_seconds = max(1.0, maintenance_interval_seconds)
        self.worker_id = f"supervisor-{uuid.uuid4().hex[:10]}"
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._started_at: float | None = None
        self._last_iteration_at: float | None = None
        self._last_success_at: float | None = None
        self._last_error: str = ""
        self._iterations = 0
        self._work_count = 0
        self._last_maintenance_at: float | None = None
        self._last_maintenance_report: dict = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> dict:
        recovery = await self.maintain(force=True)
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._started_at = time.time()
            self._last_error = ""
            self._task = asyncio.create_task(self._run_loop(), name="agent-supervisor")
        return recovery

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def wake(self) -> None:
        self._wake_event.set()

    async def health(self) -> dict:
        """Return an operational snapshot without mutating the worker."""
        run_counts, action_counts = await asyncio.gather(
            runtime_repo.count_runs_by_status(),
            runtime_repo.count_actions_by_status(),
        )
        job_counts = await job_repo.count_jobs_by_status() if self.scheduler is not None else {}
        now = time.time()
        heartbeat_age = (
            round(now - self._last_iteration_at, 3)
            if self._last_iteration_at is not None
            else None
        )
        state = "ok" if self.running and not self._last_error else "degraded"
        if not self.running:
            state = "stopped"
        return {
            "status": state,
            "running": self.running,
            "worker_id": self.worker_id,
            "started_at": self._started_at,
            "last_iteration_at": self._last_iteration_at,
            "last_success_at": self._last_success_at,
            "heartbeat_age_seconds": heartbeat_age,
            "last_error": self._last_error,
            "last_maintenance_at": self._last_maintenance_at,
            "last_maintenance_report": self._last_maintenance_report,
            "iterations": self._iterations,
            "work_count": self._work_count,
            "queues": {
                "runs": run_counts,
                "actions": action_counts,
                "jobs": job_counts,
            },
        }


    async def maintain(self, *, force: bool = False) -> dict:
        """Recover expired leases and reconcile durable provider outcomes.

        Maintenance runs at startup and periodically while the process remains up,
        so a crashed worker cannot leave an executing Run stuck until the next restart.
        """
        now = time.time()
        if (
            not force
            and self._last_maintenance_at is not None
            and now - self._last_maintenance_at < self.maintenance_interval_seconds
        ):
            return self._last_maintenance_report

        recovery = await self.runtime.recover_expired_runs(now=now)
        if self.scheduler is not None:
            recovery["scheduled_jobs_recovered"] = await self.scheduler.recover(now=now)
        reconciliation = {
            "scanned": 0,
            "succeeded": 0,
            "failed": 0,
            "unknown": 0,
            "errors": [],
        }
        for action in await runtime_repo.list_actions(status="executing", limit=500):
            if not action.get("reconciliation_required"):
                continue
            reconciliation["scanned"] += 1
            try:
                outcome = await self.executor.reconcile_unknown_side_effect(action)
                status = str(outcome.get("status") or "unknown")
                if status not in {"succeeded", "failed", "unknown"}:
                    status = "unknown"
                reconciliation[status] += 1
            except Exception as error:  # one damaged action must not block the worker
                logger.exception("side-effect reconciliation failed: action=%s", action.get("id"))
                reconciliation["errors"].append(
                    {
                        "action_id": action.get("id"),
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        recovery["reconciliation"] = reconciliation
        self._last_maintenance_at = now
        self._last_maintenance_report = recovery
        return recovery


    async def run_once(self) -> bool:
        await self.maintain()
        run = await self.runtime.claim_queued_run(
            self.worker_id,
            self.lease_seconds,
            execution_lane="background",
        )
        if run is not None:
            await self.executor.execute_run(
                run,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            return True
        if self.scheduler is not None:
            return await self.scheduler.run_once(self.worker_id, self.lease_seconds)
        return False

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._last_iteration_at = time.time()
                self._iterations += 1
                worked = await self.run_once()
                self._last_success_at = time.time()
                self._last_error = ""
                if worked:
                    self._work_count += 1
                    continue
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(), timeout=self.poll_interval_seconds
                    )
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {error}"
                logger.exception("agent supervisor iteration failed")
                await asyncio.sleep(self.poll_interval_seconds)
