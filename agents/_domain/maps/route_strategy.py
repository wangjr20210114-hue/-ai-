"""Pure route-strategy selection policy."""

from __future__ import annotations

import re
from dataclasses import dataclass


ROUTE_MODES = frozenset({"driving", "transit", "walking", "bicycling"})
ROUTE_STRATEGIES = frozenset({"time_then_cost", "least_time", "least_cost"})

_MODE_TERMS = (
    ("walking", ("步行", "走路", "walk", "walking")),
    ("bicycling", (
        "骑行", "騎行", "自行车", "自行車", "单车", "單車",
        "bicycle", "bike", "cycling",
    )),
    ("transit", (
        "公共交通", "公交", "公車", "地铁", "地鐵", "巴士",
        "public transit", "subway", "metro", "bus",
    )),
    ("driving", (
        "自驾", "自駕", "驾车", "駕車", "开车", "開車",
        "driving", "drive", "car",
    )),
)
_STRATEGY_TERMS = (
    ("least_cost", (
        "省钱", "省錢", "最便宜", "低预算", "低預算", "经济", "經濟",
        "cheapest", "low cost", "budget", "economical",
    )),
    ("least_time", (
        "最快", "省时", "省時", "赶时间", "趕時間", "时间紧", "時間緊",
        "fastest", "quickest", "save time",
    )),
    ("time_then_cost", (
        "兼顾", "兼顧", "平衡", "性价比", "性價比", "时间和费用",
        "時間和費用", "balanced", "time and cost",
    )),
)
_NEGATIONS = ("不要", "不想", "避免", "别", "別", "not", "without")


@dataclass(frozen=True)
class RouteStrategySelection:
    mode: str
    strategy: str
    explicit_mode: str = ""
    explicit_strategy: str = ""


def _positive_term(message: str, term: str) -> bool:
    pattern = (
        rf"(?<![a-z]){re.escape(term)}(?![a-z])"
        if term.isascii() else re.escape(term)
    )
    for match in re.finditer(pattern, message):
        prefix = message[max(0, match.start() - 8):match.start()].strip()
        clause_prefix = re.split(r"[，,。.!！?？;；]", prefix)[-1]
        if not any(marker in clause_prefix for marker in _NEGATIONS):
            return True
    return False


def _matched_preferences(
    message: str,
    definitions: tuple[tuple[str, tuple[str, ...]], ...],
) -> set[str]:
    return {
        value for value, terms in definitions
        if any(_positive_term(message, term) for term in terms)
    }


def infer_route_preferences(message: str) -> tuple[str, str]:
    """Extract only explicit user preferences without delegating policy to a model."""
    normalized = " ".join(str(message or "").lower().split())
    modes = _matched_preferences(normalized, _MODE_TERMS)
    strategies = _matched_preferences(normalized, _STRATEGY_TERMS)
    if modes == {"walking", "transit"}:
        mode = "transit"
    else:
        mode = next(iter(modes)) if len(modes) == 1 else ""
    if strategies == {"least_time", "least_cost"}:
        strategy = "time_then_cost"
    else:
        strategy = next(iter(strategies)) if len(strategies) == 1 else ""
    return mode, strategy


def select_route_strategy(
    *,
    requested_mode: str,
    planned_mode: str,
    context_mode: str,
    learned_mode: str,
    default_mode: str,
    requested_strategy: str,
    planned_strategy: str,
    context_strategy: str,
    learned_strategy: str,
    default_strategy: str,
) -> RouteStrategySelection:
    """Select explicit context first, then learned and configured defaults."""
    requested_mode = str(requested_mode or "").strip().lower()
    planned_mode = str(planned_mode or "").strip().lower()
    explicit_mode = (
        requested_mode if requested_mode in ROUTE_MODES
        else planned_mode if planned_mode in ROUTE_MODES
        else ""
    )
    requested_strategy = str(requested_strategy or "").strip().lower()
    planned_strategy = str(planned_strategy or "").strip().lower()
    explicit_strategy = (
        requested_strategy if requested_strategy in ROUTE_STRATEGIES
        else planned_strategy if planned_strategy in ROUTE_STRATEGIES
        else ""
    )
    mode = next(
        (
            value for value in (
                explicit_mode, context_mode, learned_mode, default_mode, "driving",
            )
            if value in ROUTE_MODES
        ),
        "driving",
    )
    strategy = next(
        (
            value for value in (
                explicit_strategy, context_strategy, learned_strategy, default_strategy,
                "time_then_cost",
            )
            if value in ROUTE_STRATEGIES
        ),
        "time_then_cost",
    )
    return RouteStrategySelection(
        mode=mode,
        strategy=strategy,
        explicit_mode=explicit_mode,
        explicit_strategy=explicit_strategy,
    )


__all__ = (
    "ROUTE_MODES",
    "ROUTE_STRATEGIES",
    "RouteStrategySelection",
    "infer_route_preferences",
    "select_route_strategy",
)
