"""Structured, source-bound media metadata for rich search answers.

The model is never allowed to invent or echo image URLs.  Search retrieval owns
the URLs and exposes stable ``media-*`` identifiers that the model may reference
inside the answer.  The frontend resolves those identifiers from trusted
metadata delivered beside the text.
"""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from services.safe_http import validate_public_url


class SourceReference(BaseModel):
    id: str
    source: str = "web"
    title: str = ""
    snippet: str = ""
    url: str
    account_name: str = ""
    date: str = ""


class MediaAsset(BaseModel):
    id: str
    kind: str = "image"
    url: str
    source_id: str = ""
    source_url: str = ""
    source_title: str = ""
    alt: str = ""
    caption: str = ""
    attribution: str = ""
    generated: bool = False


class RichSearchMetadata(BaseModel):
    schema_version: int = 1
    query: str
    results: list[SourceReference] = Field(default_factory=list)
    media: list[MediaAsset] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    total: int = 0


def build_source_references(
    results: list[dict[str, Any]], *, limit: int = 12
) -> list[SourceReference]:
    """Create deterministic source IDs and remove duplicate URLs."""
    references: list[SourceReference] = []
    seen: set[str] = set()
    for result in results:
        url = str(result.get("url") or result.get("article_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        references.append(
            SourceReference(
                id=f"source-{len(references) + 1}",
                source=str(result.get("source") or "web"),
                title=str(result.get("title") or ""),
                snippet=str(result.get("snippet") or "")[:240],
                url=url,
                account_name=str(result.get("account_name") or ""),
                date=str(result.get("date") or ""),
            )
        )
        if len(references) >= limit:
            break
    return references


async def build_media_assets(
    candidates: list[dict[str, Any]],
    descriptions: list[dict[str, str]],
    sources: list[SourceReference],
    *,
    limit: int = 8,
) -> list[MediaAsset]:
    """Validate, deduplicate and bind images to their source documents."""
    description_by_url = {
        str(item.get("url") or ""): str(item.get("description") or "").strip()
        for item in descriptions
        if item.get("url")
    }
    source_by_url = {source.url: source for source in sources}
    seen: set[str] = set()
    prepared: list[dict[str, Any]] = []
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        prepared.append(candidate)
        if len(prepared) >= limit * 2:
            break

    validations = await asyncio.gather(
        *(validate_public_url(str(item.get("url") or "")) for item in prepared),
        return_exceptions=True,
    )
    assets: list[MediaAsset] = []
    for candidate, validation in zip(prepared, validations):
        if isinstance(validation, Exception):
            continue
        url = str(candidate.get("url") or "").strip()
        source_url = str(candidate.get("source_url") or "").strip()
        source = source_by_url.get(source_url)
        description = description_by_url.get(url, "")
        source_title = str(candidate.get("source_title") or (source.title if source else ""))
        original_alt = str(candidate.get("alt") or "").strip()

        # Caption priority: vision description > original alt > source title
        if description:
            caption = description
            if original_alt and original_alt not in description:
                caption = f"{description}（原文：{original_alt[:30]}）"
        elif original_alt:
            caption = original_alt
        elif source_title:
            caption = f"{source_title}（第{len(assets) + 1}张）"
        else:
            caption = "相关图片"
        assets.append(
            MediaAsset(
                id=f"media-{len(assets) + 1}",
                url=url,
                source_id=source.id if source else "",
                source_url=source_url,
                source_title=source_title,
                alt=caption,
                caption=caption,
                attribution=source_title,
            )
        )
        if len(assets) >= limit:
            break
    return assets


def referenced_media_ids(content: str) -> set[str]:
    """Return structured media identifiers referenced by model output."""
    import re

    return set(re.findall(r"\[\[image:(media-[a-zA-Z0-9_-]+)\]\]", content))
