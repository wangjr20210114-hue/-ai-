"""Localized model presentation for provider-independent search evidence."""

from __future__ import annotations

from typing import Any

from agents._domain.search.evidence import SearchEvidence

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
            fallback=(
                text("model.search.media_fallback", language)
                if item.get("vision_fallback")
                or item.get("vision_reviewed") is False
                else ""
            ),
        )
        for item in metadata.get("media", [])
    ) or text("model.search.media_none", language)
    media_status = text(
        (
            "model.search.media_pending"
            if metadata.get("media_pending")
            else "model.search.media_ready"
        ),
        language,
    )
    image_instruction = text(
        (
            "model.search.image_required"
            if require_relevant_image and metadata.get("media")
            else "model.search.image_default"
        ),
        language,
    )
    temporal_instruction = (
        text(
            "model.search.temporal", language,
            target_date=metadata.get("target_date"),
        )
        if metadata.get("strict_date") and metadata.get("target_date")
        else ""
    )
    return text(
        "model.search.evidence", language,
        temporal=temporal_instruction,
        sources=sources or "[]",
        media=media,
        media_status=media_status,
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
