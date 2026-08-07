"""Pure policy for one conversation-scoped, provider-verified route chain."""

from __future__ import annotations

import copy
import hashlib
import time
from typing import Any


def _chain_id(conversation_id: str) -> str:
    digest = hashlib.sha256(str(conversation_id).encode("utf-8")).hexdigest()[:16]
    return f"routechain-{digest}"


def current_route_plan(
    state: dict[str, Any],
    conversation_id: str = "",
) -> dict[str, Any]:
    """Return only the current conversation's chain head.

    An empty conversation id keeps compatibility for bounded internal tests.
    Production callers always provide it, so a route from another chat can
    never become an implicit origin or Calendar source.
    """
    clean_conversation_id = str(conversation_id or "").strip()
    index = state.get("route_chain_index")
    chains = state.get("route_chains")
    chain_id = (
        str(index.get(clean_conversation_id) or "")
        if clean_conversation_id and isinstance(index, dict)
        else ""
    )
    chain = chains.get(chain_id) if chain_id and isinstance(chains, dict) else None
    current = chain.get("current_plan") if isinstance(chain, dict) else None
    if isinstance(current, dict) and str(current.get("id") or ""):
        return copy.deepcopy(current)
    latest = state.get("latest_route_plan")
    if not isinstance(latest, dict) or not str(latest.get("id") or ""):
        return {}
    owner = str(latest.get("conversation_id") or "").strip()
    if clean_conversation_id and owner != clean_conversation_id:
        # One-time compatibility for workspaces written before route chains
        # existed. Once any chain has been recorded, cross-chat fallback is
        # permanently disabled.
        if owner or state.get("route_chains"):
            return {}
    return copy.deepcopy(latest)


def route_plan_by_id(
    state: dict[str, Any],
    conversation_id: str,
    route_plan_id: str,
) -> dict[str, Any]:
    """Resolve one revision from the current conversation's route chain."""
    clean_plan_id = str(route_plan_id or "").strip()
    if not clean_plan_id:
        return {}
    clean_conversation_id = str(conversation_id or "").strip()
    index = state.get("route_chain_index")
    chains = state.get("route_chains")
    chain_id = (
        str(index.get(clean_conversation_id) or "")
        if clean_conversation_id and isinstance(index, dict)
        else ""
    )
    chain = chains.get(chain_id) if chain_id and isinstance(chains, dict) else None
    plans = chain.get("plans") if isinstance(chain, dict) else None
    plan = plans.get(clean_plan_id) if isinstance(plans, dict) else None
    if isinstance(plan, dict):
        return copy.deepcopy(plan)
    legacy = state.get("route_plans")
    plan = legacy.get(clean_plan_id) if isinstance(legacy, dict) else None
    if not isinstance(plan, dict):
        return {}
    owner = str(plan.get("conversation_id") or "").strip()
    if clean_conversation_id and owner != clean_conversation_id:
        # Owner-less legacy revisions are accepted only until the first
        # conversation chain exists. Afterwards every lookup is strictly
        # scoped, including explicit route_plan_id references.
        if owner or state.get("route_chains"):
            return {}
    return copy.deepcopy(plan)


def record_route_plan(
    state: dict[str, Any],
    conversation_id: str,
    route_plan: dict[str, Any],
    *,
    now: int | None = None,
    maximum_chains: int = 24,
) -> dict[str, Any]:
    """Append one immutable plan revision and advance its route chain."""
    clean_conversation_id = str(conversation_id or "").strip()
    if not clean_conversation_id:
        raise ValueError("conversation_id is required for a route chain")
    plan = copy.deepcopy(route_plan)
    if not str(plan.get("id") or ""):
        raise ValueError("route plan id is required")
    timestamp = int(time.time() if now is None else now)
    index = state.setdefault("route_chain_index", {})
    chains = state.setdefault("route_chains", {})
    chain_id = str(index.get(clean_conversation_id) or _chain_id(clean_conversation_id))
    previous = chains.get(chain_id) if isinstance(chains.get(chain_id), dict) else {}
    previous_plan = previous.get("current_plan") if isinstance(previous, dict) else {}
    revision = int(previous.get("revision") or 0) + 1
    plan.update({
        "conversation_id": clean_conversation_id,
        "route_chain_id": chain_id,
        "route_chain_revision": revision,
        "previous_route_plan_id": str(
            (previous_plan.get("id") if isinstance(previous_plan, dict) else "") or ""
        ),
    })
    plan_ids = list(dict.fromkeys([
        *(
            str(value or "")
            for value in (previous.get("route_plan_ids") or [])
            if str(value or "")
        ),
        str(plan["id"]),
    ]))[-12:]
    plans = {
        str(key): copy.deepcopy(value)
        for key, value in (
            previous.get("plans") if isinstance(previous.get("plans"), dict) else {}
        ).items()
        if str(key) in plan_ids and isinstance(value, dict)
    }
    plans[str(plan["id"])] = copy.deepcopy(plan)
    chains[chain_id] = {
        "id": chain_id,
        "conversation_id": clean_conversation_id,
        "revision": revision,
        "current_plan": copy.deepcopy(plan),
        "route_plan_ids": plan_ids,
        "plans": {plan_id: plans[plan_id] for plan_id in plan_ids if plan_id in plans},
        "updated_at": timestamp,
    }
    index[clean_conversation_id] = chain_id
    keep = dict(sorted(
        (
            (key, value) for key, value in chains.items()
            if isinstance(value, dict) and str(value.get("conversation_id") or "")
        ),
        key=lambda item: int(item[1].get("updated_at") or 0),
        reverse=True,
    )[:max(1, min(64, int(maximum_chains or 24)))])
    state["route_chains"] = keep
    state["route_chain_index"] = {
        str(value.get("conversation_id")): key
        for key, value in keep.items()
    }
    state["latest_route_plan"] = copy.deepcopy(plan)
    return plan


__all__ = ("current_route_plan", "record_route_plan", "route_plan_by_id")
