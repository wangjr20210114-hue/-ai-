"""Small dependency-free academic discovery cascade.

A fast model may propose exact arXiv identities, but official arXiv metadata
must verify them. DBLP affiliation profiles disambiguate named scholars, and
strictly filtered Crossref metadata is the final fallback.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable


def _ssl_context() -> ssl.SSLContext:
    """Use certifi in managed Python images while retaining the system fallback."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _year_bounds(year: int, year_from: int, year_to: int) -> tuple[int, int]:
    current = datetime.now(timezone.utc).year
    exact = int(year or 0)
    if 1991 <= exact <= current + 1:
        return exact, exact
    start = int(year_from or 0)
    end = int(year_to or 0)
    start = start if 1991 <= start <= current + 1 else 0
    end = end if 1991 <= end <= current + 1 else 0
    if start and not end:
        end = current
    if end and not start:
        start = end
    if start and end and start > end:
        start, end = end, start
    return start, end


def _canonical_arxiv_id(value: str) -> str:
    """Return a safe arXiv identifier, never an arbitrary model-provided URL."""
    candidate = str(value or "").strip()
    candidate = re.sub(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", candidate, flags=re.I)
    candidate = re.sub(r"\.pdf$", "", candidate, flags=re.I)
    candidate = re.sub(r"^arxiv\s*:\s*", "", candidate, flags=re.I)
    candidate = candidate.split("?", 1)[0].split("#", 1)[0].strip("/")
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", candidate, flags=re.I):
        return candidate
    if re.fullmatch(
        r"[a-z][a-z0-9.-]*/\d{7}(?:v\d+)?",
        candidate,
        flags=re.I,
    ):
        return candidate
    return ""


def _author_matches(authors: list[str], requested: str) -> bool:
    requested_tokens = set(_normalized_title(requested).split())
    if not requested_tokens:
        return True
    return any(
        requested_tokens.issubset(set(_normalized_title(author).split()))
        for author in authors
    )


def _parse_arxiv_feed(
    body: bytes,
    *,
    author: str = "",
    year_from: int = 0,
    year_to: int = 0,
    expected_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers: list[dict[str, Any]] = []
    expected = {
        re.sub(r"v\d+$", "", identifier, flags=re.I)
        for identifier in (expected_ids or set())
        if identifier
    }
    for entry in root.findall("atom:entry", ns):
        identifier = _canonical_arxiv_id(
            entry.findtext("atom:id", "", ns).rstrip("/").split("/abs/")[-1]
        )
        canonical_without_version = re.sub(r"v\d+$", "", identifier, flags=re.I)
        if expected and canonical_without_version not in expected:
            continue
        title = " ".join(entry.findtext("atom:title", "", ns).split())
        abstract = " ".join(entry.findtext("atom:summary", "", ns).split())
        authors = [
            node.findtext("atom:name", "", ns)
            for node in entry.findall("atom:author", ns)
            if node.findtext("atom:name", "", ns)
        ]
        published = entry.findtext("atom:published", "", ns)
        paper_year = int(published[:4]) if published[:4].isdigit() else 0
        if year_from and paper_year < year_from:
            continue
        if year_to and paper_year > year_to:
            continue
        if author and not _author_matches(authors, author):
            continue
        if identifier and title:
            papers.append({
                "title": title,
                "arxiv_id": identifier,
                "authors": ", ".join(authors[:8]),
                "year": paper_year,
                "abstract_zh": abstract,
                "key_contribution": abstract[:240],
                "citations": "arXiv",
                "source": "arXiv",
                "source_url": f"https://arxiv.org/abs/{identifier}",
                "arxiv_url": f"https://arxiv.org/abs/{identifier}",
                "pdf_url": f"https://arxiv.org/pdf/{identifier}.pdf",
            })
    return papers


def _search_arxiv_sync(
    topic: str,
    limit: int,
    title_only: bool = False,
    author: str = "",
    year_from: int = 0,
    year_to: int = 0,
) -> list[dict[str, Any]]:
    if title_only:
        search_query = f'ti:"{topic}"'
    elif author:
        search_query = f'au:"{author}"'
    else:
        search_query = f"all:{topic}"
    if year_from and year_to:
        search_query += (
            f" AND submittedDate:[{year_from}01010000 TO {year_to}12312359]"
        )
    query = urllib.parse.urlencode({
        "search_query": search_query,
        "start": 0,
        "max_results": max(1, min(12, limit)),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    request = urllib.request.Request(
        f"https://export.arxiv.org/api/query?{query}",
        headers={"User-Agent": "Floris/1.0 (academic discovery)"},
    )
    with urllib.request.urlopen(
        request,
        timeout=18,
        context=_ssl_context(),
    ) as response:
        body = response.read(2 * 1024 * 1024)
    return _parse_arxiv_feed(
        body,
        author=author,
        year_from=year_from,
        year_to=year_to,
    )


def _lookup_arxiv_ids_sync(
    candidate_ids: list[str],
    author: str = "",
    year_from: int = 0,
    year_to: int = 0,
) -> list[dict[str, Any]]:
    """Verify model-proposed identifiers through the official arXiv API."""
    safe_ids = list(dict.fromkeys(
        identifier
        for identifier in (
            _canonical_arxiv_id(value) for value in candidate_ids[:12]
        )
        if identifier
    ))[:8]
    if not safe_ids:
        return []
    query = urllib.parse.urlencode({
        "id_list": ",".join(safe_ids),
        "max_results": len(safe_ids),
    })
    request = urllib.request.Request(
        f"https://export.arxiv.org/api/query?{query}",
        headers={"User-Agent": "Floris/1.0 (academic discovery)"},
    )
    with urllib.request.urlopen(
        request,
        timeout=18,
        context=_ssl_context(),
    ) as response:
        body = response.read(2 * 1024 * 1024)
    rows = _parse_arxiv_feed(
        body,
        author=author,
        year_from=year_from,
        year_to=year_to,
        expected_ids=set(safe_ids),
    )
    order = {
        re.sub(r"v\d+$", "", identifier, flags=re.I): index
        for index, identifier in enumerate(safe_ids)
    }
    rows.sort(key=lambda paper: order.get(
        re.sub(r"v\d+$", "", str(paper.get("arxiv_id") or ""), flags=re.I),
        len(order),
    ))
    return rows


def _best_title_match(requested: str, candidates: list[dict]) -> dict | None:
    requested_normalized = _normalized_title(requested)
    return next(
        (
            paper for paper in candidates
            if requested_normalized
            and _normalized_title(paper.get("title", "")) == requested_normalized
        ),
        None,
    )


def _crossref_date(item: dict[str, Any]) -> int:
    for key in ("published", "published-online", "published-print", "issued", "created"):
        value = item.get(key)
        parts = value.get("date-parts") if isinstance(value, dict) else None
        if (
            isinstance(parts, list)
            and parts
            and isinstance(parts[0], list)
            and parts[0]
        ):
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return 0


def _xml_text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _institution_matches(value: str, institution: str) -> bool:
    requested = set(_normalized_title(institution).split())
    candidate = set(_normalized_title(value).split())
    return bool(requested and requested.issubset(candidate))


def _dblp_json_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    hits = ((payload.get("result") or {}).get("hits") or {}).get("hit") or []
    if isinstance(hits, dict):
        hits = [hits]
    return [item for item in hits if isinstance(item, dict)]


@lru_cache(maxsize=128)
def _dblp_profile_cached(
    author: str,
    institution: str,
    _cache_bucket: int,
) -> tuple[str, ET.Element | None]:
    """Resolve one identity and retain the already downloaded profile XML."""
    exact_terms = " ".join(f"{term}$" for term in str(author or "").split())
    params = urllib.parse.urlencode({
        "q": exact_terms or author,
        "format": "json",
        "h": 30,
        "c": 0,
    })
    request = urllib.request.Request(
        f"https://dblp.org/search/author/api?{params}",
        headers={"User-Agent": "Floris/1.0 (academic discovery)"},
    )
    with urllib.request.urlopen(
        request,
        timeout=18,
        context=_ssl_context(),
    ) as response:
        payload = json.loads(response.read(2 * 1024 * 1024))
    requested_name = _normalized_title(author)
    exact_profiles: list[str] = []
    for hit in _dblp_json_hits(payload):
        info = hit.get("info") if isinstance(hit.get("info"), dict) else {}
        candidate = re.sub(
            r"\s+\d{4}$",
            "",
            str(info.get("author") or "").strip(),
        )
        url = str(info.get("url") or "").strip()
        if _normalized_title(candidate) == requested_name and "/pid/" in url:
            exact_profiles.append(url.split("/pid/", 1)[1].strip("/"))
    for profile_pid in exact_profiles:
        request = urllib.request.Request(
            f"https://dblp.org/pid/{profile_pid}.xml",
            headers={"User-Agent": "Floris/1.0 (academic discovery)"},
        )
        with urllib.request.urlopen(
            request,
            timeout=18,
            context=_ssl_context(),
        ) as response:
            root = ET.fromstring(response.read(4 * 1024 * 1024))
        people = [
            node
            for node in root.findall("./person")
            if node.attrib.get("publtype") != "disambiguation"
        ]
        people.extend(root.findall("./homonyms/h/person"))
        for person in people:
            affiliations = " ".join(
                _xml_text(note)
                for note in person.findall("./note")
                if note.attrib.get("type") == "affiliation"
            )
            if institution and not _institution_matches(affiliations, institution):
                continue
            author_node = person.find("./author")
            pid = str(
                (author_node.attrib.get("pid") if author_node is not None else "")
                or ""
            ).strip()
            if pid:
                if pid == profile_pid:
                    return pid, root
                request = urllib.request.Request(
                    f"https://dblp.org/pid/{pid}.xml",
                    headers={"User-Agent": "Floris/1.0 (academic discovery)"},
                )
                with urllib.request.urlopen(
                    request,
                    timeout=18,
                    context=_ssl_context(),
                ) as response:
                    return pid, ET.fromstring(response.read(8 * 1024 * 1024))
        if not institution and root.attrib.get("pid") and root.find("./person") is not None:
            return str(root.attrib["pid"]), root
    return "", None


def _dblp_profile(
    author: str,
    institution: str,
) -> tuple[str, ET.Element | None]:
    # A warm Edge function can be reused for a long time. Keep the speed
    # benefit without making "recent papers" stale for the process lifetime.
    return _dblp_profile_cached(
        author,
        institution,
        int(time.time() // (15 * 60)),
    )


def _dblp_profile_pid(author: str, institution: str) -> str:
    """Compatibility wrapper used by diagnostics and focused unit tests."""
    return _dblp_profile(author, institution)[0]


def _search_dblp_sync(
    topic: str,
    limit: int,
    author: str,
    institution: str,
    year_from: int,
    year_to: int,
) -> list[dict[str, Any]]:
    if not author:
        return []
    pid, root = _dblp_profile(author, institution)
    if not pid or root is None:
        return []
    topic_tokens = set(_normalized_title(topic).split())
    papers: list[dict[str, Any]] = []
    for wrapper in root.findall("./r"):
        publication = next(iter(wrapper), None)
        if publication is None:
            continue
        title = _xml_text(publication.find("./title"))
        try:
            paper_year = int(_xml_text(publication.find("./year")) or 0)
        except ValueError:
            paper_year = 0
        if year_from and paper_year < year_from:
            continue
        if year_to and paper_year > year_to:
            continue
        if topic_tokens and not topic_tokens.intersection(
            set(_normalized_title(title).split())
        ):
            continue
        authors = [
            re.sub(r"\s+\d{4}$", "", _xml_text(node))
            for node in publication.findall("./author")
            if _xml_text(node)
        ]
        electronic = [
            _xml_text(node)
            for node in publication.findall("./ee")
            if _xml_text(node).startswith("https://")
        ]
        arxiv_url = next(
            (url for url in electronic if "arxiv.org/abs/" in url),
            "",
        )
        if not arxiv_url:
            arxiv_doi = next(
                (
                    url for url in electronic
                    if re.search(r"10\.48550/arxiv\.", url, re.I)
                ),
                "",
            )
            if arxiv_doi:
                arxiv_id_from_doi = re.split(
                    r"10\.48550/arxiv\.",
                    arxiv_doi,
                    flags=re.I,
                )[-1]
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id_from_doi}"
        arxiv_id = (
            arxiv_url.split("/abs/", 1)[1].split("?", 1)[0]
            if arxiv_url else ""
        )
        key = str(publication.attrib.get("key") or "").strip()
        if not arxiv_id:
            corr_match = re.fullmatch(
                r"journals/corr/abs-(\d{4})-(\d{4,5})",
                key,
                flags=re.I,
            )
            if corr_match:
                arxiv_id = f"{corr_match.group(1)}.{corr_match.group(2)}"
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
        source_url = (
            f"https://dblp.org/rec/{key}"
            if key else (electronic[0] if electronic else f"https://dblp.org/pid/{pid}")
        )
        venue = (
            _xml_text(publication.find("./journal"))
            or _xml_text(publication.find("./booktitle"))
            or "DBLP"
        )
        papers.append({
            "title": title,
            "arxiv_id": arxiv_id,
            "authors": ", ".join(authors[:12]),
            "year": paper_year,
            "abstract_zh": "",
            "key_contribution": "",
            "citations": f"DBLP · {venue}",
            "source": "DBLP",
            "source_url": source_url,
            "arxiv_url": arxiv_url,
            "pdf_url": (
                f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                if arxiv_id else ""
            ),
        })
    papers.sort(
        key=lambda item: (
            int(item.get("year") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return papers[:max(1, min(8, limit))]


def _crossref_author_text(item: dict[str, Any]) -> tuple[str, list[str]]:
    author_records = item.get("author") if isinstance(item.get("author"), list) else []
    names: list[str] = []
    affiliations: list[str] = []
    for author in author_records:
        if not isinstance(author, dict):
            continue
        name = " ".join(
            part for part in (
                str(author.get("given") or "").strip(),
                str(author.get("family") or "").strip(),
            ) if part
        )
        if name:
            names.append(name)
        for affiliation in author.get("affiliation") or []:
            if isinstance(affiliation, dict) and str(affiliation.get("name") or "").strip():
                affiliations.append(str(affiliation["name"]).strip())
    return ", ".join(names[:8]), affiliations


def _crossref_pdf(item: dict[str, Any]) -> str:
    links = item.get("link") if isinstance(item.get("link"), list) else []
    for link in links:
        if not isinstance(link, dict):
            continue
        url = str(link.get("URL") or "").strip()
        content_type = str(link.get("content-type") or "").lower()
        if url.startswith("https://") and (
            "pdf" in content_type or url.lower().split("?", 1)[0].endswith(".pdf")
        ):
            return url
    return ""


def _strip_markup(value: Any) -> str:
    return " ".join(
        html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split()
    )


def _search_crossref_sync(
    topic: str,
    limit: int,
    author: str,
    institution: str,
    year_from: int,
    year_to: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "rows": max(6, min(30, limit * 5)),
        "sort": "published",
        "order": "desc",
    }
    if author:
        params["query.author"] = author
    if institution:
        params["query.affiliation"] = institution
    if topic:
        params["query.bibliographic"] = topic
    filters: list[str] = []
    if year_from:
        filters.append(f"from-pub-date:{year_from}-01-01")
    if year_to:
        filters.append(f"until-pub-date:{year_to}-12-31")
    if filters:
        params["filter"] = ",".join(filters)
    request = urllib.request.Request(
        "https://api.crossref.org/v1/works?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "Floris/1.0 (mailto:opensource@floris.local)"},
    )
    with urllib.request.urlopen(
        request,
        timeout=18,
        context=_ssl_context(),
    ) as response:
        payload = json.loads(response.read(3 * 1024 * 1024))
    items = ((payload.get("message") or {}).get("items") or []) if isinstance(payload, dict) else []
    author_tokens = set(_normalized_title(author).split())
    institution_tokens = set(_normalized_title(institution).split())
    output: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get("title") if isinstance(item.get("title"), list) else []
        title = " ".join(str(titles[0] if titles else "").split())
        if not title:
            continue
        authors, affiliations = _crossref_author_text(item)
        candidate_author_tokens = set(_normalized_title(authors).split())
        if author_tokens and not author_tokens.issubset(candidate_author_tokens):
            continue
        affiliation_tokens = set(_normalized_title(" ".join(affiliations)).split())
        if institution_tokens and not institution_tokens.issubset(affiliation_tokens):
            continue
        paper_year = _crossref_date(item)
        if year_from and paper_year and paper_year < year_from:
            continue
        if year_to and paper_year and paper_year > year_to:
            continue
        doi = str(item.get("DOI") or "").strip()
        source_url = str(item.get("URL") or "").strip()
        if not source_url and doi:
            source_url = f"https://doi.org/{doi}"
        pdf_url = _crossref_pdf(item)
        identity = doi or source_url or title
        abstract = _strip_markup(item.get("abstract"))[:700]
        output.append({
            "title": title,
            "arxiv_id": (
                f"webpdf-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
                if pdf_url else ""
            ),
            "authors": authors,
            "year": paper_year,
            "abstract_zh": abstract,
            "key_contribution": abstract[:240],
            "citations": (
                f"Crossref · 被引 {int(item.get('is-referenced-by-count') or 0)} 次"
            ),
            "source": "Crossref",
            "source_url": source_url,
            "arxiv_url": "",
            "pdf_url": pdf_url,
        })
        if len(output) >= max(1, min(8, limit)):
            break
    return output


async def search_arxiv(
    topic: str = "",
    limit: int = 5,
    titles: list[str] | None = None,
    author: str = "",
    year: int = 0,
    institution: str = "",
    year_from: int = 0,
    year_to: int = 0,
    candidate_ids: list[str] | None = None,
    candidate_ids_loader: Callable[[], Awaitable[list[str]]] | None = None,
) -> list[dict]:
    """Search verified academic metadata without trusting model recall directly.

    A caller may provide a lazy model-knowledge candidate loader. It runs in
    parallel with provider lookup; every proposed identifier is accepted only
    after an exact official arXiv API lookup.
    """
    requested_limit = max(1, min(8, int(limit or 5)))
    start_year, end_year = _year_bounds(year, year_from, year_to)
    output: list[dict[str, Any]] = []
    provider_failures = 0

    if titles:
        semaphore = asyncio.Semaphore(3)

        async def lookup(title: str):
            async with semaphore:
                try:
                    candidates = await asyncio.to_thread(
                        _search_arxiv_sync,
                        str(title)[:240],
                        3,
                        True,
                        author,
                        start_year,
                        end_year,
                    )
                except Exception:
                    return None
            return _best_title_match(title, candidates)

        matched = await asyncio.gather(*(lookup(title) for title in titles[:8]))
        output.extend(paper for paper in matched if paper)
    else:
        async def candidate_id_lookup() -> tuple[list[dict[str, Any]], bool]:
            proposed = list(candidate_ids or [])
            if candidate_ids_loader is not None:
                try:
                    proposed.extend(await candidate_ids_loader())
                except Exception:
                    pass
            if not proposed:
                return [], False
            try:
                return await asyncio.to_thread(
                    _lookup_arxiv_ids_sync,
                    proposed,
                    author,
                    start_year,
                    end_year,
                ), False
            except Exception:
                return [], True

        async def arxiv_lookup() -> tuple[list[dict[str, Any]], bool]:
            # An author name alone is not an identity. When an affiliation is
            # supplied, broad arXiv author search can mix homonyms and is
            # therefore intentionally disabled.
            if author and institution:
                return [], False
            try:
                return await asyncio.to_thread(
                    _search_arxiv_sync,
                    topic,
                    requested_limit,
                    False,
                    author,
                    start_year,
                    end_year,
                ), False
            except Exception:
                return [], True

        async def dblp_lookup() -> tuple[list[dict[str, Any]], bool]:
            if not author:
                return [], False
            try:
                return await asyncio.to_thread(
                    _search_dblp_sync,
                    topic,
                    requested_limit,
                    author,
                    institution,
                    start_year,
                    end_year,
                ), False
            except Exception:
                return [], True

        candidate_task = asyncio.create_task(candidate_id_lookup())
        dblp_task = asyncio.create_task(dblp_lookup())
        arxiv_task = asyncio.create_task(arxiv_lookup())
        candidate_result, dblp_result, arxiv_result = await asyncio.gather(
            candidate_task,
            dblp_task,
            arxiv_task,
        )
        candidate_rows, candidate_failed = candidate_result
        dblp_rows, dblp_failed = dblp_result
        broad_arxiv_rows, arxiv_failed = arxiv_result
        provider_failures += sum(
            int(value)
            for value in (candidate_failed, dblp_failed, arxiv_failed)
        )

        # DBLP's affiliation-specific profile is authoritative identity
        # evidence. When available, reject a recalled candidate that is not in
        # that profile even if the arXiv identifier itself exists.
        if institution and dblp_rows:
            dblp_titles = {
                _normalized_title(paper.get("title") or "")
                for paper in dblp_rows
            }
            dblp_ids = {
                re.sub(
                    r"v\d+$",
                    "",
                    str(paper.get("arxiv_id") or ""),
                    flags=re.I,
                )
                for paper in dblp_rows
                if paper.get("arxiv_id")
            }
            candidate_rows = [
                paper for paper in candidate_rows
                if (
                    _normalized_title(paper.get("title") or "") in dblp_titles
                    or re.sub(
                        r"v\d+$",
                        "",
                        str(paper.get("arxiv_id") or ""),
                        flags=re.I,
                    ) in dblp_ids
                )
            ]
        output.extend(candidate_rows)
        output.extend(dblp_rows)
        output.extend(broad_arxiv_rows)

    if len(output) < requested_limit and (author or institution):
        try:
            crossref = await asyncio.to_thread(
                _search_crossref_sync,
                topic,
                requested_limit,
                author,
                institution,
                start_year,
                end_year,
            )
            output.extend(crossref)
        except Exception:
            provider_failures += 1

    deduped: list[dict[str, Any]] = []
    seen_arxiv_ids: set[str] = set()
    seen_titles: set[str] = set()
    for paper in output:
        arxiv_identity = re.sub(
            r"v\d+$",
            "",
            str(paper.get("arxiv_id") or ""),
            flags=re.I,
        )
        title_identity = _normalized_title(paper.get("title") or "")
        if (
            not arxiv_identity
            and not title_identity
        ) or (
            arxiv_identity
            and arxiv_identity in seen_arxiv_ids
        ) or (
            title_identity
            and title_identity in seen_titles
        ):
            continue
        if arxiv_identity:
            seen_arxiv_ids.add(arxiv_identity)
        if title_identity:
            seen_titles.add(title_identity)
        deduped.append(paper)
        if len(deduped) >= requested_limit:
            break
    if provider_failures >= 3 and not deduped:
        raise RuntimeError("arXiv、DBLP 与 Crossref 本轮均未响应")
    return deduped
