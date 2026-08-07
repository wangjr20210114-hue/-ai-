"""Pure policy for editing an already verified ordered route place set."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal


RouteEditOperation = Literal["add", "remove", "replace"]
RouteEditPosition = Literal["default", "start", "end", "before", "after"]


@dataclass(frozen=True)
class RoutePlaceEdit:
    operation: RouteEditOperation
    target_query: str = ""
    new_query: str = ""
    new_near_query: str = ""
    position: RouteEditPosition = "default"


@dataclass(frozen=True)
class RoutePlaceSetIssue:
    edit_index: int
    field: Literal["target", "new"]
    reason: Literal["missing_target", "ambiguous_target", "missing_new_place"]
    query: str
    candidates: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RoutePlaceSetResult:
    stops: tuple[dict[str, Any], ...]
    issues: tuple[RoutePlaceSetIssue, ...] = ()
    new_stop_edit_indexes: tuple[int | None, ...] = ()


def _normalize(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _stop_search_values(stop: dict[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("name", "address", "title"):
        normalized = _normalize(stop.get(key))
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _match_score(query: str, stop: dict[str, Any]) -> float:
    clean_query = _normalize(query)
    if not clean_query:
        return 0.0
    best = 0.0
    for candidate in _stop_search_values(stop):
        if clean_query == candidate:
            return 1.0
        if len(clean_query) >= 2 and (
            clean_query in candidate or candidate in clean_query
        ):
            best = max(best, 0.94)
        best = max(best, SequenceMatcher(None, clean_query, candidate).ratio())
    return best


def _target_candidates(
    stops: list[dict[str, Any]], query: str,
) -> tuple[int | None, tuple[dict[str, Any], ...]]:
    """Match only within the current verified route, including small typos."""
    opaque_prefix = "floris-place:"
    clean_query = str(query or "").strip()
    if clean_query.startswith(opaque_prefix):
        place_id = clean_query[len(opaque_prefix):].strip()
        matches = [
            index for index, stop in enumerate(stops)
            if str(stop.get("place_id") or "").strip() == place_id
        ]
        return (matches[0], ()) if len(matches) == 1 else (None, tuple(stops))

    scored = sorted(
        (
            (_match_score(clean_query, stop), index, stop)
            for index, stop in enumerate(stops)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not scored or scored[0][0] < 0.64:
        return None, tuple(copy.deepcopy(stops))
    best_score = scored[0][0]
    plausible = [item for item in scored if item[0] >= max(0.64, best_score - 0.08)]
    if len(plausible) == 1:
        return plausible[0][1], ()
    return None, tuple(copy.deepcopy(item[2]) for item in plausible[:6])


def apply_route_place_edits(
    current_stops: list[dict[str, Any]],
    edits: list[RoutePlaceEdit],
) -> RoutePlaceSetResult:
    """Apply edits without inventing places or searching outside the route.

    New place queries are emitted as unresolved descriptors. The trusted
    provider adapter verifies them concurrently before route planning starts.
    """
    stops = [copy.deepcopy(stop) for stop in current_stops if isinstance(stop, dict)]
    origins: list[int | None] = [None] * len(stops)
    for edit_index, edit in enumerate(edits):
        operation = edit.operation
        position = edit.position if edit.position in {
            "default", "start", "end", "before", "after",
        } else "default"
        target_index: int | None = None
        target_candidates: tuple[dict[str, Any], ...] = ()
        target_required = operation in {"remove", "replace"} or (
            operation == "add" and position in {"before", "after"}
        )
        if target_required:
            target_index, target_candidates = _target_candidates(
                stops, edit.target_query,
            )
            if target_index is None:
                return RoutePlaceSetResult(
                    stops=tuple(stops),
                    issues=(RoutePlaceSetIssue(
                        edit_index=edit_index,
                        field="target",
                        reason=(
                            "ambiguous_target" if target_candidates else "missing_target"
                        ),
                        query=edit.target_query,
                        candidates=target_candidates or tuple(copy.deepcopy(stops)),
                    ),),
                    new_stop_edit_indexes=tuple(origins),
                )

        if operation == "remove":
            assert target_index is not None
            stops.pop(target_index)
            origins.pop(target_index)
            continue

        if not str(edit.new_query or "").strip():
            return RoutePlaceSetResult(
                stops=tuple(stops),
                issues=(RoutePlaceSetIssue(
                    edit_index=edit_index,
                    field="new",
                    reason="missing_new_place",
                    query="",
                ),),
                new_stop_edit_indexes=tuple(origins),
            )
        new_stop = {
            "query": str(edit.new_query).strip()[:160],
            "near_query": str(edit.new_near_query or "").strip()[:160],
            "_route_edit_index": edit_index,
        }
        if operation == "replace":
            assert target_index is not None
            stops[target_index] = new_stop
            origins[target_index] = edit_index
            continue

        if position == "start":
            insert_index = 0
        elif position == "before" and target_index is not None:
            insert_index = target_index
        elif position == "after" and target_index is not None:
            insert_index = target_index + 1
        else:
            insert_index = len(stops)
        stops.insert(insert_index, new_stop)
        origins.insert(insert_index, edit_index)

    return RoutePlaceSetResult(
        stops=tuple(stops),
        new_stop_edit_indexes=tuple(origins),
    )


__all__ = (
    "RoutePlaceEdit",
    "RoutePlaceSetIssue",
    "RoutePlaceSetResult",
    "apply_route_place_edits",
)
