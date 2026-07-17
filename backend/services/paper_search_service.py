"""Reusable paper-search application service.

It owns query parsing, non-blocking arXiv retrieval, result normalization, and
optional abstract translation. REST routes and Agent skills share this service;
neither calls another local HTTP endpoint.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest


PAPER_SEARCH_PROMPT = """你是学术论文搜索助手。把用户需求转换为 arXiv 查询参数。
输出严格 JSON 对象：
{"query":"...", "max_results":5, "year_from":null}
规则：作者全名使用 au:\"Name\"；中文关键词翻译成英文；数量 1-10；未指定年份填 null。"""


class PaperSearchParams(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)
    year_from: int | None = Field(default=None, ge=1991, le=datetime.now().year + 1)


class PaperTranslation(BaseModel):
    index: int
    abstract_zh: str
    key_contribution: str = ""


class PaperTranslationBatch(BaseModel):
    items: list[PaperTranslation] = Field(default_factory=list)


def _search_arxiv_sync(query: str, max_results: int, year_from: int | None) -> list[dict[str, Any]]:
    import arxiv as arxiv_lib

    search = arxiv_lib.Search(
        query=query,
        max_results=max_results * 2,
        sort_by=arxiv_lib.SortCriterion.Relevance,
    )
    raw_results = list(arxiv_lib.Client().results(search))
    papers: list[dict[str, Any]] = []
    for result in raw_results:
        if year_from and result.published.year < year_from:
            continue
        arxiv_id = result.entry_id.split("/")[-1].split("v")[0]
        papers.append(
            {
                "title": result.title.replace("\n", " ").strip(),
                "arxiv_id": arxiv_id,
                "authors": ", ".join(author.name for author in result.authors[:6]),
                "year": result.published.year,
                "abstract_zh": result.summary[:500].replace("\n", " ").strip(),
                "key_contribution": "",
                "citations": "",
                "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            }
        )
        if len(papers) >= max_results:
            break
    return papers


class PaperSearchService:
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    async def parse_params(
        self,
        user_message: str,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> PaperSearchParams:
        fallback = PaperSearchParams(query=user_message, max_results=5)
        if self.gateway is None or not settings.deepseek_ready:
            return fallback
        try:
            return await self.gateway.complete_json(
                ModelRequest(
                    messages=[
                        {"role": "system", "content": PAPER_SEARCH_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    provider="deepseek",
                    model=settings.deepseek_model,
                    max_tokens=240,
                    temperature=0.2,
                    operation="paper_query_parse",
                ),
                PaperSearchParams,
                CallContext(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    skill_name="paper",
                ),
            )
        except Exception:
            return fallback

    async def search(
        self,
        *,
        topic: str,
        user_message: str = "",
        max_results: int | None = None,
        year_from: int | None = None,
        run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        query_text = user_message.strip() or f"帮我找关于{topic}的论文"
        parsed = await self.parse_params(
            query_text,
            run_id=run_id,
            conversation_id=conversation_id,
        )
        if max_results is not None:
            parsed.max_results = max(1, min(int(max_results), 10))
        if year_from is not None:
            parsed.year_from = int(year_from)
        papers = await asyncio.to_thread(
            _search_arxiv_sync,
            parsed.query,
            parsed.max_results,
            parsed.year_from,
        )
        if papers and self.gateway is not None and settings.deepseek_ready:
            await self._translate_abstracts(
                papers,
                run_id=run_id,
                conversation_id=conversation_id,
            )
        return {
            "papers": papers,
            "topic": topic,
            "query": parsed.query,
            "max_results": parsed.max_results,
            "year_from": parsed.year_from,
        }

    async def _translate_abstracts(
        self,
        papers: list[dict[str, Any]],
        *,
        run_id: str | None,
        conversation_id: str | None,
    ) -> None:
        paper_text = "\n\n".join(
            f"[{index}] {paper['title']}\n{paper['abstract_zh']}"
            for index, paper in enumerate(papers)
        )
        try:
            translated = await self.gateway.complete_json(
                ModelRequest(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "把每篇英文摘要翻译成不超过100字的中文，并概括一句核心贡献。"
                                "输出严格 JSON 对象：{\"items\":[{\"index\":0,"
                                "\"abstract_zh\":\"...\",\"key_contribution\":\"...\"}]}"
                            ),
                        },
                        {"role": "user", "content": paper_text},
                    ],
                    provider="deepseek",
                    model=settings.deepseek_model,
                    max_tokens=1800,
                    temperature=0.3,
                    operation="paper_abstract_translation",
                ),
                PaperTranslationBatch,
                CallContext(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    skill_name="paper",
                ),
            )
        except Exception:
            return
        for item in translated.items:
            if 0 <= item.index < len(papers):
                papers[item.index]["abstract_zh"] = item.abstract_zh
                papers[item.index]["key_contribution"] = item.key_contribution
