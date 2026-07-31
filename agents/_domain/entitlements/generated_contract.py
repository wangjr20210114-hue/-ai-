"""Generated entitlement contract. Do not edit by hand."""

from __future__ import annotations

from typing import Final


ENTITLEMENT_VERSION: Final = 1
MEMBERSHIP_PLANS: Final = ("guest", "free", "plus", "pro")
GUEST_SKILL_IDS: Final = frozenset(("core", "proactive-agent"))
PLAN_LIMITS: Final = {
    "guest": {
        "search_depth": "basic",
        "concurrent_runs": 1,
        "daily_tokens": 20000,
        "user_skill_uploads": 0,
    },
    "free": {
        "search_depth": "standard",
        "concurrent_runs": 1,
        "daily_tokens": 80000,
        "user_skill_uploads": 2,
    },
    "plus": {
        "search_depth": "deep",
        "concurrent_runs": 2,
        "daily_tokens": 300000,
        "user_skill_uploads": 10,
    },
    "pro": {
        "search_depth": "deep",
        "concurrent_runs": 4,
        "daily_tokens": 1000000,
        "user_skill_uploads": 50,
    },
}
PAYMENT_AVAILABLE: Final = False
ENTITLEMENT_CONTRACT: Final = {
    "version": 1,
    "plans": ["guest", "free", "plus", "pro"],
    "guest_skill_ids": ["core", "proactive-agent"],
    "limits": {
        "guest": {
            "search_depth": "basic",
            "concurrent_runs": 1,
            "daily_tokens": 20000,
            "user_skill_uploads": 0,
        },
        "free": {
            "search_depth": "standard",
            "concurrent_runs": 1,
            "daily_tokens": 80000,
            "user_skill_uploads": 2,
        },
        "plus": {
            "search_depth": "deep",
            "concurrent_runs": 2,
            "daily_tokens": 300000,
            "user_skill_uploads": 10,
        },
        "pro": {
            "search_depth": "deep",
            "concurrent_runs": 4,
            "daily_tokens": 1000000,
            "user_skill_uploads": 50,
        },
    },
    "payment_available": False,
}
