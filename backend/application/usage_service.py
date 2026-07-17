"""Usage accounting and user-controlled budget checks."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from config import settings
from database.repositories import usage_repo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


class UsageService:
    async def record_usage(
        self,
        *,
        run_id: str | None,
        provider: str,
        operation: str,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        units: float = 0,
        estimated_cost: Decimal | float = 0,
        status: str = "succeeded",
    ) -> dict[str, Any]:
        return await usage_repo.record_usage(
            run_id=run_id,
            provider=provider,
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            units=units,
            estimated_cost=float(estimated_cost),
            status=status,
        )

    @staticmethod
    def _period_starts() -> tuple[float, float]:
        now = datetime.now(LOCAL_TZ)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        return day_start, month_start

    async def summarize_daily(self) -> dict[str, Any]:
        day_start, _ = self._period_starts()
        return await usage_repo.summarize_since(day_start)

    async def summarize_monthly(self) -> dict[str, Any]:
        _, month_start = self._period_starts()
        return await usage_repo.summarize_since(month_start)

    async def summarize(self) -> dict[str, Any]:
        daily, monthly, preferences = await self._load_summary_context()
        daily_cost = float(daily["estimated_cost"])
        monthly_cost = float(monthly["estimated_cost"])
        daily_limit = float(preferences["daily_budget_cny"])
        monthly_limit = float(preferences["monthly_budget_cny"])
        threshold = int(preferences["alert_threshold_percent"])
        return {
            "daily": daily,
            "monthly": monthly,
            "preferences": preferences,
            "alerts": {
                "daily": bool(daily_limit and daily_cost >= daily_limit * threshold / 100),
                "monthly": bool(monthly_limit and monthly_cost >= monthly_limit * threshold / 100),
            },
        }

    async def _load_summary_context(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        daily = await self.summarize_daily()
        monthly = await self.summarize_monthly()
        try:
            preferences = await usage_repo.get_preferences()
        except Exception:
            # Migration-safe fallback for callers running against an older test DB.
            preferences = {
                "daily_budget_cny": max(0.0, float(settings.daily_cost_budget_cny)),
                "monthly_budget_cny": 0.0,
                "enforcement": "soft",
                "alert_threshold_percent": 80,
            }
        return daily, monthly, preferences

    async def check_budget(self, additional_estimated_cost: float = 0) -> dict[str, Any]:
        daily, monthly, preferences = await self._load_summary_context()
        extra = max(0.0, additional_estimated_cost)
        daily_limit = max(0.0, float(preferences["daily_budget_cny"]))
        monthly_limit = max(0.0, float(preferences["monthly_budget_cny"]))
        daily_projected = float(daily["estimated_cost"]) + extra
        monthly_projected = float(monthly["estimated_cost"]) + extra
        enforcement = str(preferences.get("enforcement") or "soft")
        exceeded = bool(
            (daily_limit and daily_projected > daily_limit)
            or (monthly_limit and monthly_projected > monthly_limit)
        )
        # Soft budgets ask for confirmation at planning time but do not invalidate
        # an already-confirmed immutable action at execution time.
        allowed = enforcement != "hard" or not exceeded
        return {
            "allowed": allowed,
            "requires_confirmation": enforcement == "soft" and exceeded,
            "enforcement": enforcement,
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
            "current_cost": float(daily["estimated_cost"]),
            "projected_cost": daily_projected,
            "monthly_current_cost": float(monthly["estimated_cost"]),
            "monthly_projected_cost": monthly_projected,
        }

    async def list_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        return await usage_repo.list_usage(limit)

    async def get_preferences(self) -> dict[str, Any]:
        return await usage_repo.get_preferences()

    async def update_preferences(self, **changes: Any) -> dict[str, Any]:
        return await usage_repo.update_preferences(**changes)
