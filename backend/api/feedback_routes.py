"""User feedback APIs for explainable policy adjustment proposals."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    run_id: str | None = None
    action_id: str | None = None
    action: Literal["helpful", "unhelpful", "dismissed", "corrected"]
    reason: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_feedback_id: str = Field(default="", max_length=200)


@router.post("/feedback")
async def record_feedback(body: FeedbackRequest, request: Request) -> dict:
    return await request.app.state.feedback_service.record_feedback(
        run_id=body.run_id,
        action_id=body.action_id,
        action=body.action,
        reason=body.reason,
        metadata=body.metadata,
        client_feedback_id=body.client_feedback_id,
    )


@router.get("/feedback")
async def list_feedback(
    request: Request,
    run_id: str | None = None,
    action_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {
        "feedback": await request.app.state.feedback_service.list_feedback(
            run_id=run_id,
            action_id=action_id,
            limit=limit,
        )
    }
