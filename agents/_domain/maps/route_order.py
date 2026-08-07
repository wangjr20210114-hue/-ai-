"""Deterministic stop-order policy over provider-supplied road matrices."""

from __future__ import annotations

import math
from collections.abc import Sequence


Matrix = Sequence[Sequence[float]]


def optimize_open_route_order(
    distance_matrix: Matrix,
    duration_matrix: Matrix,
    *,
    strategy: str = "time_then_cost",
) -> tuple[int, ...]:
    """Return the best open Hamiltonian path without inventing map facts.

    Tencent owns the road distance and duration evidence. This pure domain
    policy only selects a deterministic order from that evidence: least-cost
    uses road distance as the cost proxy, while the time strategies prioritize
    provider duration. Invalid or disconnected matrices preserve input order.
    """
    count = len(distance_matrix)
    identity = tuple(range(count))
    if count < 3 or count > 12:
        return identity
    if len(duration_matrix) != count:
        return identity
    try:
        distances = tuple(tuple(float(value) for value in row) for row in distance_matrix)
        durations = tuple(tuple(float(value) for value in row) for row in duration_matrix)
    except (TypeError, ValueError):
        return identity
    if any(len(row) != count for row in distances + durations):
        return identity
    if any(
        value < 0 or not math.isfinite(value)
        for matrix in (distances, durations)
        for row in matrix
        for value in row
    ):
        return identity

    normalized_strategy = str(strategy or "time_then_cost").strip().lower()

    def edge_score(origin: int, destination: int) -> tuple[float, float]:
        distance = distances[origin][destination]
        duration = durations[origin][destination]
        if normalized_strategy == "least_cost":
            return distance, duration
        return duration, distance

    # State score is (primary objective, secondary objective, lexical path).
    # Every verified place may become the start or end because recommendations
    # have no user-provided order.
    dp: dict[tuple[int, int], tuple[float, float, tuple[int, ...]]] = {
        (1 << index, index): (0.0, 0.0, (index,))
        for index in range(count)
    }
    for mask in range(1, 1 << count):
        for last in range(count):
            current = dp.get((mask, last))
            if current is None:
                continue
            for nxt in range(count):
                if mask & (1 << nxt):
                    continue
                primary, secondary = edge_score(last, nxt)
                candidate = (
                    current[0] + primary,
                    current[1] + secondary,
                    current[2] + (nxt,),
                )
                state_key = (mask | (1 << nxt), nxt)
                previous = dp.get(state_key)
                if previous is None or candidate < previous:
                    dp[state_key] = candidate
    full_mask = (1 << count) - 1
    completed = [
        dp[(full_mask, last)]
        for last in range(count)
        if (full_mask, last) in dp
    ]
    return min(completed)[2] if completed else identity
