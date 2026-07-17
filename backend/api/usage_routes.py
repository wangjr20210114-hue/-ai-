"""Usage accounting and budget preference APIs."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["usage"])


class UsagePreferencesRequest(BaseModel):
    daily_budget_cny: float | None = Field(default=None, ge=0, le=1_000_000)
    monthly_budget_cny: float | None = Field(default=None, ge=0, le=10_000_000)
    enforcement: str | None = Field(default=None, pattern="^(off|soft|hard)$")
    alert_threshold_percent: int | None = Field(default=None, ge=1, le=100)


@router.get("/usage")
async def list_usage(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    return {"records": await request.app.state.usage_service.list_usage(limit)}


@router.get("/usage-summary")
async def usage_summary(request: Request) -> dict:
    return await request.app.state.usage_service.summarize()


@router.get("/usage-preferences")
async def usage_preferences(request: Request) -> dict:
    return {"preferences": await request.app.state.usage_service.get_preferences()}


@router.put("/usage-preferences")
async def update_usage_preferences(body: UsagePreferencesRequest, request: Request) -> dict:
    return {
        "preferences": await request.app.state.usage_service.update_preferences(
            **body.model_dump(exclude_none=True)
        )
    }
