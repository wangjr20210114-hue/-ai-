"""Small dependency-free arXiv search adapter."""
from __future__ import annotations
import asyncio
import difflib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

def _search(topic: str, limit: int, title_only: bool = False, author: str = "", year: int = 0) -> list[dict]:
    if title_only:
        search_query = f'ti:"{topic}"'
    elif author:
        search_query = f'au:"{author}"'
    else:
        search_query = f"all:{topic}"
    if 1991 <= year <= 2100:
        search_query += f" AND submittedDate:[{year}01010000 TO {year}12312359]"
    query = urllib.parse.urlencode({"search_query": search_query, "start": 0, "max_results": max(1, min(8, limit)), "sortBy": "relevance", "sortOrder": "descending"})
    request = urllib.request.Request(f"https://export.arxiv.org/api/query?{query}", headers={"User-Agent": "Yuanbao-Agent/1.0 (paper reader)"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(2 * 1024 * 1024)
    root = ET.fromstring(body)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers = []
    for entry in root.findall("atom:entry", ns):
        identifier = entry.findtext("atom:id", "", ns).rstrip("/").split("/")[-1]
        title = " ".join(entry.findtext("atom:title", "", ns).split())
        abstract = " ".join(entry.findtext("atom:summary", "", ns).split())
        authors = [node.findtext("atom:name", "", ns) for node in entry.findall("atom:author", ns)]
        published = entry.findtext("atom:published", "", ns)
        paper_year = int(published[:4]) if published[:4].isdigit() else 0
        normalized_author = _normalized_title(author)
        normalized_authors = _normalized_title(" ".join(authors))
        if year and paper_year != year:
            continue
        if normalized_author and normalized_author not in normalized_authors:
            continue
        if identifier and title:
            papers.append({"title": title, "arxiv_id": identifier, "authors": ", ".join(authors[:8]), "year": paper_year, "abstract_zh": abstract, "key_contribution": abstract[:240], "citations": "arXiv", "arxiv_url": f"https://arxiv.org/abs/{identifier}", "pdf_url": f"https://arxiv.org/pdf/{identifier}.pdf"})
    return papers

def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

def _best_title_match(requested: str, candidates: list[dict]) -> dict | None:
    requested_normalized = _normalized_title(requested)
    ranked = sorted(
        candidates,
        key=lambda paper: difflib.SequenceMatcher(None, requested_normalized, _normalized_title(paper.get("title", ""))).ratio(),
        reverse=True,
    )
    if not ranked:
        return None
    best = ranked[0]
    similarity = difflib.SequenceMatcher(None, requested_normalized, _normalized_title(best.get("title", ""))).ratio()
    if similarity < 0.72:
        return None
    best["title_match"] = round(similarity, 3)
    return best

async def search_arxiv(
    topic: str = "",
    limit: int = 5,
    titles: list[str] | None = None,
    author: str = "",
    year: int = 0,
) -> list[dict]:
    if not year:
        year_match = re.search(r"\b(20\d{2})\b", topic)
        if year_match:
            year = int(year_match.group(1))
            topic = (topic[:year_match.start()] + topic[year_match.end():]).strip()
    if not author:
        tokens = topic.split()
        if 2 <= len(tokens) <= 5 and all(re.fullmatch(r"[A-Z][A-Za-z.-]*", token) for token in tokens):
            author, topic = topic, ""
    if titles:
        semaphore = asyncio.Semaphore(3)
        async def lookup(title: str):
            async with semaphore:
                candidates = await asyncio.to_thread(_search, str(title)[:240], 3, True, author, year)
            match = _best_title_match(title, candidates)
            if match and year and match.get("year") != year:
                return None
            return match
        matched = await asyncio.gather(*(lookup(title) for title in titles[:8]))
        output, seen = [], set()
        for paper in matched:
            if paper and paper["arxiv_id"] not in seen:
                seen.add(paper["arxiv_id"])
                output.append(paper)
            if len(output) >= max(1, min(8, limit)):
                break
        return output
    return await asyncio.to_thread(_search, topic, limit, False, author, year)
