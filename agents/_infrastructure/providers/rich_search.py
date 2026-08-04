"""Makers provider adapter for the rich-search pipeline; not an Agent route.

Search pages provide image candidates and surrounding text. HY-Vision then reviews
the real pixels against both the user question and page context.  Only reviewed
images are exposed to the answer model as ordinary Markdown resources.
"""

from __future__ import annotations

import asyncio
import http.client
import io
import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from html import unescape
from typing import Any, Awaitable, Callable

from .web_media import collect_page_media
from .vision import vision_completion, vision_providers
from ..._application.i18n import text
from ..._application.search.evidence_presenter import evidence_for_model
from ..._domain.search.source_policy import (
    RECENT_SOURCE_WINDOW_DAYS,
    filter_preferred_recent_sources,
    filter_sources_for_target_date,
    query_match_terms,
    rank_source_results,
    source_domain,
)


def _vision_review_timeout(env: dict[str, Any]) -> float:
    try:
        configured = float(env.get("RICH_SEARCH_VISION_TIMEOUT_SECONDS") or 7)
    except (TypeError, ValueError):
        configured = 7.0
    return max(2.0, min(7.0, configured))


def _embedded_image_url(value: Any) -> str:
    """Read a provider-supplied article image embedded in an HTML passage."""
    text = unescape(str(value or ""))
    match = re.search(r"<img\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _provider_page_images(page: dict[str, Any], snippet: str) -> list[dict[str, str]]:
    """Normalize the native SearchPro ``images``/``pics`` response contract."""
    raw_items: list[Any] = []
    for field in ("pics", "images"):
        value = page.get(field)
        if isinstance(value, list):
            raw_items.extend(value)
        elif value:
            raw_items.append(value)
    for field in ("image", "image_url", "thumbnail"):
        if page.get(field):
            raw_items.append(page[field])
    embedded = _embedded_image_url(snippet)
    if embedded:
        raw_items.append({"url": embedded, "caption": ""})

    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_items:
        if isinstance(raw, dict):
            url = str(
                raw.get("origin_url")
                or raw.get("url")
                or raw.get("image_url")
                or raw.get("src")
                or ""
            ).strip()
            caption = str(raw.get("caption") or raw.get("alt") or raw.get("title") or "").strip()
        else:
            url = str(raw or "").strip()
            caption = ""
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        output.append({"url": url, "caption": caption[:240]})
        if len(output) >= 10:
            break
    return output


def _provider_image_candidates(
    results: list[dict[str, Any]], response_language: object = "zh-CN",
) -> list[dict[str, str]]:
    """Return only SearchPro-supplied article images, never page-scraped media.

    These are the conservative fallback when every configured vision provider is
    unavailable or times out. They are not used when vision explicitly rejects
    an image as irrelevant.
    """
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        provider_images = result.get("provider_images")
        if not isinstance(provider_images, list):
            provider_images = [{"url": result.get("image") or "", "caption": ""}]
        for item in provider_images:
            if not isinstance(item, dict):
                continue
            image = unescape(str(item.get("url") or "").strip())
            caption = str(item.get("caption") or "").strip()
            if image.startswith("http://"):
                image = "https://" + image[len("http://"):]
            path = urllib.parse.urlparse(image).path.lower()
            if (
                not image.startswith("https://")
                or path.endswith((".svg", ".gif", ".ico"))
                or image in seen
            ):
                continue
            seen.add(image)
            candidates.append({
                "url": image,
                "alt": caption,
                "context": caption or text("search.article_image", response_language),
                "source_url": result["url"],
                "source_title": result["title"],
            })
    return candidates


def _json_request(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """POST JSON without urllib's process-global proxy discovery overhead.

    Tencent's WSA API guide uses ``HTTPSConnection`` for the API-key route.
    In the Makers Python runtime, ``urllib.request.urlopen`` can spend longer
    than the complete ten-second provider budget before SearchPro responds,
    while the direct connection completes in well under a second.  Keep this
    helper generic because the vision adapter shares the same JSON transport.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("JSON provider URL must be absolute HTTP(S)")
    connection_type = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(
        parsed.hostname,
        port=parsed.port,
        timeout=timeout,
    )
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    try:
        connection.request(
            "POST",
            target,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        response = connection.getresponse()
        raw = response.read(8 * 1024 * 1024)
        if not 200 <= int(response.status) < 300:
            raise urllib.error.HTTPError(
                url,
                int(response.status),
                str(response.reason or "provider request failed"),
                response.headers,
                io.BytesIO(raw),
            )
        return json.loads(raw.decode("utf-8"))
    finally:
        connection.close()


def _retryable_searchpro_error(error: Exception) -> bool:
    """Return whether a read-only SearchPro request is safe to retry once."""
    if isinstance(error, urllib.error.HTTPError):
        status = int(getattr(error, "code", 0) or 0)
        return status in {408, 429} or status >= 500
    return isinstance(
        error,
        (
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
            OSError,
        ),
    )


async def _searchpro_json_request(
    url: str,
    payload: dict,
    headers: dict,
    timeout: int,
    request_id: str = "",
) -> tuple[dict, int]:
    """Use the shared SearchPro adapter with one bounded transport recovery."""
    deadline = asyncio.get_running_loop().time() + max(1.0, float(timeout))
    for attempt in range(1, 3):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        try:
            data = await _searchpro_request_json(
                url,
                payload,
                headers,
                max(1, min(timeout, int(remaining))),
            )
            return data, attempt
        except Exception as error:
            if attempt >= 2 or not _retryable_searchpro_error(error):
                raise
            logging.warning(
                "SearchPro transport retry request_id=%s attempt=%s error_type=%s",
                request_id,
                attempt,
                type(error).__name__,
            )
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError() from error
            await asyncio.sleep(min(0.2, remaining))
    raise RuntimeError("SearchPro request did not complete")


async def _searchpro_request_json(
    url: str,
    payload: dict,
    headers: dict,
    timeout: int,
) -> dict:
    """Call SearchPro through its proven direct Tencent transport.

    The generic shared HTTP client remains useful for public page extraction,
    but SearchPro's Maker runtime path is not equivalent: the provider's own
    documented direct HTTPS request succeeds where the shared pool can spend
    the complete budget establishing a connection.  Keep the blocking socket
    off the event loop while retaining the cancellable outer deadline.
    """
    return await asyncio.to_thread(
        _json_request,
        url,
        payload,
        headers,
        timeout,
    )


def _parse_pages(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    response = data.get("Response") if isinstance(data.get("Response"), dict) else data
    pages = response.get("Pages") or response.get("pages") or []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in pages:
        try:
            page = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            continue
        if not isinstance(page, dict):
            continue
        url = str(page.get("url") or page.get("link") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        source_kind = "video" if re.search(
            r"(?:^|\.)(?:bilibili\.com|youtube\.com|youtu\.be|v\.qq\.com|youku\.com|douyin\.com|ixigua\.com)$",
            host,
        ) else "wsa"
        snippet = str(page.get("passage") or page.get("snippet") or page.get("description") or "")
        provider_images = _provider_page_images(page, snippet)
        image = provider_images[0]["url"] if provider_images else ""
        raw_score = page.get("score")
        relevance_score = (
            max(0.0, min(1.0, float(raw_score)))
            if isinstance(raw_score, (int, float))
            and not isinstance(raw_score, bool)
            and math.isfinite(float(raw_score))
            else 0.0
        )
        results.append({
            "source": source_kind, "title": str(page.get("title") or page.get("name") or url)[:200],
            "snippet": snippet[:500],
            "url": url,
            "image": image,
            "provider_images": provider_images,
            "date": str(page.get("date") or page.get("publish_time") or "")[:40],
            "publisher": str(page.get("site") or page.get("site_name") or "")[:120],
            "relevance_score": relevance_score,
        })
        if len(results) >= limit:
            break
    return results


def _bounded_provider_query(
    query: str, qualifiers: list[str], limit: int = 500,
) -> str:
    """Compose one bounded SearchPro query without dropping whole constraints.

    The factual user query receives three times the weight of each optional
    qualifier. Unused space is redistributed deterministically, so short date
    or quality constraints leave more room for the original query.
    """
    sections = [
        value.strip()
        for value in [str(query or ""), *qualifiers]
        if value and value.strip()
    ]
    if not sections or limit <= 0:
        return ""
    joined = "\n".join(sections)
    if len(joined) <= limit:
        return joined
    available = max(0, limit - (len(sections) - 1))
    weights = [3, *([1] * (len(sections) - 1))]
    total_weight = sum(weights)
    allocations = [available * weight // total_weight for weight in weights]
    for index in range(available - sum(allocations)):
        allocations[index % len(allocations)] += 1
    unused = available - sum(
        min(len(value), allocations[index])
        for index, value in enumerate(sections)
    )
    while unused:
        expandable = [
            index for index, value in enumerate(sections)
            if allocations[index] < len(value)
        ]
        if not expandable:
            break
        for index in expandable:
            if not unused:
                break
            allocations[index] += 1
            unused -= 1
    return "\n".join(
        value[:allocations[index]]
        for index, value in enumerate(sections)
    )[:limit]


def _provider_time_window(
    target_date: str, *, strict_date: bool, prefer_recent: bool,
) -> dict[str, int]:
    """Translate semantic recency into SearchPro's native time filter.

    The window is intentionally generic and timezone-stable. SearchPro still
    receives one request; local date verification remains the truth boundary
    for incomplete provider metadata.
    """
    if not target_date or not (strict_date or prefer_recent):
        return {}
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return {}
    start = (
        target
        if strict_date
        else target - timedelta(days=RECENT_SOURCE_WINDOW_DAYS)
    )
    beijing = timezone(timedelta(hours=8))
    return {
        "FromTime": int(datetime.combine(start, datetime_time.min, beijing).timestamp()),
        "ToTime": int(datetime.combine(
            target + timedelta(days=1), datetime_time.min, beijing,
        ).timestamp()) - 1,
    }


async def _extract_candidates(
    results: list[dict[str, Any]],
    page_limit: int = 6,
    parallel: bool = True,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    candidates = _provider_image_candidates(results)

    async def page(result: dict[str, Any]) -> list[dict[str, str]]:
        try:
            items = await collect_page_media(result["url"], 10)
        except Exception:
            return []
        normalized = []
        for item in items:
            image_url = str(item.get("url") or "")
            if image_url.startswith("http://"):
                image_url = "https://" + image_url[len("http://"):]
            if image_url.startswith("https://"):
                normalized.append({**item, "url": image_url, "source_url": result["url"], "source_title": result["title"]})
        return normalized

    selected_results = results[:max(1, min(6, page_limit))]
    if not selected_results:
        return candidates
    if parallel:
        # Keep every source page that completes inside the shared media budget.
        # Waiting on one combined gather used to discard fast pages whenever
        # any other publisher crossed the deadline.
        tasks = [asyncio.create_task(page(result)) for result in selected_results]
        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=(
                    max(0.1, float(timeout_seconds))
                    if timeout_seconds is not None
                    else None
                ),
            )
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        batches = []
        for task in tasks:
            if task not in done:
                continue
            try:
                batches.append(task.result())
            except Exception:
                batches.append([])
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    else:
        batches = []
        deadline = (
            asyncio.get_running_loop().time() + max(0.1, float(timeout_seconds))
            if timeout_seconds is not None
            else None
        )
        for result in selected_results:
            if deadline is None:
                batches.append(await page(result))
                continue
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                batches.append(await asyncio.wait_for(page(result), remaining))
            except asyncio.TimeoutError:
                break
    for batch in batches:
        candidates.extend(batch)
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate["url"] in seen:
            continue
        seen.add(candidate["url"])
        output.append(candidate)
        if len(output) >= 30:
            break
    return output


def _candidate_visual_priority(
    candidate: dict[str, str], query: str = "",
) -> tuple[int, int, int]:
    """Rank editorial-looking candidates without increasing the review budget.

    Search pages often expose account avatars and ultra-wide navigation banners
    before the first useful article image. URL dimensions are only a visual
    quality signal; semantic relevance and safety remain the vision model's job.
    """
    url = str(candidate.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    lowered = f"{parsed.netloc}{parsed.path}".lower()
    url_params = urllib.parse.parse_qs(parsed.query)

    def number(name: str) -> int:
        try:
            return max(0, int((url_params.get(name) or [0])[0]))
        except (TypeError, ValueError):
            return 0

    width = number("w") or number("width")
    height = number("h") or number("height")
    encoded_size = number("size")
    score = 0
    if any(marker in lowered for marker in ("avatar", "profile", "logo", "icon")):
        score -= 20
    if width and height:
        ratio = max(width, height) / max(1, min(width, height))
        shortest = min(width, height)
        if shortest >= 300 and ratio <= 2.4:
            score += 8
        elif shortest < 160 or ratio >= 3.0:
            score -= 8
    if encoded_size >= 100:
        score += 4
    elif encoded_size and encoded_size < 40:
        score -= 2
    context_length = len(str(
        candidate.get("context")
        or candidate.get("alt")
        or candidate.get("source_title")
        or ""
    ).strip())
    if context_length >= 80:
        score += 1
    context = str(
        candidate.get("context")
        or candidate.get("alt")
        or candidate.get("source_title")
        or ""
    ).casefold()
    normalized_query = str(query or "").casefold()
    lexical_units = set(re.findall(
        r"[a-z0-9][a-z0-9.+_-]{1,}",
        normalized_query,
    ))
    for chinese_run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized_query):
        lexical_units.update(
            chinese_run[index:index + 2]
            for index in range(len(chinese_run) - 1)
        )
    overlap = sum(1 for unit in lexical_units if unit in context)
    score += min(12, overlap * 3)
    return score, min(encoded_size, 10_000), min(width * height, 20_000_000)


def _candidate_prefilter_reason(candidate: dict[str, str]) -> str:
    """Reject URL shapes that are reliably non-editorial before paid review."""
    url = str(candidate.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    lowered = f"{parsed.netloc}{parsed.path}".lower()
    if (
        parsed.netloc.lower() == "qb-profile.image.myqcloud.com"
        or any(marker in lowered for marker in ("avatar", "profile", "logo", "icon"))
    ):
        return "profile_or_brand_asset"
    if re.search(
        r"(?:^|[/_.-])(?:ads?|advert|promo|promotion|coupon)(?:[/_.-]|$)",
        lowered,
    ):
        return "advertising_url"
    params = urllib.parse.parse_qs(parsed.query)

    def number(name: str) -> int:
        try:
            return max(0, int((params.get(name) or [0])[0]))
        except (TypeError, ValueError):
            return 0

    width = number("w") or number("width")
    height = number("h") or number("height")
    if width and height:
        shortest = min(width, height)
        ratio = max(width, height) / max(1, shortest)
        if shortest < 120:
            return "tiny_asset"
        if ratio >= 3.2 and shortest <= 500:
            return "banner_geometry"
    return ""


def _source_bound_fallback_candidates(
    candidates: list[dict[str, str]],
    query: str,
    source_urls: set[str],
    output_limit: int,
    *,
    require_semantic_overlap: bool = True,
) -> list[dict[str, str]]:
    """Select traceable page media only when vision made no decision.

    This fallback is capability-level rather than topic-level: candidates must
    belong to an exact retained source, pass the shared asset prefilter, and
    overlap the planner's visual intent. One image per source is preferred so
    a single page cannot monopolize the answer.
    """
    limit = max(0, min(8, int(output_limit)))
    if limit == 0:
        return []
    terms = query_match_terms(query)
    ranked: list[tuple[int, tuple[int, int, int], int, dict[str, str]]] = []
    seen_urls: set[str] = set()
    for index, candidate in enumerate(candidates[:30]):
        image_url = str(candidate.get("url") or "").strip()
        source_url = str(candidate.get("source_url") or "").strip()
        if (
            not image_url
            or image_url in seen_urls
            or source_url not in source_urls
            or _candidate_prefilter_reason(candidate)
        ):
            continue
        context = " ".join(str(candidate.get(field) or "") for field in (
            "source_title", "context", "alt",
        )).casefold()
        overlap = sum(1 for term in terms if term in context)
        if require_semantic_overlap and terms and overlap == 0:
            continue
        seen_urls.add(image_url)
        ranked.append((
            overlap,
            _candidate_visual_priority(candidate, query),
            -index,
            candidate,
        ))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    preferred: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for _, _, _, candidate in ranked:
        source_url = str(candidate.get("source_url") or "")
        if source_url not in seen_sources:
            preferred.append(candidate)
            seen_sources.add(source_url)
        else:
            remaining.append(candidate)
    return (preferred + remaining)[:limit]


def _vision_endpoint(env: dict[str, Any]) -> str:
    base = str(
        env.get("HUNYUAN_VISION_BASE_URL")
        or env.get("HUNYUAN_IMAGE_BASE_URL")
        or "https://tokenhub.tencentmaas.com"
    ).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _review_image(
    env: dict[str, Any], candidate: dict[str, str], query: str,
) -> tuple[str, str]:
    # Token Plan keys only authorize text models such as Hy3. Prefer the
    # dedicated TokenHub key so image_url is processed by a real vision model.
    api_key = str(
        env.get("HUNYUAN_VISION_API_KEY")
        or env.get("HUNYUAN_IMAGE_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return "", "missing_api_key"
    model = str(env.get("HUNYUAN_VISION_MODEL") or "hy-vision-2.0-instruct")
    prompt = text(
        "model.search.vision_review", "zh-CN",
        query=query[:120],
        context=(candidate.get("context") or candidate.get("alt") or candidate.get("source_title") or "")[:300],
    )
    payload = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": candidate["url"]}},
    ]}], "max_tokens": 240, "temperature": 0.2, "stream": False}
    data = None
    for attempt in range(2):
        try:
            data = _json_request(
                _vision_endpoint(env), payload,
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, 30,
            )
            break
        except urllib.error.HTTPError as error:
            if attempt == 0 and (error.code == 429 or error.code >= 500):
                time.sleep(1.2)
                continue
            return "", f"http_{error.code}"
        except Exception as error:
            return "", f"transport_{type(error).__name__}"
    try:
        if data is None:
            return "", "empty_response"
        raw = str(data["choices"][0]["message"]["content"]).strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            raw = match.group(0)
        reviewed = json.loads(raw)
        if (
            reviewed.get("relevant") is True
            and reviewed.get("promotional") is not True
        ):
            description = str(reviewed.get("description") or "").strip()[:240]
            return (description, "approved") if description else ("", "missing_description")
        return "", "irrelevant"
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return "", "invalid_response"


async def _vision_filter(
    env: dict[str, Any], query: str, candidates: list[dict[str, str]], output_limit: int = 4,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    output_limit = max(0, min(8, int(output_limit)))
    if output_limit == 0:
        return [], {"candidates": len(candidates), "reviewed": 0, "disabled": 1}
    if not vision_providers(env):
        return [], {"missing_api_key": 1, "candidates": len(candidates), "reviewed": 0}

    # Remove deterministic non-editorial URL/geometry shapes before spending
    # any vision budget. Keep reason counts in diagnostics so these rules remain
    # observable and can be relaxed if a provider changes its asset format.
    prefilter_diagnostics: Counter[str] = Counter()
    eligible_candidates: list[dict[str, str]] = []
    for candidate in candidates[:30]:
        reason = _candidate_prefilter_reason(candidate)
        if reason:
            prefilter_diagnostics[f"prefilter_{reason}"] += 1
        else:
            eligible_candidates.append(candidate)

    # Prefer one candidate per source before filling remaining slots. HY-Vision
    # supports exactly one image per request, so review a small bounded set in
    # parallel instead of sending an invalid multi-image Chat Completions body.
    selected: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    ranked_candidates = sorted(
        eligible_candidates,
        key=lambda candidate: _candidate_visual_priority(candidate, query),
        reverse=True,
    )
    for candidate in ranked_candidates:
        source = str(candidate.get("source_url") or "")
        if source and source not in seen_sources:
            seen_sources.add(source)
            selected.append(candidate)
        else:
            remaining.append(candidate)
    selected = (selected + remaining)[:output_limit]
    if not selected:
        return [], {
            "candidates": len(candidates),
            "eligible_candidates": 0,
            "reviewed": 0,
            **dict(prefilter_diagnostics),
        }

    # Image review is a shallow relevance/safety gate, not an open-ended
    # visual-analysis task. Keep one shared deadline for the whole provider
    # chain and never allow an environment override to exceed seven seconds.
    timeout = _vision_review_timeout(env)

    async def review(candidate: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        context = str(candidate.get("context") or candidate.get("alt") or candidate.get("source_title") or "")[:240]
        prompt = text(
            "model.search.vision_quick_review", "zh-CN",
            query=query[:160], context=context,
        )
        try:
            raw, provider = await vision_completion(
                env,
                [
                    {"type": "image_url", "image_url": {"url": candidate["url"]}},
                    {"type": "text", "text": prompt},
                ],
                max_tokens=160,
                timeout=timeout,
            )
            if not raw:
                return None, provider
            clean = raw.strip().strip("`").strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            match = re.search(r"\{[\s\S]*\}", clean)
            item = json.loads(match.group(0) if match else clean)
            return item if isinstance(item, dict) else None, provider
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return None, {"error": f"review_{type(exc).__name__}"}

    reviews = await asyncio.gather(*(review(candidate) for candidate in selected))
    output: list[dict[str, str]] = []
    diagnostics: Counter[str] = Counter()
    diagnostics.update(prefilter_diagnostics)
    for candidate, (item, provider_diagnostics) in zip(selected, reviews):
        provider_name = str(provider_diagnostics.get("provider") or "")
        if provider_name:
            diagnostics[f"provider_{provider_name}"] += 1
        diagnostics["input_tokens"] += max(0, int(provider_diagnostics.get("input_tokens") or 0))
        diagnostics["output_tokens"] += max(0, int(provider_diagnostics.get("output_tokens") or 0))
        diagnostics["total_tokens"] += max(0, int(provider_diagnostics.get("total_tokens") or 0))
        if not item:
            diagnostics[str(provider_diagnostics.get("error") or "vision_failed")] += 1
            continue
        description = str(item.get("description") or "").strip()[:240]
        if (
            item.get("relevant") is True
            and item.get("promotional") is not True
            and description
        ):
            output.append({**candidate, "description": description})
            diagnostics["approved"] += 1
        elif item.get("promotional") is True:
            diagnostics["promotional"] += 1
        else:
            diagnostics["irrelevant"] += 1
    diagnostics["candidates"] = len(candidates)
    diagnostics["eligible_candidates"] = len(eligible_candidates)
    diagnostics["reviewed"] = len(selected)
    return output[:output_limit], dict(diagnostics)


async def rich_search(
    env: dict[str, Any],
    query: str,
    image_query: str = "",
    depth: str = "standard",
    *,
    parallel_queries: bool = True,
    result_limit: int | None = None,
    image_limit: int = 8,
    target_date: str = "",
    strict_date: bool = False,
    prefer_recent: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    include_media: bool = True,
    response_language: object = "zh-CN",
    request_id: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    api_key = str(env.get("WSA_API_KEY") or "").strip()
    base_url = str(env.get("WSA_BASE_URL") or "https://api.wsa.cloud.tencent.com").rstrip("/")
    if not api_key:
        raise RuntimeError(text("search.provider_unconfigured", response_language))
    limit = max(4, min(18, int(result_limit))) if result_limit is not None else {
        "basic": 8, "standard": 12, "deep": 18,
    }.get(depth, 12)
    image_limit = max(0, min(8, int(image_limit)))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json; charset=utf-8"}
    provider_qualifiers = [
        text("model.search.provider_quality", response_language),
    ]
    if target_date:
        provider_qualifiers.append(text(
            "model.search.provider_date", response_language,
            target_date=target_date,
            constraint=text(
                "model.search.provider_date_strict" if strict_date else "model.search.provider_date_asof",
                response_language, target_date=target_date,
            ),
        ))
    provider_timeout = max(4, min(20, int(env.get("RICH_SEARCH_PROVIDER_TIMEOUT_SECONDS") or 10)))
    distinct_visual_query = bool(image_query and image_query.strip() != query.strip())
    # SearchPro already returns article passages and provider-supplied images.
    # Merge the planner's visual intent into the one factual request instead of
    # paying for a second near-duplicate search. Page extraction remains
    # concurrent and pixel review still happens below.
    if distinct_visual_query:
        provider_qualifiers.append(text(
            "model.search.provider_visual", response_language,
            image_query=image_query[:180],
        ))
    provider_query = _bounded_provider_query(query, provider_qualifiers)
    provider_time_window = _provider_time_window(
        target_date,
        strict_date=strict_date,
        prefer_recent=prefer_recent,
    )
    provider_payload = {"Query": provider_query, **provider_time_window}
    data, provider_request_count = await _searchpro_json_request(
        f"{base_url}/SearchPro",
        # Cnt and Industry remain premium-only. FromTime/ToTime are native
        # standard filters and let SearchPro do the first recency pass without
        # another provider call.
        provider_payload,
        headers,
        provider_timeout,
        request_id,
    )
    logging.info(
        "SearchPro completed request_id=%s attempts=%s elapsed_ms=%s",
        request_id,
        provider_request_count,
        round((time.perf_counter() - started) * 1000),
    )
    visual_data = data
    searched_at = time.perf_counter()
    candidate_limit = min(30, max(limit * 3, limit))
    candidate_results = _parse_pages(data, candidate_limit)
    date_filter = {
        "received": len(candidate_results),
        "kept": len(candidate_results),
        "undated": 0,
        "mismatched": 0,
    }
    if strict_date and target_date:
        candidate_results, date_filter = filter_sources_for_target_date(
            candidate_results, target_date
        )
        # Images are evidence-bearing search output too. Do not review or
        # expose media from an older/undated article after its source has been
        # removed by the same-day truth boundary.
    if prefer_recent and target_date and not strict_date:
        candidate_results, recent_filter = filter_preferred_recent_sources(
            candidate_results,
            target_date,
        )
        date_filter["recent"] = recent_filter
    results = rank_source_results(
        candidate_results, query, target_date, prefer_recent
    )[:limit]
    visual_results = results
    date_filter["kept"] = len(results)
    source_domains: list[str] = []
    for item in results:
        domain = source_domain(item.get("url"))
        if domain and domain not in source_domains:
            source_domains.append(domain)
    sources = [{
        "id": f"source-{index}", "source": item["source"], "title": item["title"],
        "snippet": item["snippet"][:240], "url": item["url"], "date": item["date"],
        # Keep SearchPro's article hero image available to the source card as
        # well as the separately reviewed full-width media pipeline.  Dropping
        # it here made visually rich provider results look text-only.
        "image": item.get("image", ""),
        "publisher": item.get("publisher", ""),
        "publisher_domain": source_domain(item.get("url")),
        "relevance_score": item.get("relevance_score", 0.0),
    } for index, item in enumerate(results, 1)]
    # Keep SearchPro's own article hero images as explicitly provisional
    # diagnostics. Production waits for pixel review and never exposes these
    # candidates as final answer media; the field remains compatible with
    # older persisted runs and the optional progressive provider API.
    source_by_url = {item["url"]: item for item in sources}
    preview_media = []
    for index, candidate in enumerate(_provider_image_candidates(results, response_language)[:image_limit], 1):
        source = source_by_url.get(candidate["source_url"], {})
        source_title = candidate.get("source_title") or source.get("title") or text("search.preview_image", response_language)
        preview_media.append({
            "id": f"preview-media-{index}", "kind": "image", "url": candidate["url"],
            "source_id": source.get("id", ""), "source_url": candidate["source_url"],
            "source_title": source_title, "alt": source_title, "caption": source_title,
            "attribution": source_title, "generated": False, "preview": True,
            "vision_reviewed": False,
        })
    base_metadata = {
        "schema_version": 2, "query": query, "results": sources, "media": [],
        "preview_media": preview_media,
        "images": [], "sources_used": ["wsa"] if sources else [], "total": len(sources),
        "target_date": target_date, "strict_date": strict_date, "date_filter": date_filter,
        "media_pending": include_media and image_limit > 0 and media_callback is not None and background_tasks is not None,
        "search_config": {
            "result_limit": limit,
            "image_limit": image_limit,
            "parallel_image_search": bool(parallel_queries),
            "media_delivery": (
                "disabled"
                if not include_media or image_limit == 0
                else "progressive"
                if media_callback is not None and background_tasks is not None
                else "blocking"
            ),
            "provider_request_count": provider_request_count,
            "prefer_recent": prefer_recent,
            "visual_query_merged": distinct_visual_query,
            "provider_timeout_seconds": provider_timeout,
            "source_domain_count": len(source_domains),
            "source_domains": source_domains[:12],
            "provider_time_window": provider_time_window,
            "page_fetch_limit": min(6, max(4, image_limit * 2)) if image_limit else 0,
        },
        "timings_ms": {
            "search": round((searched_at - started) * 1000),
            "page_media": 0, "vision": 0,
            "total": round((searched_at - started) * 1000),
        },
    }

    async def enrich_media() -> dict[str, Any]:
        page_fetch_limit = min(6, max(4, image_limit * 2))
        media_timeout = max(2, min(10, int(env.get("RICH_SEARCH_MEDIA_TIMEOUT_SECONDS") or 5)))
        visual_candidates = await _extract_candidates(
            visual_results,
            page_fetch_limit,
            parallel=parallel_queries,
            timeout_seconds=media_timeout,
        )
        extracted_at = time.perf_counter()
        review_goal = image_query.strip() or query
        vision_timeout = _vision_review_timeout(env)
        try:
            reviewed, diagnostics = await asyncio.wait_for(
                _vision_filter(env, review_goal, visual_candidates, image_limit),
                timeout=vision_timeout + 0.5,
            )
        except asyncio.TimeoutError:
            reviewed, diagnostics = [], {"timeout": 1, "candidates": len(visual_candidates), "reviewed": 0}
        # A vision outage should not turn a sourced answer into a permanently
        # text-only response. Retain a deterministically relevant, traceable
        # page image only when the vision chain made no relevance decision. If
        # vision actively rejected candidates, keep the list empty instead.
        explicit_rejection = bool(
            diagnostics.get("approved", 0)
            or diagnostics.get("irrelevant", 0)
            or diagnostics.get("promotional", 0)
        )
        if not reviewed and not explicit_rejection:
            provider_fallbacks = _source_bound_fallback_candidates(
                _provider_image_candidates(results, response_language),
                review_goal,
                set(source_by_url),
                image_limit,
                require_semantic_overlap=False,
            )
            page_fallbacks = _source_bound_fallback_candidates(
                visual_candidates,
                review_goal,
                set(source_by_url),
                image_limit,
            )
            fallback_candidates = []
            fallback_urls: set[str] = set()
            for candidate in provider_fallbacks + page_fallbacks:
                if candidate["url"] in fallback_urls:
                    continue
                fallback_urls.add(candidate["url"])
                fallback_candidates.append(candidate)
                if len(fallback_candidates) >= image_limit:
                    break
            if fallback_candidates:
                reviewed = [{
                    **candidate,
                    "description": str(
                        candidate.get("context")
                        or candidate.get("alt")
                        or candidate.get("source_title")
                        or text("search.article_hero", response_language)
                    )[:240],
                    "vision_reviewed": False,
                    "vision_fallback": True,
                    # Exact source binding is checked again by the domain and
                    # frontend. This never becomes vision-reviewed evidence.
                    "source_bound_fallback": True,
                } for candidate in fallback_candidates]
                diagnostics = {
                    **diagnostics,
                    "source_bound_fallback": len(reviewed),
                }
        reviewed_at = time.perf_counter()
        media = []
        for index, candidate in enumerate(reviewed, 1):
            source = source_by_url.get(candidate["source_url"], {})
            caption = candidate["description"]
            media.append({
                "id": f"media-{index}", "kind": "image", "url": candidate["url"],
                "source_id": source.get("id", ""), "source_url": candidate["source_url"],
                "source_title": candidate["source_title"], "alt": caption, "caption": caption,
                "attribution": candidate["source_title"], "generated": False,
                "vision_reviewed": candidate.get("vision_reviewed", True),
                **({"vision_fallback": True} if candidate.get("vision_fallback") else {}),
                **({"source_bound_fallback": True} if candidate.get("source_bound_fallback") else {}),
            })
        enriched = {
            **base_metadata, "media": media, "images": [item["url"] for item in media],
            "media_pending": False, "vision_diagnostics": diagnostics,
            "timings_ms": {
                "search": base_metadata["timings_ms"]["search"],
                "page_media": round((extracted_at - searched_at) * 1000),
                "vision": round((reviewed_at - extracted_at) * 1000),
                "total": round((reviewed_at - started) * 1000),
            },
        }
        logging.info(
            "rich search media candidates=%s approved=%s diagnostics=%s",
            diagnostics.get("candidates", 0), len(media), diagnostics,
        )
        if media_callback is not None:
            await media_callback(enriched)
        return enriched

    if not include_media or image_limit == 0:
        return base_metadata
    if media_callback is not None and background_tasks is not None:
        task = asyncio.create_task(enrich_media())
        background_tasks.append(task)
        return base_metadata
    return await enrich_media()
