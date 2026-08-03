"""Source-bound academic candidate extraction for the papers Skill adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from .contracts import PaperKnowledgeCandidates, PaperSearchEvidenceCandidates


async def _paper_candidate_ids_from_model(
    model,
    *,
    topic: str,
    author: str,
    institution: str,
    year: int,
    year_from: int,
    year_to: int,
    limit: int,
    timeout_seconds: float = 8.0,
) -> list[str]:
    """Ask a fast model for high-confidence identities, never final metadata."""
    if model is None:
        return []
    current_year = datetime.now(timezone.utc).year
    prompt = (
        "Use only your pretrained/internal scholarly knowledge. Do not search, "
        "browse, call tools, or explain your reasoning. Propose at most the "
        "requested number of exact arXiv paper identities matching every "
        "constraint. A named scholar must be the scholar at the requested "
        "institution, not a homonym. Include an arXiv identifier only when you "
        "know the exact ID with high confidence; omit uncertain papers and "
        "return an empty list when necessary. These are only candidates: the "
        "application will verify every ID against official arXiv metadata."
    )
    payload = json.dumps({
        "topic": topic,
        "author": author,
        "institution": institution,
        "year": year,
        "year_from": year_from,
        "year_to": year_to,
        "result_limit": max(1, min(8, int(limit or 5))),
        "current_year": current_year,
    }, ensure_ascii=False)
    started_at = time.monotonic()
    try:
        chain = model.with_structured_output(
            PaperKnowledgeCandidates,
            method="function_calling",
            include_raw=True,
        )
        response = await asyncio.wait_for(
            chain.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload},
            ]),
            timeout=max(1.0, min(10.0, float(timeout_seconds))),
        )
        parsed = response.get("parsed") if isinstance(response, dict) else response
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        raw_candidates = (
            parsed.get("candidates")
            if isinstance(parsed, dict) and isinstance(parsed.get("candidates"), list)
            else []
        )
        candidate_ids = list(dict.fromkeys(
            str(candidate.get("arxiv_id") or "").strip()[:80]
            for candidate in raw_candidates[:8]
            if isinstance(candidate, dict)
            and str(candidate.get("arxiv_id") or "").strip()
        ))
        logging.info(
            "paper knowledge candidates=%s elapsed_ms=%s",
            len(candidate_ids),
            round((time.monotonic() - started_at) * 1000),
        )
        return candidate_ids
    except Exception as exc:
        logging.warning(
            "paper knowledge proposal unavailable error_type=%s elapsed_ms=%s",
            type(exc).__name__,
            round((time.monotonic() - started_at) * 1000),
        )
        return []


async def _paper_candidates_from_searchpro(
    model,
    *,
    metadata: dict[str, Any],
    topic: str,
    author: str,
    institution: str,
    year: int,
    year_from: int,
    year_to: int,
    limit: int,
    timeout_seconds: float = 6.0,
) -> list[dict[str, Any]]:
    """Convert native Makers search evidence into strictly source-bound cards."""
    if model is None:
        return []
    raw_sources = metadata.get("results") if isinstance(metadata, dict) else None
    sources = [
        {
            "id": str(source.get("id") or "")[:80],
            "title": str(source.get("title") or "")[:300],
            "snippet": str(source.get("snippet") or "")[:700],
            "url": str(source.get("url") or "")[:1000],
            "date": str(source.get("date") or "")[:40],
        }
        for source in (raw_sources if isinstance(raw_sources, list) else [])
        if (
            isinstance(source, dict)
            and str(source.get("id") or "").strip()
            and str(source.get("url") or "").startswith("https://")
        )
    ][:18]
    if not sources:
        return []
    source_by_id = {source["id"]: source for source in sources}
    prompt = (
        "Select academic papers only from the supplied Makers SearchPro evidence. "
        "Return the fixed schema and no prose. Every candidate must match the "
        "named author identity, institution, topic and year constraints. Use an "
        "exact supplied source_id; never invent a source, title, author, year, or "
        "identifier. The source may be an arXiv, DBLP, DOI, publisher, or official "
        "research page. Include arxiv_id only if the exact identifier is visibly "
        "present in that source record. Omit uncertain or merely related records."
    )
    payload = json.dumps({
        "constraints": {
            "topic": topic,
            "author": author,
            "institution": institution,
            "year": year,
            "year_from": year_from,
            "year_to": year_to,
            "limit": max(1, min(8, int(limit or 5))),
        },
        "sources": sources,
    }, ensure_ascii=False)[:16_000]
    try:
        chain = model.with_structured_output(
            PaperSearchEvidenceCandidates,
            method="function_calling",
            include_raw=True,
        )
        response = await asyncio.wait_for(
            chain.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload},
            ]),
            timeout=max(1.0, min(8.0, float(timeout_seconds))),
        )
        parsed = response.get("parsed") if isinstance(response, dict) else response
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        candidates = (
            parsed.get("candidates")
            if isinstance(parsed, dict) and isinstance(parsed.get("candidates"), list)
            else []
        )
    except Exception as exc:
        logging.warning(
            "paper SearchPro evidence extraction unavailable error_type=%s",
            type(exc).__name__,
        )
        return []

    output: list[dict[str, Any]] = []
    for candidate in candidates[:8]:
        if not isinstance(candidate, dict):
            continue
        source = source_by_id.get(str(candidate.get("source_id") or "").strip())
        if not source:
            continue
        title = " ".join(str(candidate.get("title") or "").split())[:300]
        normalized_source_evidence = " ".join(
            (source["url"], source["title"], source["snippet"], source["date"])
        ).casefold()
        if not title or " ".join(title.casefold().split()) not in " ".join(
            normalized_source_evidence.split()
        ):
            title = source["title"]
        arxiv_id = str(candidate.get("arxiv_id") or "").strip()
        if (
            arxiv_id
            and (
                not re.fullmatch(
                    r"(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
                    arxiv_id,
                    flags=re.I,
                )
                or arxiv_id.casefold() not in normalized_source_evidence
            )
        ):
            arxiv_id = ""
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
        source_url = source["url"]
        source_name = (
            "arXiv"
            if "arxiv.org/" in source_url
            else ("DBLP" if "dblp.org/" in source_url else "Makers SearchPro")
        )
        authors = ", ".join(value for value in (
            str(raw_value or "").strip()
            for raw_value in (candidate.get("authors") or [])[:12]
        ) if value and value.casefold() in normalized_source_evidence)
        paper_year = int(candidate.get("year") or 0)
        if paper_year and str(paper_year) not in normalized_source_evidence:
            paper_year = 0
        output.append({
            "title": title,
            "arxiv_id": arxiv_id,
            "authors": authors,
            "year": paper_year,
            "abstract_zh": source["snippet"],
            "key_contribution": "",
            "citations": f"{source_name} · Makers 原生检索核实",
            "source": source_name,
            "source_url": source_url,
            "arxiv_url": arxiv_url,
            "pdf_url": (
                f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                if arxiv_id else ""
            ),
        })
        if len(output) >= max(1, min(8, int(limit or 5))):
            break
    return output


__all__ = (
    "_paper_candidate_ids_from_model",
    "_paper_candidates_from_searchpro",
)
