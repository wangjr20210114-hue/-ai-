"""Localized model presentation for provider-independent search evidence."""

from __future__ import annotations

from typing import Any

from agents._domain.search.evidence import SearchEvidence
from agents._domain.search.source_policy import source_domain

from ..i18n import normalize_language, text


def evidence_for_model(
    metadata: dict[str, Any], *, require_relevant_image: bool = False,
    response_language: object = "zh-CN",
) -> str:
    """Render structured evidence without leaking presentation into domain values."""
    language = normalize_language(response_language)
    media_source_ids = {
        str(item.get("source_id") or "")
        for item in metadata.get("media", [])
        if item.get("source_id")
    }
    sources = "\n".join(
        text(
            "model.search.source_line", language,
            id=item.get("id") or "source",
            source_type=item.get("source") or "web",
            title=item["title"], url=item["url"],
            date=item.get("date") or "N/A", snippet=item["snippet"],
            publisher=item.get("publisher") or "N/A",
            publisher_domain=(
                item.get("publisher_domain") or source_domain(item.get("url"))
                or "N/A"
            ),
            relevance=item.get("relevance_score") or "N/A",
            has_image=(
                "true"
                if str(item.get("id") or "") in media_source_ids
                else "false"
            ),
        )
        for item in metadata.get("results", [])
    )
    media = "\n".join(
        text(
            "model.search.media_line", language,
            id=item.get("id") or "media",
            source_id=item.get("source_id") or "none",
            caption=item["caption"], url=item["url"],
            source=(
                item.get("source_title")
                or item.get("source_url")
                or "unknown"
            ),
        )
        for item in metadata.get("media", [])
    )
    media_section = (
        text(
            "model.search.media_section", language,
            media=media,
            media_status=text("model.search.media_ready", language),
        )
        if media
        else ""
    )
    image_instruction = (
        text("model.search.image_required", language)
        if require_relevant_image and media
        else ""
    )
    target_date = str(metadata.get("target_date") or "")
    search_config = metadata.get("search_config")
    prefer_recent = bool(
        isinstance(search_config, dict)
        and search_config.get("prefer_recent")
    )
    if metadata.get("strict_date") and target_date:
        temporal_instruction = text(
            "model.search.temporal", language,
            target_date=target_date,
        )
    elif target_date and prefer_recent:
        temporal_instruction = text(
            "model.search.recency", language,
            target_date=target_date,
        )
    else:
        temporal_instruction = ""
    publisher_domains = {
        str(item.get("publisher_domain") or source_domain(item.get("url")))
        for item in metadata.get("results", [])
        if str(
            item.get("publisher_domain") or source_domain(item.get("url"))
        ).strip()
    }
    source_diversity = text(
        (
            "model.search.diversity_available"
            if len(publisher_domains) >= 2
            else "model.search.diversity_limited"
        ),
        language,
        count=len(publisher_domains),
    )
    return text(
        "model.search.evidence", language,
        temporal=temporal_instruction,
        sources=sources or "[]",
        source_diversity=source_diversity,
        media_section=media_section,
        image_instruction=image_instruction,
    )


def present_search_evidence(
    evidence: SearchEvidence, *, response_language: object = "zh-CN",
) -> str:
    """Adapt the immutable domain value to the model presentation contract."""
    return evidence_for_model(
        {
            "results": [
                {
                    **source.to_dict(),
                    "date": source.published_at,
                    "source": "web",
                }
                for source in evidence.sources
            ],
            "media": [item.to_dict() for item in evidence.media],
            "media_pending": evidence.media_pending,
        },
        response_language=response_language,
    )


__all__ = ("evidence_for_model", "present_search_evidence")
