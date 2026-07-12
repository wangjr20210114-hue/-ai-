"""Flexible travel orchestrator — no hardcoded constraints, asks user for missing info."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agents.travel.agent import TravelAgent
from agents.travel.context_analyzer import analyze, TravelContext
from agents.travel.models import TravelConstraints
from agents.travel.constraints import normalize_constraints
from agents.travel.place_repository import PlaceRepository


class TravelOrchestrator:
    def __init__(self) -> None:
        self._agent = TravelAgent(PlaceRepository())

    async def handle(self, message: str, history: list[str] | None = None) -> dict[str, Any]:
        """Handle a travel message: analyze → ask missing info → plan itinerary."""
        ctx = await analyze(message, history)

        # Not enough info → ask user naturally
        if not ctx.is_complete:
            return {
                "action": "ask",
                "reply": self._build_question(ctx),
                "context": asdict(ctx),
            }

        # Enough info → plan trip
        constraints = self._ctx_to_constraints(ctx)
        draft = await self._agent.plan_trip_dict(constraints)
        draft["action"] = "plan"
        draft["context"] = asdict(ctx)
        return draft

    def _build_question(self, ctx: TravelContext) -> str:
        """Build a natural question from missing fields."""
        parts: list[str] = []
        if ctx.destination:
            parts.append(f"好的，你想去{ctx.destination}")
        if ctx.days > 0:
            parts.append(f"玩{ctx.days}天")
        if ctx.style:
            parts.append(f"偏好{ctx.style}")
        if ctx.participants:
            parts.append(f"{ctx.participants}出行")

        if parts:
            msg = "、".join(parts) + "。"
        else:
            msg = "好的，旅行规划交给我！"

        if ctx.missing:
            msg += "\n\n还需要确认一下："
            for m in ctx.missing[:3]:
                msg += f"\n• {m}"
        return msg

    def _ctx_to_constraints(self, ctx: TravelContext) -> TravelConstraints:
        return normalize_constraints({
            "destination": ctx.destination,
            "departure": ctx.departure,
            "days": ctx.days,
            "budget": ctx.budget,
            "style": ctx.style,
            "interests": ctx.interests,
            "participants": ctx.participants,
            "start_date": ctx.start_date,
        })
