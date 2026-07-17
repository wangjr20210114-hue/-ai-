"""Persistent Agent run, action, and notification APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from database.repositories import job_repo, runtime_repo
from database.repositories.runtime_repo import StateConflict

router = APIRouter(prefix="/api", tags=["agent-runtime"])


class ConfirmActionRequest(BaseModel):
    version: int = Field(ge=1)


class SnoozeNotificationRequest(BaseModel):
    until: float = Field(gt=0)


class NotificationPreferencesRequest(BaseModel):
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    daily_limit: int | None = Field(default=None, ge=0, le=500)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    enabled: bool | None = None


@router.get("/runs")
async def read_runs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"runs": await runtime_repo.list_runs(limit=limit, status=status)}


@router.get("/runs/{run_id}")
async def read_run(run_id: str) -> dict:
    run = await runtime_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": run}


@router.get("/actions")
async def read_actions(
    status: str | None = "awaiting_confirmation",
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    normalized = None if status in {None, "", "all"} else status
    return {"actions": await runtime_repo.list_actions(normalized, limit=limit)}


@router.get("/actions/{action_id}")
async def read_action(action_id: str) -> dict:
    action = await runtime_repo.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return {"action": action}


@router.post("/actions/{action_id}/confirm")
async def confirm_pending_action(
    action_id: str,
    body: ConfirmActionRequest,
    request: Request,
) -> dict:
    try:
        action = await request.app.state.action_service.confirm_action(action_id, body.version)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    request.app.state.agent_supervisor.wake()
    return {"action": action}


@router.post("/actions/{action_id}/cancel")
async def cancel_pending_action(action_id: str, request: Request) -> dict:
    try:
        action = await request.app.state.action_service.cancel_action(action_id)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"action": action}


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str, request: Request) -> dict:
    # Wake a process-local streaming call first; persistent cancellation remains
    # the source of truth and also handles queued work after a restart.
    await request.app.state.run_cancellation_service.cancel(run_id)
    try:
        run = await runtime_repo.cancel_run(run_id)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"run": run}


@router.post("/runs/{run_id}/retry")
async def retry_failed_run(run_id: str, request: Request) -> dict:
    try:
        run = await runtime_repo.retry_run(run_id)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    request.app.state.agent_supervisor.wake()
    return {"run": run}


@router.get("/notifications")
async def read_notifications(
    request: Request,
    since: float | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    notifications = await request.app.state.notification_service.list_since(since, limit)
    return {"notifications": notifications}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request) -> dict:
    item = await request.app.state.notification_service.mark_read(notification_id)
    if item is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"notification": item}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, request: Request) -> dict:
    item = await request.app.state.notification_service.dismiss(notification_id)
    if item is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"notification": item}


@router.post("/notifications/{notification_id}/snooze")
async def snooze_notification(
    notification_id: str,
    body: SnoozeNotificationRequest,
    request: Request,
) -> dict:
    item = await request.app.state.notification_service.snooze(notification_id, body.until)
    if item is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"notification": item}


@router.get("/notification-preferences")
async def read_notification_preferences(request: Request) -> dict:
    return {"preferences": await request.app.state.notification_service.get_preferences()}


@router.put("/notification-preferences")
async def update_notification_preferences(
    body: NotificationPreferencesRequest,
    request: Request,
) -> dict:
    changes = body.model_dump(exclude_none=True)
    return {
        "preferences": await request.app.state.notification_service.update_preferences(**changes)
    }


@router.get("/scheduled-jobs")
async def read_scheduled_jobs(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"jobs": await job_repo.list_jobs(limit)}


@router.post("/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str) -> dict:
    job = await job_repo.pause_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job}


@router.post("/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str, request: Request) -> dict:
    job = await job_repo.resume_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    request.app.state.agent_supervisor.wake()
    return {"job": job}
