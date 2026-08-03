"""Trusted scholarly-discovery operation for the paper Skill adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

from .paper_candidates import (
    _paper_candidate_ids_from_model,
    _paper_candidates_from_searchpro,
)


AsyncOperation = Callable[..., Awaitable[Any]]
OperationProvider = Callable[[], AsyncOperation]


def build_paper_search_operation(
    *,
    store: Any,
    user_id: str,
    runtime_env: dict[str, Any],
    paper_scope: dict[str, Any],
    paper_discovery_model: Any,
    provider_search_arxiv_provider: OperationProvider,
    provider_rich_search_provider: OperationProvider,
    record_provider_usage_provider: OperationProvider,
) -> AsyncOperation:
    """Build scholarly discovery with official-first provider verification."""

    async def search_arxiv(
        topic: str = "",
        limit: int = 5,
        titles: list[str] | None = None,
        author: str = "",
        institution: str = "",
        year: int = 0,
        year_from: int = 0,
        year_to: int = 0,
    ) -> str:
        """Search structured academic papers with an arXiv-first provider cascade."""
        clean_topic = str(topic or "").strip()[:240]
        clean_titles = [
            str(title).strip()[:240]
            for title in (titles or [])
            if str(title).strip()
        ][:8]
        clean_author = str(
            paper_scope.get("author") or author or "",
        ).strip()[:160]
        clean_institution = str(
            paper_scope.get("institution") or institution or "",
        ).strip()[:160]
        clean_year = int(paper_scope.get("year") or year or 0)
        clean_year_from = int(
            paper_scope.get("year_from") or year_from or 0,
        )
        clean_year_to = int(
            paper_scope.get("year_to") or year_to or 0,
        )
        requested_limit = int(paper_scope.get("limit") or 0)
        if requested_limit:
            limit = min(
                max(1, int(limit or requested_limit)),
                requested_limit,
            )
        if not clean_topic and not clean_titles and not clean_author:
            raise ValueError("论文主题、准确标题或作者至少需要一项")
        candidate_loader = (
            (
                lambda: _paper_candidate_ids_from_model(
                    paper_discovery_model,
                    topic=clean_topic,
                    author=clean_author,
                    institution=clean_institution,
                    year=clean_year,
                    year_from=clean_year_from,
                    year_to=clean_year_to,
                    limit=limit,
                )
            )
            if paper_discovery_model is not None and not clean_titles
            else None
        )
        provider_args = (
            clean_topic,
            limit,
            clean_titles,
            clean_author,
            clean_year,
            clean_institution,
            clean_year_from,
            clean_year_to,
        )

        async def academic_lookup() -> list[dict[str, Any]]:
            if candidate_loader is None:
                return await provider_search_arxiv_provider()(*provider_args)
            return await provider_search_arxiv_provider()(
                *provider_args,
                candidate_ids_loader=candidate_loader,
            )

        async def makers_search_fallback() -> list[dict[str, Any]]:
            if not (
                paper_discovery_model is not None
                and clean_author
                and clean_institution
                and str(runtime_env.get("WSA_API_KEY") or "").strip()
            ):
                return []
            bounds = " ".join(
                str(value)
                for value in (clean_year or clean_year_from, clean_year_to)
                if int(value or 0)
            )
            query = " ".join(
                value
                for value in (
                    clean_author,
                    clean_institution,
                    clean_topic,
                    bounds,
                    "academic papers publications arXiv DBLP",
                )
                if value
            )
            try:
                try:
                    metadata = await provider_rich_search_provider()(
                        runtime_env,
                        query,
                        depth="basic",
                        result_limit=max(8, min(18, int(limit or 5) * 4)),
                        image_limit=0,
                        include_media=False,
                    )
                finally:
                    await record_provider_usage_provider()(
                        store,
                        user_id,
                        "wsa",
                        "requests",
                        1,
                        source="paper_search_fallback",
                    )
                return await _paper_candidates_from_searchpro(
                    paper_discovery_model,
                    metadata=metadata,
                    topic=clean_topic,
                    author=clean_author,
                    institution=clean_institution,
                    year=clean_year,
                    year_from=clean_year_from,
                    year_to=clean_year_to,
                    limit=limit,
                )
            except Exception as exc:
                logging.warning(
                    "paper Makers search fallback failed error_type=%s",
                    type(exc).__name__,
                )
                return []

        provider_error = ""
        academic_timeout = max(
            8.0,
            min(
                40.0,
                float(runtime_env.get("PAPER_SEARCH_TIMEOUT_SECONDS") or 40),
            ),
        )
        try:
            try:
                academic_rows = await asyncio.wait_for(
                    academic_lookup(),
                    timeout=academic_timeout,
                )
            except Exception as exc:
                logging.warning(
                    "academic provider cascade failed error_type=%s",
                    type(exc).__name__,
                )
                academic_rows = []
            # SearchPro is recovery, not a parallel default. A successful set
            # of officially verified arXiv IDs must not wait for another
            # provider or be diluted with cached prose.
            makers_rows = (
                []
                if academic_rows
                else await makers_search_fallback()
            )
            papers: list[dict[str, Any]] = []
            seen_papers: set[str] = set()
            for paper in [*academic_rows, *makers_rows]:
                identity = (
                    str(paper.get("arxiv_id") or "").strip().lower()
                    or re.sub(
                        r"\W+",
                        " ",
                        str(paper.get("title") or "").lower(),
                    ).strip()
                )
                if not identity or identity in seen_papers:
                    continue
                seen_papers.add(identity)
                papers.append(paper)
                if len(papers) >= max(1, min(8, int(limit or 5))):
                    break
            if not papers:
                provider_error = (
                    "学术索引与 Makers 原生检索本轮没有返回可核实结果"
                )
        except Exception as exc:
            logging.warning("academic discovery failed: %s", exc)
            papers = []
            provider_error = "学术索引本轮没有返回结果"
        return json.dumps({
            "ui_action": "paper_results",
            "papers": papers,
            "topic": clean_topic,
            **({"notice": provider_error} if provider_error else {}),
        }, ensure_ascii=False)

    return search_arxiv


__all__ = ("build_paper_search_operation",)
