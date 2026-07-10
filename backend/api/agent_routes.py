"""M2 persistent Agent run and pending action APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database.repositories.runtime_repo import (
    StateConflict,
    cancel_action,
    confirm_action,
    get_run,
    list_actions,
    retry_run,
)

router = APIRouter(prefix="/api", tags=["agent-runtime"])


class ConfirmActionRequest(BaseModel):
    version: int = Field(ge=1)


@router.get("/runs/{run_id}")
async def read_run(run_id: str) -> dict:
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": run}


@router.get("/actions")
async def read_actions(status: str = "awaiting_confirmation") -> dict:
    return {"actions": await list_actions(status)}


@router.post("/actions/{action_id}/confirm")
async def confirm_pending_action(action_id: str, request: ConfirmActionRequest) -> dict:
    try:
        action = await confirm_action(action_id, request.version)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"action": action}


@router.post("/actions/{action_id}/cancel")
async def cancel_pending_action(action_id: str) -> dict:
    try:
        action = await cancel_action(action_id)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"action": action}


@router.post("/runs/{run_id}/retry")
async def retry_failed_run(run_id: str) -> dict:
    try:
        run = await retry_run(run_id)
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"run": run}
