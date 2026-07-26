"""Deterministic privacy guards for browser-current-location references.

These helpers do not decide whether the maps Skill should run. The semantic
capability planner owns that decision. They only make sure a phrase that
already reached a map tool is never sent to Tencent as if it were a POI name.
"""

from __future__ import annotations

import re
from typing import Any


def _normalize_reference(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").casefold()))


_CURRENT_LOCATION_REFERENCES = frozenset({
    "当前位置",
    "我的位置",
    "我当前位置",
    "当前地点",
    "我的当前位置",
    "我所在位置",
    "我现在的位置",
    "我当前的位置",
    "实时位置",
    "我附近",
    "我这里",
    "我这儿",
    "我这边",
    "这里",
    "这儿",
    "这边",
})

_CURRENT_LOCATION_CORE = (
    r"(?:"
    r"(?:我(?:的)?|本人(?:的)?)?(?:现在|当前|实时)?(?:所在)?(?:位置|地点)"
    r"|我?(?:这里|这儿|这边)"
    r")"
)


def is_browser_current_location_reference(value: Any) -> bool:
    """Return whether a map argument denotes the request-scoped browser fix."""
    normalized = _normalize_reference(value)
    if normalized in _CURRENT_LOCATION_REFERENCES:
        return True
    return bool(re.fullmatch(
        rf"(?:从|以)?{_CURRENT_LOCATION_CORE}(?:出发|为起点|作为起点)?",
        normalized,
    ))


def has_explicit_current_location_origin(message: Any) -> bool:
    """Recognize an explicit current-position route origin in free text."""
    normalized = _normalize_reference(message)
    return bool(
        re.search(
            rf"(?:从|以){_CURRENT_LOCATION_CORE}(?:出发|为起点|作为起点)",
            normalized,
        )
        or re.search(rf"{_CURRENT_LOCATION_CORE}(?:出发|为起点|作为起点)", normalized)
    )
