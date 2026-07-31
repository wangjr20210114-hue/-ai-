"""Domain Model for cacheable search evidence.

Only provider evidence and review metadata are cacheable. Assistant prose,
reasoning, markdown answers, and UI messages are intentionally outside this
schema so a cache hit can never freeze the model's final response.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping


SEARCH_EVIDENCE_CACHE_SCHEMA_VERSION = 1
FORBIDDEN_ANSWER_FIELDS = frozenset({
    "answer",
    "assistant_message",
    "chain_of_thought",
    "final_answer",
    "markdown",
    "model_output",
    "reasoning",
    "response_text",
})
EVIDENCE_FIELDS = (
    "schema_version",
    "query",
    "results",
    "media",
    "preview_media",
    "images",
    "sources_used",
    "total",
    "target_date",
    "strict_date",
    "date_filter",
    "media_pending",
    "search_config",
    "timings_ms",
    "vision_diagnostics",
)
_CURRENT_MARKERS = re.compile(
    r"(今天|今日|现在|当前|最新|刚刚|近期|本周|today|current|latest|breaking|recent)",
    re.IGNORECASE,
)
_EXPLICIT_REFRESH_MARKERS = re.compile(
    r"(重新|再次|再)(搜索|检索|查询|查找|搜|查)"
    r"|刷新(搜索|检索|查询|结果|资料)"
    r"|不要.{0,6}缓存|绕过缓存"
    r"|search\s+again|refresh\s+(the\s+)?(search|results?)|bypass\s+cache",
    re.IGNORECASE,
)


def force_refresh_requested(user_message: str) -> bool:
    """Recognize explicit refresh language outside model-controlled planning."""
    return bool(_EXPLICIT_REFRESH_MARKERS.search(str(user_message or "")[:2000]))


def search_evidence_key(
    *,
    query: str,
    image_query: str,
    depth: str,
    result_limit: int,
    image_limit: int,
    parallel_queries: bool,
    target_date: str,
    strict_date: bool,
    include_media: bool,
    provider_version: str = "searchpro-v1",
) -> str:
    """Fingerprint the factual request, never the eventual answer wording."""
    value = {
        "query": " ".join(str(query or "").casefold().split())[:500],
        "image_query": " ".join(str(image_query or "").casefold().split())[:500],
        "depth": str(depth or "standard"),
        "result_limit": max(0, int(result_limit or 0)),
        "image_limit": max(0, int(image_limit or 0)),
        "parallel_queries": bool(parallel_queries),
        "target_date": str(target_date or ""),
        "strict_date": bool(strict_date),
        "include_media": bool(include_media),
        "provider_version": str(provider_version or "searchpro-v1"),
    }
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def evidence_ttl_seconds(
    query: str,
    *,
    target_date: str = "",
    strict_date: bool = False,
    depth: str = "standard",
) -> int:
    """Use a short TTL for volatile facts and a bounded TTL for stable evidence."""
    if strict_date or target_date or _CURRENT_MARKERS.search(str(query or "")):
        return 2 * 60
    return 15 * 60 if depth == "deep" else 10 * 60


def assert_evidence_only(value: Any, *, path: str = "evidence") -> None:
    """Reject answer-shaped fields recursively before persistence."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key or "").casefold()
            if normalized in FORBIDDEN_ANSWER_FIELDS:
                raise ValueError(
                    f"{path}.{key} is answer output and cannot enter evidence cache"
                )
            assert_evidence_only(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_evidence_only(item, path=f"{path}[{index}]")


def cacheable_evidence(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Project provider metadata onto the strict evidence cache schema."""
    projected = {
        key: copy.deepcopy(metadata[key])
        for key in EVIDENCE_FIELDS
        if key in metadata
    }
    projected.setdefault("schema_version", 2)
    assert_evidence_only(projected)
    return projected
