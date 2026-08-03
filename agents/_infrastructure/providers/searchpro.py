"""SearchPro adapter translating provider dictionaries into domain evidence."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from agents._application.search.ports import MediaCallback
from agents._application.search.search_use_case import SearchExecution, SearchRequest
from agents._domain.search.evidence import ReviewedMedia, SearchEvidence, SearchSource
from agents._infrastructure.providers.rich_search import rich_search as provider_rich_search


def _to_evidence(metadata: Mapping[str, Any]) -> SearchEvidence:
    raw_sources = metadata.get("results")
    if not isinstance(raw_sources, (list, tuple)):
        raw_sources = metadata.get("sources")
    sources = tuple(
        SearchSource.from_dict(item)
        for item in (raw_sources or ())
        if isinstance(item, Mapping)
    )
    source_urls = {source.id: source.url for source in sources}
    media = tuple(
        ReviewedMedia.from_dict(item)
        for item in (metadata.get("media") or ())
        if isinstance(item, Mapping)
        and item.get("vision_reviewed") is True
        and str(item.get("source_id") or "") in source_urls
        and str(item.get("source_url") or "")
        == source_urls[str(item.get("source_id") or "")]
    )
    return SearchEvidence(
        query=str(metadata.get("query") or ""),
        sources=sources,
        media=media,
        total=int(metadata.get("total") or len(sources)),
        media_pending=metadata.get("media_pending") is True,
    )


class SearchProGateway:
    def __init__(self, env: Mapping[str, Any]) -> None:
        self._env = dict(env)

    async def search(
        self,
        request: SearchRequest,
        *,
        on_media: MediaCallback | None = None,
    ) -> SearchExecution:
        background_tasks: list[asyncio.Task] = []

        async def publish(_metadata: dict[str, Any]) -> None:
            # Supplying a callback selects rich_search's non-blocking path.
            # Per-turn callbacks are attached to the normalized tasks below so
            # coalesced callers can each receive the same reviewed result.
            return None

        async def normalize_media(task: asyncio.Task) -> SearchEvidence:
            evidence = _to_evidence(await task)
            if on_media is not None:
                await on_media(evidence)
            return evidence

        progressive = request.media_mode == "progressive"
        metadata = await provider_rich_search(
            self._env,
            request.query,
            image_query=request.image_query,
            depth=request.depth,
            result_limit=request.result_limit,
            image_limit=request.image_limit,
            target_date=request.target_date,
            strict_date=request.strict_date,
            parallel_queries=request.parallel_queries,
            media_callback=publish if progressive else None,
            background_tasks=background_tasks if progressive else None,
            include_media=request.media_mode != "disabled",
        )
        evidence = _to_evidence(metadata)
        if request.media_mode == "blocking" and on_media is not None:
            await on_media(evidence)
        normalized_tasks = tuple(
            asyncio.create_task(normalize_media(task))
            for task in background_tasks
        )
        return SearchExecution(
            evidence=evidence,
            media_tasks=normalized_tasks,
            provider_request_count=1,
            metadata=dict(metadata),
        )
