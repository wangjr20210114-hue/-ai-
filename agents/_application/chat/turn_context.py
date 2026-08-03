"""Deterministic assembly of controller-owned turn inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..search.search_use_case import SearchRequest
from ..._domain.entitlements.policy import public_entitlements


def experience_hints_for_plan(
    plan: Mapping[str, Any],
    *,
    auth_type: str,
) -> list[dict[str, Any]]:
    """Return presentation-only hints without changing the model answer."""
    skills = list(dict.fromkeys(
        str(value or "").strip()
        for value in (plan.get("_runtime_model_fallback_skills") or [])
        if str(value or "").strip()
    ))[:8]
    if not skills:
        return []
    hints: list[dict[str, Any]] = []
    if "web-search" in skills:
        hints.append({
            "kind": "freshness",
            "skill_ids": ["web-search"],
            "login_required": str(auth_type or "") == "guest",
        })
        skills = [value for value in skills if value != "web-search"]
    if skills:
        hints.append({
            "kind": "skill_suggestion",
            "skill_ids": skills,
            "login_required": str(auth_type or "") == "guest",
        })
    return hints


def search_request_for_plan(
    plan: Mapping[str, Any],
    identity: Mapping[str, Any],
    *,
    conversation_id: str,
    user_message: str,
    current_date: str,
    result_limit: int,
    image_limit: int,
    parallel_queries: bool,
    vision_enabled: bool,
    force_refresh: bool,
) -> SearchRequest | None:
    if (
        not plan.get("needs_web_search")
        or plan.get("needs_clarification")
        or str(plan.get("blocked_skill") or "").strip()
    ):
        return None
    media_enabled = bool(
        vision_enabled
        and image_limit > 0
        and (plan.get("needs_web_search") or plan.get("needs_images"))
    )
    # Keep main's evidence boundary: source pages and bounded visual review
    # complete before the answer graph receives the rich_search ToolMessage.
    media_mode = "blocking" if media_enabled else "disabled"
    entitlements = public_entitlements(identity)
    return SearchRequest(
        tenant_id=str(identity.get("tenant_id") or ""),
        user_id=str(identity.get("subject_id") or identity.get("user_id") or ""),
        conversation_id=conversation_id,
        query=str(plan.get("search_query") or user_message or "").strip()[:500],
        image_query=(
            str(plan.get("image_query") or "").strip()[:500]
            if media_enabled
            else ""
        ),
        depth=str((entitlements.get("limits") or {}).get("search_depth") or "standard"),
        result_limit=result_limit,
        image_limit=image_limit if media_enabled else 0,
        parallel_queries=parallel_queries,
        target_date=current_date,
        strict_date=bool(plan.get("strict_today_only")),
        force_refresh=force_refresh,
        media_mode=media_mode,
    )
