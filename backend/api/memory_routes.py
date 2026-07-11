"""User-controlled long-term memory APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from database.repositories.memory_repo import MemoryConflict

router = APIRouter(prefix="/api", tags=["memories"])


class MemoryCandidateRequest(BaseModel):
    source_message_id: str = Field(default="", max_length=200)
    key: str = Field(min_length=1, max_length=200)
    value: Any
    confidence: float = Field(default=1.0, ge=0, le=1)
    reason: str = Field(default="explicit_user_preference", max_length=500)
    sensitivity: str = Field(default="normal", max_length=40)
    expected_memory_version: int | None = Field(default=None, ge=0)


class ConfirmMemoryProposalRequest(BaseModel):
    version: int = Field(ge=1)


class UpdateMemoryRequest(BaseModel):
    value: Any
    version: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    sensitivity: str | None = Field(default=None, max_length=40)


@router.get("/memory-proposals")
async def list_memory_proposals(
    request: Request,
    status: str | None = Query(default="awaiting_confirmation"),
) -> dict:
    normalized = None if status in {None, "", "all"} else status
    return {"proposals": await request.app.state.memory_service.list_proposals(normalized)}


@router.post("/memory-proposals")
async def create_memory_proposal(body: MemoryCandidateRequest, request: Request) -> dict:
    proposal = await request.app.state.memory_service.propose_memory(
        body.source_message_id,
        body.model_dump(exclude={"source_message_id"}),
    )
    return {"proposal": proposal}


@router.post("/memory-proposals/{proposal_id}/confirm")
async def confirm_memory_proposal(
    proposal_id: str,
    body: ConfirmMemoryProposalRequest,
    request: Request,
) -> dict:
    try:
        return await request.app.state.memory_service.upsert_confirmed_memory(
            proposal_id, body.version
        )
    except MemoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/memory-proposals/{proposal_id}/reject")
async def reject_memory_proposal(proposal_id: str, request: Request) -> dict:
    try:
        proposal = await request.app.state.memory_service.reject_proposal(proposal_id)
    except MemoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="memory proposal not found")
    return {"proposal": proposal}


@router.get("/memories")
async def list_memories(request: Request) -> dict:
    return {"memories": await request.app.state.memory_service.list_memories()}


@router.put("/memories/{memory_id}")
async def update_memory(memory_id: str, body: UpdateMemoryRequest, request: Request) -> dict:
    try:
        memory = await request.app.state.memory_service.update_memory(
            memory_id,
            value=body.value,
            version=body.version,
            confidence=body.confidence,
            sensitivity=body.sensitivity,
        )
    except MemoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"memory": memory}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict:
    if not await request.app.state.memory_service.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True}


@router.delete("/memories")
async def clear_memories(request: Request) -> dict:
    return {"deleted": await request.app.state.memory_service.clear_memories()}


@router.get("/memories-export")
async def export_memories(request: Request) -> dict:
    return await request.app.state.memory_service.export_memories()
