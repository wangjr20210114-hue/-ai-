"""Safe provider balance and application token usage summary."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .._shared.auth import require_user
from .._shared.intelligence import load_intelligence_state, usage_summary
from .._shared.provider_metering import load_provider_metering_state, provider_metering_summary


DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"
_CACHE_SECONDS = 300
_deepseek_cache: dict[str, Any] = {"expires_at": 0, "value": None}


def _public_balance_info(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    currency = str(item.get("currency") or "").strip().upper()
    total = str(item.get("total_balance") or "").strip()
    if not currency or not total:
        return None
    return {
        "currency": currency[:12],
        "total_balance": total[:40],
        "granted_balance": str(item.get("granted_balance") or "0")[:40],
        "topped_up_balance": str(item.get("topped_up_balance") or "0")[:40],
    }


def _fetch_deepseek_balance(api_key: str, now: int | None = None) -> dict[str, Any]:
    timestamp = int(now or time.time())
    if int(_deepseek_cache.get("expires_at") or 0) > timestamp and isinstance(_deepseek_cache.get("value"), dict):
        return dict(_deepseek_cache["value"])

    request = urllib.request.Request(
        DEEPSEEK_BALANCE_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Floris/1.0 provider-usage",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid provider response")
        balances = [
            value for value in (
                _public_balance_info(item) for item in (payload.get("balance_infos") or [])
            ) if value is not None
        ]
        value = {
            "id": "deepseek",
            "configured": True,
            "status": "available" if payload.get("is_available") is True else "unavailable",
            "is_available": payload.get("is_available") is True,
            "balances": balances,
            "checked_at": timestamp,
        }
        _deepseek_cache.update({"expires_at": timestamp + _CACHE_SECONDS, "value": value})
        return dict(value)
    except urllib.error.HTTPError as exc:
        status = "credentials_required" if exc.code in {401, 403} else "temporarily_unavailable"
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        status = "temporarily_unavailable"
    return {
        "id": "deepseek",
        "configured": True,
        "status": status,
        "is_available": False,
        "balances": [],
        "checked_at": timestamp,
    }


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    now = int(time.time())
    env = getattr(ctx, "env", {}) or {}
    store = ctx.store.langgraph_store
    state = await load_intelligence_state(store, user_id)
    metering_state = await load_provider_metering_state(store, user_id)
    providers = []
    deepseek_key = str(env.get("DEEPSEEK_API_KEY") or "").strip()
    if deepseek_key and "admin" in identity.get("roles", []):
        providers.append(_fetch_deepseek_balance(deepseek_key, now))
    return {
        "refreshed_at": now,
        "usage": usage_summary(state, now),
        "metering": provider_metering_summary(metering_state, now),
        "providers": providers,
    }
