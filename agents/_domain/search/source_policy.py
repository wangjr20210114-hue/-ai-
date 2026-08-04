"""Provider-independent policy for selecting trustworthy search evidence.

The policy deliberately uses only structural signals that generalize across
topics: query relevance, verifiable publication time, institutional host
namespaces, stable provider order, and bounded publisher diversity.  Product-
or industry-specific words belong neither here nor in provider adapters.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


_INSTITUTIONAL_HOST_LABELS = frozenset({"ac", "edu", "gov"})
_NONPROFIT_HOST_LABEL = "org"
_COUNTRY_REGISTRATION_LABELS = frozenset(
    {"ac", "co", "com", "edu", "gov", "net", "org"}
)
RECENT_SOURCE_WINDOW_DAYS = 120


def source_host(url: object) -> str:
    """Return a normalized host without depending on a provider URL type."""
    value = str(url or "").strip().lower()
    if not value:
        return ""
    authority = re.split(
        r"[/?#]", value.split("://", 1)[-1], maxsplit=1
    )[0].rsplit("@", 1)[-1]
    if authority.startswith("["):
        return authority[1:].split("]", 1)[0].strip(".")
    return authority.split(":", 1)[0].strip(".")


def source_domain(url: object) -> str:
    """Return a deterministic publisher domain for diversity accounting.

    Country-code namespaces such as ``example.com.cn`` are handled by their
    structural registration label.  Unknown suffixes conservatively use the
    final two labels; this is intentionally not a hand-maintained publisher
    allowlist.
    """
    host = source_host(url)
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2 or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return host
    if len(labels[-1]) == 2 and labels[-2] in _COUNTRY_REGISTRATION_LABELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def query_match_terms(query: str) -> set[str]:
    """Build lightweight relevance terms without assuming one topic or locale."""
    normalized = str(query or "").lower()
    terms = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9._-]+", normalized)
        if len(token) >= 2
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(sequence) <= 6:
            terms.add(sequence)
        terms.update(
            sequence[index:index + 2]
            for index in range(len(sequence) - 1)
        )
    return terms


def date_from_text(value: str, target_year: int | None = None) -> str:
    """Return a canonical publication date found in provider metadata/text."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit() and len(raw) in {10, 13}:
        try:
            stamp = int(raw) / (1000 if len(raw) == 13 else 1)
            return datetime.fromtimestamp(stamp).date().isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    full = re.search(
        r"(?<!\d)(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?",
        raw,
    )
    if full:
        try:
            return date(
                int(full.group(1)), int(full.group(2)), int(full.group(3))
            ).isoformat()
        except ValueError:
            return ""
    if target_year:
        short = re.search(
            r"(?<!\d)(\d{1,2})[月./-](\d{1,2})日?(?!\d)", raw
        )
        if short:
            try:
                return date(
                    target_year, int(short.group(1)), int(short.group(2))
                ).isoformat()
            except ValueError:
                return ""
    return ""


def source_recency_score(
    item: dict[str, Any], target_date: str, prefer_recent: bool,
) -> tuple[int, str]:
    """Prefer verifiably recent evidence only for a recent-information query."""
    if not target_date or not prefer_recent:
        return 0, ""
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return 0, ""
    published = date_from_text(str(item.get("date") or ""), target.year)
    if not published:
        published = date_from_text(
            f"{item.get('title') or ''} {item.get('snippet') or ''}",
            target.year,
        )
    if not published:
        return -14, ""
    try:
        age_days = (target - date.fromisoformat(published)).days
    except ValueError:
        return -14, ""
    if age_days < 0:
        return -30, published
    if age_days <= 7:
        return 34, published
    if age_days <= 30:
        return 22, published
    if age_days <= RECENT_SOURCE_WINDOW_DAYS:
        return 7, published
    if age_days <= 365:
        return 0, published
    return -24, published


def filter_preferred_recent_sources(
    results: list[dict[str, Any]], target_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Avoid padding a recent-information answer with stale evidence."""
    diagnostics: dict[str, Any] = {
        "applied": False,
        "fresh": 0,
        "stale_or_undated": 0,
    }
    try:
        date.fromisoformat(target_date)
    except (TypeError, ValueError):
        return results, diagnostics
    fresh: list[dict[str, Any]] = []
    for item in results:
        recency_score, published = source_recency_score(item, target_date, True)
        if not published or recency_score <= 0:
            diagnostics["stale_or_undated"] += 1
            continue
        fresh.append({**item, "date": published})
    diagnostics["fresh"] = len(fresh)
    if not fresh:
        return results, diagnostics
    diagnostics["applied"] = True
    return fresh, diagnostics


def source_quality_score(
    item: dict[str, Any], query: str, target_date: str = "",
    prefer_recent: bool = False,
) -> int:
    """Score structural authority, relevance and time without topic lexicons."""
    searchable = (
        f"{item.get('title') or ''}\n{item.get('snippet') or ''}"
    ).lower()
    host_labels = set(source_host(item.get("url")).split("."))
    score = 0
    if host_labels & _INSTITUTIONAL_HOST_LABELS:
        score += 18
    elif _NONPROFIT_HOST_LABEL in host_labels:
        score += 4
    terms = query_match_terms(query)
    score += min(12, sum(term in searchable for term in terms))
    try:
        provider_relevance = float(
            item.get("relevance_score") or item.get("score") or 0
        )
    except (TypeError, ValueError):
        provider_relevance = 0.0
    if provider_relevance == provider_relevance:
        score += round(max(0.0, min(1.0, provider_relevance)) * 12)
    recency_score, _ = source_recency_score(item, target_date, prefer_recent)
    return score + recency_score


def rank_source_results(
    results: list[dict[str, Any]], query: str, target_date: str = "",
    prefer_recent: bool = False,
) -> list[dict[str, Any]]:
    """Stable quality ordering with a second independent publisher when available."""
    ranked = sorted(
        enumerate(results),
        key=lambda pair: (
            -source_quality_score(pair[1], query, target_date, prefer_recent),
            pair[0],
        ),
    )
    if len(ranked) < 2:
        return [item for _, item in ranked]
    chosen: list[tuple[int, dict[str, Any]]] = [ranked[0]]
    first_domain = source_domain(ranked[0][1].get("url"))
    for pair in ranked[1:]:
        candidate_domain = source_domain(pair[1].get("url"))
        if candidate_domain and candidate_domain != first_domain:
            chosen.append(pair)
            break
    chosen.extend(pair for pair in ranked if pair not in chosen)
    output: list[dict[str, Any]] = []
    for _, item in chosen:
        _, published = source_recency_score(item, target_date, prefer_recent)
        output.append({**item, **({"date": published} if published else {})})
    return output


def filter_sources_for_target_date(
    results: list[dict[str, Any]], target_date: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Strictly retain sources whose publication date can be verified."""
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return results, {
            "received": len(results), "kept": len(results),
            "undated": 0, "mismatched": 0,
        }
    kept: list[dict[str, Any]] = []
    undated = 0
    mismatched = 0
    for item in results:
        published = date_from_text(str(item.get("date") or ""), target.year)
        if not published:
            published = date_from_text(
                f"{item.get('title') or ''} {item.get('snippet') or ''}",
                target.year,
            )
        if not published:
            undated += 1
            continue
        if published != target.isoformat():
            mismatched += 1
            continue
        kept.append({**item, "date": published})
    return kept, {
        "received": len(results), "kept": len(kept),
        "undated": undated, "mismatched": mismatched,
    }


__all__ = (
    "RECENT_SOURCE_WINDOW_DAYS",
    "date_from_text",
    "filter_preferred_recent_sources",
    "filter_sources_for_target_date",
    "query_match_terms",
    "rank_source_results",
    "source_domain",
    "source_host",
    "source_quality_score",
    "source_recency_score",
)
