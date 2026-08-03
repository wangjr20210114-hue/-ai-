"""Trusted rich-search operation backed by the application SearchUseCase."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from ..._infrastructure.makers.evidence_cache import (
    get_or_compute_search_evidence,
    save_search_evidence,
)
from ..._models.search_evidence import (
    evidence_ttl_seconds,
    search_evidence_key,
)
from .visual_context import TurnVisualContext


AsyncOperation = Callable[..., Awaitable[Any]]
OperationProvider = Callable[[], Callable[..., Any]]


def build_rich_search_operation(
    *,
    store: Any,
    user_id: str,
    conversation_id: str,
    runtime_env: dict[str, Any],
    time_scope: dict[str, Any],
    visual_context: TurnVisualContext,
    progressive_media: bool,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None,
    background_tasks: list[asyncio.Task] | None,
    media_enabled: bool,
    planned_media_preferred: bool,
    planned_search_query: str,
    planned_image_query: str,
    force_search_refresh: bool,
    search_use_case_operation: Callable[[str, str, str], Awaitable[str]] | None,
    search_result_limit: int,
    search_image_limit: int,
    parallel_image_search: bool,
    provider_rich_search_provider: OperationProvider,
    evidence_for_model_provider: OperationProvider,
    record_provider_usage_provider: OperationProvider,
    record_vision_diagnostics_provider: OperationProvider,
) -> AsyncOperation:
    """Build one turn-local adapter with one provider decision per search plan."""

    rich_search_task: asyncio.Task | None = None
    rich_search_invocations = 0
    rich_search_provider_calls = 0

    async def rich_search(
        query: str,
        image_query: str = "",
        depth: str = "standard",
    ) -> str:
        """Run one fresh planner-shaped rich search per turn."""
        nonlocal rich_search_task, rich_search_invocations
        nonlocal rich_search_provider_calls
        rich_search_invocations += 1
        if search_use_case_operation is not None:
            # Search orchestration belongs to the application use case. The
            # trusted adapter keeps the established model-facing tool shape.
            if rich_search_task is None:
                rich_search_task = asyncio.create_task(
                    search_use_case_operation(query, image_query, depth),
                )
            serialized = await rich_search_task
            try:
                result = json.loads(serialized)
                metadata = (
                    result.get("search_results")
                    if isinstance(result, dict)
                    else None
                )
                if isinstance(metadata, dict):
                    search_config = dict(metadata.get("search_config") or {})
                    metadata["search_config"] = {
                        **search_config,
                        "turn_tool_invocations": rich_search_invocations,
                    }
                    visual_context.add(
                        str(item.get("url") or "")
                        for item in (metadata.get("media") or [])
                        if isinstance(item, dict)
                    )
                serialized = json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            return serialized

        if rich_search_task is None:
            clean_query = str(planned_search_query or query or "").strip()[:500]
            clean_image_query = (
                str(planned_image_query or image_query or "").strip()[:500]
                if media_enabled
                else ""
            )
            if not clean_query:
                raise ValueError("富搜索查询不能为空")
            clean_depth = (
                depth
                if depth in {"basic", "standard", "deep"}
                else "standard"
            )
            target_date = str(time_scope.get("target_date") or "")
            strict_date = bool(time_scope.get("strict_date"))
            cache_key = search_evidence_key(
                query=clean_query,
                image_query=clean_image_query,
                depth=clean_depth,
                result_limit=search_result_limit,
                image_limit=search_image_limit,
                parallel_queries=parallel_image_search,
                target_date=target_date,
                strict_date=strict_date,
                include_media=media_enabled,
            )
            cache_ttl = evidence_ttl_seconds(
                clean_query,
                target_date=target_date,
                strict_date=strict_date,
                depth=clean_depth,
            )

            async def run_once() -> str:
                nonlocal rich_search_provider_calls
                logging.info(
                    "rich_search provider_call conversation=%s media=%s",
                    conversation_id,
                    media_enabled,
                )

                async def publish_enriched_media(
                    enriched: dict[str, Any],
                ) -> None:
                    completed = {**enriched, "media_pending": False}
                    await record_vision_diagnostics_provider()(
                        store,
                        user_id,
                        completed.get("vision_diagnostics"),
                        source="rich_search_media",
                    )
                    if media_callback is not None:
                        await media_callback(completed)

                async def publish_and_cache_media(
                    enriched: dict[str, Any],
                ) -> None:
                    await save_search_evidence(
                        store,
                        user_id,
                        cache_key,
                        {**enriched, "media_pending": False},
                        ttl_seconds=cache_ttl,
                    )
                    await publish_enriched_media(enriched)

                async def provider_call() -> dict[str, Any]:
                    nonlocal rich_search_provider_calls
                    rich_search_provider_calls += 1
                    try:
                        return await provider_rich_search_provider()(
                            runtime_env,
                            clean_query,
                            image_query=clean_image_query,
                            depth=clean_depth,
                            target_date=target_date,
                            strict_date=strict_date,
                            media_callback=(
                                publish_and_cache_media
                                if progressive_media and media_enabled
                                else None
                            ),
                            background_tasks=(
                                background_tasks
                                if progressive_media and media_enabled
                                else None
                            ),
                            include_media=media_enabled,
                            result_limit=search_result_limit,
                            image_limit=search_image_limit,
                            parallel_queries=parallel_image_search,
                        )
                    finally:
                        await record_provider_usage_provider()(
                            store,
                            user_id,
                            "wsa",
                            "requests",
                            1,
                            source="rich_search",
                        )

                cached = await get_or_compute_search_evidence(
                    store,
                    user_id,
                    cache_key,
                    provider_call,
                    ttl_seconds=cache_ttl,
                    bypass_cache=force_search_refresh,
                )
                metadata = cached.metadata
                metadata["cache"] = {
                    "kind": "evidence_only",
                    "hit": cached.cache_hit,
                    "coalesced": cached.coalesced,
                    "ttl_seconds": cache_ttl,
                    "answer_cached": False,
                    "bypassed": force_search_refresh,
                }
                if not progressive_media:
                    await record_vision_diagnostics_provider()(
                        store,
                        user_id,
                        metadata.get("vision_diagnostics"),
                        source="rich_search_media",
                    )
                visual_context.add(
                    str(item.get("url") or "")
                    for item in metadata.get("media", [])
                    if isinstance(item, dict)
                )
                return json.dumps({
                    "ui_action": "rich_search_results",
                    "search_results": metadata,
                    "papers": [],
                    "evidence": evidence_for_model_provider()(
                        metadata,
                        require_relevant_image=planned_media_preferred,
                    ),
                }, ensure_ascii=False)

            rich_search_task = asyncio.create_task(run_once())

        serialized = await rich_search_task
        result = json.loads(serialized)
        metadata = (
            result.get("search_results")
            if isinstance(result, dict)
            else None
        )
        if isinstance(metadata, dict):
            search_config = metadata.get("search_config")
            if not isinstance(search_config, dict):
                search_config = {}
            metadata["search_config"] = {
                **search_config,
                "turn_tool_invocations": rich_search_invocations,
                "turn_provider_calls": rich_search_provider_calls,
            }
            logging.info(
                "rich_search turn_audit conversation=%s invocations=%s "
                "provider_calls=%s",
                conversation_id,
                rich_search_invocations,
                rich_search_provider_calls,
            )
        return json.dumps(result, ensure_ascii=False)

    return rich_search


__all__ = ("build_rich_search_operation",)
