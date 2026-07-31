"""Best-effort application-side provider metering in Makers LangGraph Store.

These counters describe calls made by Floris. They are deliberately separate
from provider billing and quota because most provider keys used by the app do
not expose a stable remaining-quota API.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .data_version import namespace
from .auth import required_user_id


STATE_KEY = "state"
SCHEMA_VERSION = 1
MAX_EVENTS = 4000
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
_locks: dict[str, asyncio.Lock] = {}


def _item_value(item: Any) -> dict[str, Any] | None:
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def metering_namespace(user_id: str) -> tuple[str, ...]:
    return namespace("provider_metering", required_user_id(user_id))


def empty_provider_metering_state() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "events": []}


async def load_provider_metering_state(store: Any, user_id: str) -> dict[str, Any]:
    state = empty_provider_metering_state()
    if store is None:
        return state
    try:
        stored = _item_value(await store.aget(metering_namespace(user_id), STATE_KEY))
    except Exception as exc:
        logging.warning("provider metering read failed: %s", exc)
        return state
    if isinstance(stored, dict):
        state.update(copy.deepcopy(stored))
    if not isinstance(state.get("events"), list):
        state["events"] = []
    return state


async def record_provider_usage(
    store: Any,
    user_id: str,
    provider: str,
    metric: str,
    amount: int | float = 1,
    *,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    source: str = "",
    created_at: int | None = None,
) -> bool:
    """Persist one bounded usage event; never raise into a business call."""
    if store is None:
        return False
    clean_provider = str(provider or "").strip().lower()[:80]
    clean_metric = str(metric or "").strip().lower()[:80]
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        return False
    if not clean_provider or not clean_metric or numeric_amount <= 0:
        return False
    lock_key = required_user_id(user_id)
    lock = _locks.setdefault(lock_key, asyncio.Lock())
    try:
        async with lock:
            state = await load_provider_metering_state(store, lock_key)
            state.setdefault("events", []).append({
                "id": f"usage_{uuid.uuid4().hex[:20]}",
                "provider": clean_provider,
                "metric": clean_metric,
                "amount": numeric_amount,
                "model": str(model or "")[:160],
                "input_tokens": max(0, int(input_tokens or 0)),
                "output_tokens": max(0, int(output_tokens or 0)),
                "source": str(source or "")[:120],
                "created_at": int(created_at or time.time()),
            })
            state["events"] = state["events"][-MAX_EVENTS:]
            state["schema_version"] = SCHEMA_VERSION
            state["revision"] = int(state.get("revision") or 0) + 1
            await store.aput(metering_namespace(lock_key), STATE_KEY, state)
        return True
    except Exception as exc:
        logging.warning(
            "provider metering write failed provider=%s metric=%s: %s",
            clean_provider,
            clean_metric,
            exc,
        )
        return False


def provider_metering_summary(state: dict[str, Any], now: int | None = None) -> dict[str, Any]:
    timestamp = int(now or time.time())
    local_now = datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE)
    day_start = int(local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    month_start = int(local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    daily: defaultdict[str, float] = defaultdict(float)
    monthly: defaultdict[str, float] = defaultdict(float)
    providers: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in state.get("events") or []:
        if not isinstance(event, dict):
            continue
        provider = str(event.get("provider") or "").strip().lower()
        metric = str(event.get("metric") or "").strip().lower()
        if not provider or not metric:
            continue
        try:
            amount = float(event.get("amount") or 0)
            occurred = int(event.get("created_at") or 0)
        except (TypeError, ValueError):
            continue
        key = f"{provider}.{metric}"
        if occurred >= month_start:
            monthly[key] += amount
            providers[provider][f"monthly_{metric}"] += amount
        if occurred >= day_start:
            daily[key] += amount
            providers[provider][f"daily_{metric}"] += amount

    def normalized(values: dict[str, float]) -> dict[str, int | float]:
        return {
            key: int(value) if float(value).is_integer() else round(value, 3)
            for key, value in sorted(values.items())
        }

    return {
        "daily": normalized(daily),
        "monthly": normalized(monthly),
        "providers": {
            provider: normalized(values)
            for provider, values in sorted(providers.items())
        },
        "recorded_events": len(state.get("events") or []),
        "timezone": "Asia/Shanghai",
    }


def usage_tokens(diagnostics: Any) -> tuple[int, int, int]:
    """Normalize OpenAI-compatible token diagnostics."""
    if not isinstance(diagnostics, dict):
        return 0, 0, 0
    try:
        input_tokens = max(0, int(
            diagnostics.get("input_tokens")
            or diagnostics.get("prompt_tokens")
            or 0
        ))
        output_tokens = max(0, int(
            diagnostics.get("output_tokens")
            or diagnostics.get("completion_tokens")
            or 0
        ))
        total_tokens = max(0, int(
            diagnostics.get("total_tokens")
            or input_tokens + output_tokens
        ))
    except (TypeError, ValueError):
        return 0, 0, 0
    return input_tokens, output_tokens, total_tokens


async def record_vision_diagnostics(
    store: Any,
    user_id: str,
    diagnostics: Any,
    *,
    source: str,
) -> bool:
    if not isinstance(diagnostics, dict):
        return False
    input_tokens, output_tokens, total_tokens = usage_tokens(diagnostics)
    if total_tokens <= 0:
        return False
    provider = str(diagnostics.get("provider") or "hunyuan")
    return await record_provider_usage(
        store,
        user_id,
        provider,
        "vision_tokens",
        total_tokens,
        model=str(diagnostics.get("model") or ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        source=source,
    )
