"""Leased persistent scheduler."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Awaitable, Callable

from database.repositories import job_repo

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JobExecutionResult:
    checkpoint: dict[str, Any] = field(default_factory=dict)
    next_run_at: float | None = None


JobHandler = Callable[[dict[str, Any]], Awaitable[JobExecutionResult | dict[str, Any] | None]]


class AgentScheduler:
    def __init__(self, handlers: dict[str, JobHandler]) -> None:
        self.handlers = handlers

    async def recover(self, *, now: float | None = None) -> int:
        return await job_repo.recover_expired_jobs(now=now)

    async def run_once(self, worker_id: str, lease_seconds: int = 60) -> bool:
        job = await job_repo.claim_due_job(worker_id, lease_seconds=lease_seconds)
        if job is None:
            return False
        handler = self.handlers.get(job["job_type"])
        if handler is None:
            await job_repo.fail_job(job["id"], f"unknown job type: {job['job_type']}")
            return True
        try:
            raw_result = await handler(job)
            if isinstance(raw_result, JobExecutionResult):
                outcome = raw_result
            else:
                outcome = JobExecutionResult(checkpoint=raw_result or {})
            await job_repo.complete_job(
                job["id"],
                checkpoint=outcome.checkpoint,
                next_run_at=outcome.next_run_at,
            )
        except Exception as error:
            logger.exception("scheduled job failed: %s", job["id"])
            await job_repo.fail_job(job["id"], f"{type(error).__name__}: {error}")
        return True
