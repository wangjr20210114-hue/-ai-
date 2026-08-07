"""Pure route-strategy selection policy."""

from __future__ import annotations

from dataclasses import dataclass


ROUTE_MODES = frozenset({"driving", "transit", "walking", "bicycling"})
ROUTE_STRATEGIES = frozenset({"time_then_cost", "least_time", "least_cost"})


@dataclass(frozen=True)
class RouteStrategySelection:
    mode: str
    strategy: str
    explicit_mode: str = ""
    explicit_strategy: str = ""


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
    "select_route_strategy",
)
