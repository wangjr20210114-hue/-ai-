"""Provider adapter for the dependency-free academic discovery cascade.

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

from ..._application.i18n import text


def _ssl_context() -> ssl.SSLContext:
    """Use certifi in managed Python images while retaining the system fallback."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


_TOPIC_STOPWORDS = frozenset({
    "a", "an", "and", "article", "articles", "for", "in", "latest",
    "new", "of", "on", "paper", "papers", "recent", "research", "study",
    "the", "to", "using", "with",
})


def _topic_terms(topic: str) -> list[str]:
    """Return portable lexical constraints without assuming a paper domain.

    Non-Latin topics are left to the verified candidate/provider pipeline: an
    English metadata feed cannot safely prove that a Chinese query is
    irrelevant. Latin words and acronyms, however, can be checked
    deterministically and prevent a broad provider query from returning recent
    but unrelated work.
    """
    return list(dict.fromkeys(
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]*", str(topic or ""))
        if token.lower() not in _TOPIC_STOPWORDS
    ))


def _lexical_term_matches(term: str, words: list[str], text: str) -> bool:
    normalized = term.replace("-", "").lower()
    if not normalized:
        return False
    if normalized in words:
        return True
    # Match ordinary inflections without pulling in a language-specific
    # stemmer. Five characters is conservative enough for academic terms such
    # as evaluation/evaluated while avoiding short-token collisions.
    if len(normalized) >= 6 and any(
        len(word) >= 6 and word[:5] == normalized[:5]
        for word in words
    ):
        return True
    # A short query token may be an established acronym. Accept either its
    # literal occurrence or the initials of adjacent words in verified
    # metadata (for example, RAG -> retrieval augmented generation).
    if 2 <= len(normalized) <= 6:
        if re.search(rf"\b{re.escape(normalized)}\b", text):
            return True
        width = len(normalized)
        return any(
            "".join(word[0] for word in words[index:index + width]) == normalized
            for index in range(max(0, len(words) - width + 1))
        )
    return False


def _paper_matches_topic(paper: dict[str, Any], topic: str) -> bool:
    terms = _topic_terms(topic)
    if not terms:
        return True
    haystack = _normalized_title(" ".join((
        str(paper.get("title") or ""),
        str(paper.get("abstract_zh") or ""),
        str(paper.get("key_contribution") or ""),
    )))
    words = haystack.split()
    matched = sum(_lexical_term_matches(term, words, haystack) for term in terms)
    # Two-term requests usually encode the subject and the user's angle (for
    # example, "RAG evaluation"), so both must be present. Longer natural
    # phrases tolerate one modifier while still requiring broad coverage.
    required = len(terms) if len(terms) <= 2 else max(2, (len(terms) + 1) // 2)
    return matched >= required


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
    hits: list[dict[str, Any]] = []
    # DBLP's exact-term syntax occasionally returns a transient 5xx even while
    # the normal author endpoint is healthy. Retry with the ordinary author
    # query only when needed; affiliation verification below remains strict.
    normal_query = str(author or "").strip()
    # DBLP's exact author endpoint is occasionally slow or returns a transient
    # 5xx. Retry that high-value query once before falling back to the broad
    # search. A larger candidate window is important for common names because
    # affiliation-qualified homonyms can otherwise be truncated.
    queries = [exact_terms, exact_terms, normal_query]
    for query in queries:
        if not query:
            continue
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "h": 100,
            "c": 0,
        })
        request = urllib.request.Request(
            f"https://dblp.org/search/author/api?{params}",
            headers={"User-Agent": "Floris/1.0 (academic discovery)"},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=18,
                context=_ssl_context(),
            ) as response:
                payload = json.loads(response.read(2 * 1024 * 1024))
        except Exception:
            continue
        hits.extend(_dblp_json_hits(payload))
        if hits:
            break
    requested_name = _normalized_title(author)
    exact_profiles: list[str] = []
    for hit in hits:
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
        try:
            with urllib.request.urlopen(
                request,
                timeout=18,
                context=_ssl_context(),
            ) as response:
                root = ET.fromstring(response.read(4 * 1024 * 1024))
        except Exception:
            continue
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
    clean_author = " ".join(
        str(author or "").replace(",", " ").replace(";", " ").split()
    )
    signatures = [clean_author]
    tokens = clean_author.split()
    if len(tokens) == 2:
        signatures.append(" ".join(reversed(tokens)))
    cache_bucket = int(time.time() // (15 * 60))
    for signature in dict.fromkeys(signatures):
        if not signature:
            continue
        pid, root = _dblp_profile_cached(
            signature,
            institution,
            cache_bucket,
        )
        if pid and root is not None:
            return pid, root
    return "", None


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


def _openalex_institution_names(author: dict[str, Any]) -> str:
    names: list[str] = []
    for item in author.get("last_known_institutions") or []:
        if isinstance(item, dict) and str(item.get("display_name") or "").strip():
            names.append(str(item["display_name"]).strip())
    for affiliation in author.get("affiliations") or []:
        if not isinstance(affiliation, dict):
            continue
        institution = affiliation.get("institution")
        if (
            isinstance(institution, dict)
            and str(institution.get("display_name") or "").strip()
        ):
            names.append(str(institution["display_name"]).strip())
    return " ".join(dict.fromkeys(names))


def _search_openalex_sync(
    topic: str,
    limit: int,
    author: str,
    institution: str,
    year_from: int,
    year_to: int,
) -> list[dict[str, Any]]:
    """Resolve an affiliation-qualified author and fetch recent works.

    OpenAlex is used as an independent structured index, not as a source of
    model-generated facts. The affiliation is verified first on the author
    entity and again on each selected authorship.
    """
    if not author:
        return []
    author_params = urllib.parse.urlencode({
        "search": author,
        "per-page": 15,
        "select": (
            "id,display_name,display_name_alternatives,last_known_institutions,"
            "affiliations,works_count,cited_by_count"
        ),
    })
    author_request = urllib.request.Request(
        f"https://api.openalex.org/authors?{author_params}",
        headers={"User-Agent": "Floris/1.0 (mailto:opensource@floris.local)"},
    )
    with urllib.request.urlopen(
        author_request,
        timeout=12,
        context=_ssl_context(),
    ) as response:
        author_payload = json.loads(response.read(3 * 1024 * 1024))
    requested_name_tokens = set(_normalized_title(author).split())
    author_candidates: list[dict[str, Any]] = []
    for candidate in (
        author_payload.get("results")
        if isinstance(author_payload, dict)
        and isinstance(author_payload.get("results"), list)
        else []
    ):
        if not isinstance(candidate, dict):
            continue
        candidate_names = [
            str(candidate.get("display_name") or ""),
            *[
                str(value)
                for value in (candidate.get("display_name_alternatives") or [])
                if str(value).strip()
            ],
        ]
        if requested_name_tokens and not any(
            set(_normalized_title(name).split()) == requested_name_tokens
            for name in candidate_names
        ):
            continue
        if institution and not _institution_matches(
            _openalex_institution_names(candidate),
            institution,
        ):
            continue
        if str(candidate.get("id") or "").strip():
            author_candidates.append(candidate)
    if not author_candidates:
        return []
    author_candidates.sort(
        key=lambda item: (
            int(item.get("works_count") or 0),
            int(item.get("cited_by_count") or 0),
        ),
        reverse=True,
    )
    author_id = str(author_candidates[0]["id"]).rsplit("/", 1)[-1]
    filters = [f"author.id:{author_id}"]
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")
    work_params: dict[str, Any] = {
        "filter": ",".join(filters),
        "sort": "publication_date:desc",
        "per-page": max(8, min(30, int(limit or 5) * 4)),
        "select": (
            "id,doi,title,publication_year,ids,authorships,primary_location,"
            "best_oa_location,cited_by_count"
        ),
    }
    if topic:
        work_params["search"] = topic
    work_request = urllib.request.Request(
        "https://api.openalex.org/works?"
        + urllib.parse.urlencode(work_params),
        headers={"User-Agent": "Floris/1.0 (mailto:opensource@floris.local)"},
    )
    with urllib.request.urlopen(
        work_request,
        timeout=12,
        context=_ssl_context(),
    ) as response:
        work_payload = json.loads(response.read(6 * 1024 * 1024))
    papers: list[dict[str, Any]] = []
    for work in (
        work_payload.get("results")
        if isinstance(work_payload, dict)
        and isinstance(work_payload.get("results"), list)
        else []
    ):
        if not isinstance(work, dict):
            continue
        title = " ".join(
            str(work.get("title") or work.get("display_name") or "").split()
        )
        if not title:
            continue
        matched_authorship = None
        author_names: list[str] = []
        for authorship in work.get("authorships") or []:
            if not isinstance(authorship, dict):
                continue
            work_author = authorship.get("author")
            if not isinstance(work_author, dict):
                continue
            work_author_id = str(work_author.get("id") or "").rsplit("/", 1)[-1]
            work_author_name = str(work_author.get("display_name") or "").strip()
            if work_author_name:
                author_names.append(work_author_name)
            if work_author_id == author_id:
                matched_authorship = authorship
        if matched_authorship is None:
            continue
        if institution:
            work_institutions = " ".join(
                str(item.get("display_name") or "")
                for item in (matched_authorship.get("institutions") or [])
                if isinstance(item, dict)
            )
            if not _institution_matches(work_institutions, institution):
                continue
        ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
        arxiv_url = str(ids.get("arxiv") or "").strip()
        doi_url = str(work.get("doi") or ids.get("doi") or "").strip()
        if not arxiv_url and re.search(r"10\.48550/arxiv\.", doi_url, re.I):
            arxiv_id_from_doi = re.split(
                r"10\.48550/arxiv\.",
                doi_url,
                flags=re.I,
            )[-1]
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id_from_doi}"
        arxiv_id = (
            arxiv_url.split("/abs/", 1)[1].split("?", 1)[0]
            if "/abs/" in arxiv_url
            else ""
        )
        primary = (
            work.get("primary_location")
            if isinstance(work.get("primary_location"), dict)
            else {}
        )
        best_oa = (
            work.get("best_oa_location")
            if isinstance(work.get("best_oa_location"), dict)
            else {}
        )
        pdf_url = str(
            best_oa.get("pdf_url") or primary.get("pdf_url") or ""
        ).strip()
        source_url = (
            arxiv_url
            or doi_url
            or str(primary.get("landing_page_url") or "").strip()
            or str(work.get("id") or "").strip()
        )
        papers.append({
            "title": title,
            "arxiv_id": arxiv_id,
            "authors": ", ".join(author_names[:12]),
            "year": int(work.get("publication_year") or 0),
            "abstract_zh": "",
            "key_contribution": "",
            "citations": text(
                "paper.cited_count", source="OpenAlex",
                count=int(work.get("cited_by_count") or 0),
            ),
            "source": "OpenAlex",
            "source_url": source_url,
            "arxiv_url": arxiv_url,
            "pdf_url": pdf_url,
        })
        if len(papers) >= max(1, min(8, int(limit or 5))):
            break
    return papers


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
            "citations": text(
                "paper.cited_count", source="Crossref",
                count=int(item.get("is-referenced-by-count") or 0),
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
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        _lookup_arxiv_ids_sync,
                        proposed,
                        author,
                        start_year,
                        end_year,
                    ),
                    timeout=22.0,
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
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        _search_dblp_sync,
                        topic,
                        requested_limit,
                        author,
                        institution,
                        start_year,
                        end_year,
                    ),
                    timeout=24.0,
                ), False
            except Exception:
                return [], True

        async def openalex_lookup() -> tuple[list[dict[str, Any]], bool]:
            if not author:
                return [], False
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        _search_openalex_sync,
                        topic,
                        requested_limit,
                        author,
                        institution,
                        start_year,
                        end_year,
                    ),
                    timeout=38.0,
                ), False
            except Exception:
                return [], True

        # The model's exact arXiv identifiers are the primary discovery path.
        # Verify them against the official API first; only pay for broad indexes
        # when the verified model candidates cannot satisfy the requested count.
        candidate_rows, candidate_failed = await candidate_id_lookup()
        dblp_rows: list[dict[str, Any]] = []
        broad_arxiv_rows: list[dict[str, Any]] = []
        openalex_rows: list[dict[str, Any]] = []
        dblp_failed = arxiv_failed = openalex_failed = False
        if len(candidate_rows) < requested_limit:
            (
                dblp_result,
                arxiv_result,
                openalex_result,
            ) = await asyncio.gather(
                dblp_lookup(),
                arxiv_lookup(),
                openalex_lookup(),
            )
            dblp_rows, dblp_failed = dblp_result
            broad_arxiv_rows, arxiv_failed = arxiv_result
            openalex_rows, openalex_failed = openalex_result
        provider_failures += sum(
            int(value)
            for value in (
                candidate_failed,
                dblp_failed,
                arxiv_failed,
                openalex_failed,
            )
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
        output.extend(openalex_rows)
        output.extend(broad_arxiv_rows)

    if len(output) < requested_limit and (author or institution):
        try:
            crossref = await asyncio.wait_for(
                asyncio.to_thread(
                    _search_crossref_sync,
                    topic,
                    requested_limit,
                    author,
                    institution,
                    start_year,
                    end_year,
                ),
                timeout=10.0,
            )
            output.extend(crossref)
        except Exception:
            provider_failures += 1

    deduped: list[dict[str, Any]] = []
    seen_arxiv_ids: set[str] = set()
    seen_titles: set[str] = set()
    for paper in output:
        if topic and not _paper_matches_topic(paper, topic):
            continue
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
        raise RuntimeError(text("paper.providers_unavailable"))
    return deduped
