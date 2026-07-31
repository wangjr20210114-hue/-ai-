"""Deterministic membership and anonymous Skill policy."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


MEMBERSHIP_PLANS = ("guest", "free", "plus", "pro")
PLAN_RANK = {plan: index for index, plan in enumerate(MEMBERSHIP_PLANS)}
GUEST_SKILL_IDS = frozenset({"core", "proactive-agent"})


def normalize_membership(value: Any, auth_type: str = "guest") -> str:
    plan = str(value or "").lower()
    if plan in PLAN_RANK:
        return plan
    return "guest" if auth_type == "guest" else "free"


def plan_allows(actual: Any, required: Any = "free") -> bool:
    current = normalize_membership(actual)
    minimum = normalize_membership(required, "user")
    return PLAN_RANK[current] >= PLAN_RANK[minimum]


def allowed_skill_ids(
    identity: Mapping[str, Any],
    requested: Iterable[str],
    *,
    required_plans: Mapping[str, str] | None = None,
) -> frozenset[str]:
    values = {str(value or "") for value in requested if str(value or "")}
    if str(identity.get("auth_type") or "guest") == "guest":
        return frozenset(values & GUEST_SKILL_IDS)
    plan = normalize_membership(
        identity.get("membership"),
        str(identity.get("auth_type") or "wechat"),
    )
    requirements = required_plans or {}
    return frozenset(
        skill_id for skill_id in values
        if plan_allows(plan, requirements.get(skill_id, "free"))
    )


def effective_skill_preferences(
    identity: Mapping[str, Any],
    preferences: Mapping[str, Any] | None,
) -> dict[str, bool]:
    values = {
        str(skill_id): bool(enabled)
        for skill_id, enabled in (preferences or {}).items()
    }
    if str(identity.get("auth_type") or "guest") == "guest":
        return {
            skill_id: bool(enabled and skill_id in GUEST_SKILL_IDS)
            for skill_id, enabled in values.items()
        }
    return values


def public_entitlements(identity: Mapping[str, Any]) -> dict[str, Any]:
    plan = normalize_membership(
        identity.get("membership"),
        str(identity.get("auth_type") or "guest"),
    )
    limits = {
        "guest": {
            "search_depth": "basic",
            "concurrent_runs": 1,
            "daily_tokens": 20_000,
            "user_skill_uploads": 0,
        },
        "free": {
            "search_depth": "standard",
            "concurrent_runs": 1,
            "daily_tokens": 80_000,
            "user_skill_uploads": 2,
        },
        "plus": {
            "search_depth": "deep",
            "concurrent_runs": 2,
            "daily_tokens": 300_000,
            "user_skill_uploads": 10,
        },
        "pro": {
            "search_depth": "deep",
            "concurrent_runs": 4,
            "daily_tokens": 1_000_000,
            "user_skill_uploads": 50,
        },
    }[plan]
    return {
        "plan": plan,
        "limits": limits,
        "payment_available": False,
    }


def require_skill_access(
    identity: Mapping[str, Any],
    skill_id: str,
    required_plan: str = "free",
) -> None:
    auth_type = str(identity.get("auth_type") or "guest")
    if auth_type == "guest" and skill_id not in GUEST_SKILL_IDS:
        raise PermissionError("请先登录微信后使用此 Skill")
    if auth_type != "guest" and not plan_allows(
        identity.get("membership"),
        required_plan,
    ):
        raise PermissionError("当前会员等级无法使用此 Skill")
