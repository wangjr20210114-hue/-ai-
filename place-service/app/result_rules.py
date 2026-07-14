from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


def deduplicate_nearby_names(
    rows: Iterable[Mapping[str, Any]], limit: int, *, tolerance_degrees: float = 0.005,
) -> list[dict[str, Any]]:
    """Collapse OSM node/way duplicates while preserving same-name places far apart."""

    result: list[dict[str, Any]] = []
    accepted: list[tuple[str, float, float]] = []
    for raw in rows:
        row = dict(raw)
        normalized_name = re.sub(r"\s+", "", str(row.get("name") or "")).casefold()
        lat, lng = float(row.get("lat") or 0), float(row.get("lng") or 0)
        duplicate = any(
            name == normalized_name
            and abs(existing_lat - lat) <= tolerance_degrees
            and abs(existing_lng - lng) <= tolerance_degrees
            for name, existing_lat, existing_lng in accepted
        )
        if normalized_name and duplicate:
            continue
        result.append(row)
        accepted.append((normalized_name, lat, lng))
        if len(result) >= limit:
            break
    return result


def rank_and_deduplicate(
    rows: Iterable[Mapping[str, Any]], query: str, limit: int,
) -> list[dict[str, Any]]:
    """Rank merged OSM/Overture candidates, then collapse nearby duplicates."""

    normalized_query = re.sub(r"\s+", "", query).casefold()

    def rank(raw: Mapping[str, Any]) -> tuple[int, float, int]:
        name = re.sub(r"\s+", "", str(raw.get("name") or "")).casefold()
        if not normalized_query:
            text_rank = 0
        elif name == normalized_query:
            text_rank = 0
        elif name.startswith(normalized_query):
            text_rank = 1
        elif normalized_query in name:
            text_rank = 2
        else:
            text_rank = 3
        importance = float(raw.get("importance") or 0)
        source_rank = 0 if raw.get("source") == "openstreetmap" else 1
        return text_rank, -importance, source_rank

    return deduplicate_nearby_names(sorted(rows, key=rank), limit)
