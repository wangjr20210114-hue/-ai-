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
    raw_reasons = plan.get("_runtime_fallback_reasons") or {}
    reasons = (
        {
            str(skill_id or "").strip(): str(reason or "").strip()
            for skill_id, reason in raw_reasons.items()
        }
        if isinstance(raw_reasons, Mapping)
        else {}
    )

    def login_required(skill_id: str) -> bool:
        reason = reasons.get(skill_id)
        if reason:
            return reason == "login_required"
        # Backward compatibility for persisted messages created before the
        # entitlement layer began carrying an explicit downgrade reason.
        return str(auth_type or "") == "guest"

    hints: list[dict[str, Any]] = []
    if "web-search" in skills:
        hints.append({
            "kind": "freshness",
            "skill_ids": ["web-search"],
            "login_required": login_required("web-search"),
        })
        skills = [value for value in skills if value != "web-search"]
    login_skills = [
        skill_id for skill_id in skills if login_required(skill_id)
    ]
    degraded_skills = [
        skill_id for skill_id in skills if skill_id not in login_skills
    ]
    if login_skills:
        hints.append({
            "kind": "skill_suggestion",
            "skill_ids": login_skills,
            "login_required": True,
        })
    if degraded_skills:
        hints.append({
            "kind": "skill_suggestion",
            "skill_ids": degraded_skills,
            "login_required": False,
        })
    return hints


def state_requirements_for_plan(
    plan: Mapping[str, Any],
    fallback_tool_names: tuple[str, ...] = (),
) -> tuple[bool, bool]:
    """Return whether the selected chain needs workspace or proactive state."""
    fallback = set(fallback_tool_names)
    workspace = bool(
        plan.get("needs_calendar_context")
        or plan.get("needs_calendar_action")
        or plan.get("needs_route")
        or {"propose_calendar_changes", "plan_route_between_places"} & fallback
    )
    proactive = bool(
        plan.get("needs_workflow_action")
        or plan.get("needs_opportunity_review")
        or "propose_workflow" in fallback
    )
    return workspace, proactive


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
    force_refresh: bool,
    progressive_media: bool | None = None,
    response_language: str = "zh-CN",
) -> SearchRequest | None:
    if (
        not plan.get("needs_web_search")
        or plan.get("needs_clarification")
        or str(plan.get("blocked_skill") or "").strip()
    ):
        return None
    # Real article media belongs to the web-search component contract. Turning
    # off the standalone Vision Skill must not silently make every rich-search
    # answer text-only; the provider adapter still applies its configured
    # review chain and source-bound fallback policy.
    media_enabled = bool(
        image_limit > 0
        and (plan.get("needs_web_search") or plan.get("needs_images"))
    )
    progressive_media = (
        not bool(plan.get("needs_image_generation"))
        if progressive_media is None
        else bool(progressive_media)
    )
    # Factual sources stay on the answer path. Reviewed images may arrive later
    # unless image generation needs them as provider references first.
    media_mode = (
        "progressive" if media_enabled and progressive_media
        else "blocking" if media_enabled
        else "disabled"
    )
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
        prefer_recent_results=bool(plan.get("prefer_recent_results")),
        force_refresh=force_refresh,
        media_mode=media_mode,
        response_language=response_language,
    )
