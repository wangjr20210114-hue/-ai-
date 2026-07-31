"""Makers provider adapter for the rich-search pipeline; not an Agent route.

Search pages provide image candidates and surrounding text. HY-Vision then reviews
the real pixels against both the user question and page context.  Only reviewed
images are exposed to the answer model as ordinary Markdown resources.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from html import unescape
from typing import Any, Awaitable, Callable

from .web_media import collect_page_media
from .vision import vision_completion, vision_providers


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


def _provider_image_candidates(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return only SearchPro-supplied article images, never page-scraped media.

    These are the conservative fallback when every configured vision provider is
    unavailable or times out. They are not used when vision explicitly rejects
    an image as irrelevant.
    """
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        image = unescape(str(result.get("image") or "").strip())
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
            "alt": "",
            "context": "搜索服务返回的文章主图",
            "source_url": result["url"],
            "source_title": result["title"],
        })
    return candidates


def _json_request(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))


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
        image = str(
            page.get("image") or page.get("image_url") or page.get("thumbnail")
            or _embedded_image_url(snippet)
        ).strip()
        if image.startswith("http://"):
            image = "https://" + image[len("http://"):]
        results.append({
            "source": source_kind, "title": str(page.get("title") or page.get("name") or url)[:200],
            "snippet": snippet[:500],
            "url": url,
            "image": image,
            "date": str(page.get("date") or page.get("publish_time") or "")[:40],
        })
        if len(results) >= limit:
            break
    return results


def _date_from_text(value: str, target_year: int | None = None) -> str:
    """Return a canonical publication date found in provider metadata/text."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit() and len(text) in {10, 13}:
        try:
            stamp = int(text) / (1000 if len(text) == 13 else 1)
            return datetime.fromtimestamp(stamp).date().isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    full = re.search(r"(?<!\d)(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text)
    if full:
        try:
            return date(int(full.group(1)), int(full.group(2)), int(full.group(3))).isoformat()
        except ValueError:
            return ""
    if target_year:
        short = re.search(r"(?<!\d)(\d{1,2})[月./-](\d{1,2})日?(?!\d)", text)
        if short:
            try:
                return date(target_year, int(short.group(1)), int(short.group(2))).isoformat()
            except ValueError:
                return ""
    return ""


def _filter_for_target_date(
    results: list[dict[str, Any]], target_date: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Strictly retain sources whose publication date can be verified."""
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return results, {"received": len(results), "kept": len(results), "undated": 0, "mismatched": 0}
    kept: list[dict[str, Any]] = []
    undated = 0
    mismatched = 0
    for item in results:
        raw_date = str(item.get("date") or "")
        published = _date_from_text(raw_date, target.year)
        if not published:
            published = _date_from_text(
                f"{item.get('title') or ''} {item.get('snippet') or ''}", target.year,
            )
        if not published:
            undated += 1
            continue
        if published != target.isoformat():
            mismatched += 1
            continue
        kept.append({**item, "date": published})
    return kept, {
        "received": len(results), "kept": len(kept),
        "undated": undated, "mismatched": mismatched,
    }


async def _extract_candidates(
    results: list[dict[str, Any]], page_limit: int = 6, parallel: bool = True,
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
    if parallel:
        batches = await asyncio.gather(*(page(result) for result in selected_results))
    else:
        batches = [await page(result) for result in selected_results]
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
    prompt = (
        '分析图片与用户查询的关系，只返回 JSON：'
        '{"description":"准确描述图片实际内容","relevant":true或false,"promotional":true或false}。\n'
        '以图片本身为准，网页上下文仅供参考。广告、促销价格、热线、二维码、Logo、图标、装饰、UI、占位图、纯文字截图或无关内容必须为 false；'
        '图片能识别或呈现查询中的具体事件、人物、产品、地点或报道主体，且与来源标题语义一致时即可为 true；'
        '不要求图片证明整篇回答，也不要因为无法确认次要背景细节而拒绝一张明显相关的非宣传图片。'
        '品牌营销海报、带促销卖点的产品宣传图或商业导流图必须 promotional=true；普通新闻现场或客观产品实拍为 false。\n'
        f'用户问题：{query[:120]}\n网页上下文：{(candidate.get("context") or candidate.get("alt") or candidate.get("source_title") or "")[:300]}'
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
        prompt = (
            '快速审核图片，不做背景推理或深度分析。只判断图片是否直接帮助回答用户问题，以及是否属于广告、'
            '促销、二维码、Logo、图标、UI、占位图、纯文字截图或无关内容；这些情况必须判为 false。'
            '图片能识别或呈现查询中的具体事件、人物、产品、地点或报道主体，且与来源标题语义一致时即可判为 true；'
            '不要因无法确认次要背景细节而拒绝明显相关的非宣传图片。'
            '品牌营销海报、带促销卖点的产品宣传图或商业导流图必须 promotional=true；'
            '普通新闻现场或客观产品实拍为 false。'
            '只返回简短 JSON：{"description":"一句话描述可见主体","relevant":true,"promotional":false}。\n'
            f'用户问题：{query[:160]}\n网页上下文：{context}'
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
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    include_media: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    api_key = str(env.get("WSA_API_KEY") or "").strip()
    base_url = str(env.get("WSA_BASE_URL") or "https://api.wsa.cloud.tencent.com").rstrip("/")
    if not api_key:
        raise RuntimeError("富搜索缺少 WSA_API_KEY")
    limit = max(4, min(18, int(result_limit))) if result_limit is not None else {
        "basic": 8, "standard": 12, "deep": 18,
    }.get(depth, 12)
    image_limit = max(0, min(8, int(image_limit)))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json; charset=utf-8"}
    provider_query = query
    if target_date:
        provider_query += (
            f"\n当前日期：{target_date}。"
            + (f"只返回发布日期可核验为 {target_date} 的当日内容，每条结果必须带发布日期。" if strict_date
               else "检索和排序必须以该日期为时间基准，不要混用旧年份信息。")
        )
    provider_timeout = max(4, min(20, int(env.get("RICH_SEARCH_PROVIDER_TIMEOUT_SECONDS") or 10)))
    distinct_visual_query = bool(image_query and image_query.strip() != query.strip())
    # SearchPro already returns article passages and provider-supplied images.
    # Merge the planner's visual intent into the one factual request instead of
    # paying for a second near-duplicate search. Page extraction remains
    # concurrent and pixel review still happens below.
    if distinct_visual_query:
        provider_query += f"\n同时优先返回包含这些可视对象的结果：{image_query[:180]}"
    data = await asyncio.wait_for(
        asyncio.to_thread(
            _json_request,
            f"{base_url}/SearchPro",
            {"Query": provider_query[:500]},
            headers,
            provider_timeout,
        ),
        timeout=provider_timeout + 0.5,
    )
    visual_data = data
    searched_at = time.perf_counter()
    results = _parse_pages(data, limit)
    visual_results = results
    date_filter = {"received": len(results), "kept": len(results), "undated": 0, "mismatched": 0}
    if strict_date and target_date:
        results, date_filter = _filter_for_target_date(results, target_date)
        # Images are evidence-bearing search output too. Do not review or
        # expose media from an older/undated article after its source has been
        # removed by the same-day truth boundary.
        visual_results = results
    sources = [{
        "id": f"source-{index}", "source": item["source"], "title": item["title"],
        "snippet": item["snippet"][:240], "url": item["url"], "date": item["date"],
        # Keep SearchPro's article hero image available to the source card as
        # well as the separately reviewed full-width media pipeline.  Dropping
        # it here made visually rich provider results look text-only.
        "image": item.get("image", ""),
    } for index, item in enumerate(results, 1)]
    # Keep SearchPro's own article hero images as explicitly provisional
    # diagnostics. Production waits for pixel review and never exposes these
    # candidates as final answer media; the field remains compatible with
    # older persisted runs and the optional progressive provider API.
    source_by_url = {item["url"]: item for item in sources}
    preview_media = []
    for index, candidate in enumerate(_provider_image_candidates(results)[:image_limit], 1):
        source = source_by_url.get(candidate["source_url"], {})
        source_title = candidate.get("source_title") or source.get("title") or "搜索结果文章配图"
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
            "provider_request_count": 1,
            "visual_query_merged": distinct_visual_query,
            "provider_timeout_seconds": provider_timeout,
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
        try:
            visual_candidates = await asyncio.wait_for(
                _extract_candidates(visual_results, page_fetch_limit, parallel=parallel_queries),
                timeout=media_timeout,
            )
        except asyncio.TimeoutError:
            # Do not discard fast provider-supplied article images merely
            # because one source page was slow to parse.
            visual_candidates = _provider_image_candidates(visual_results)
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
        # A vision outage should not turn a news answer into a permanently
        # text-only response. SearchPro's own article hero image is traceable
        # to a source URL, so retain it as an explicitly unreviewed fallback
        # when the vision chain produced no relevance decision. If vision
        # actively rejected candidates, keep the list empty instead.
        explicit_rejection = bool(
            diagnostics.get("approved", 0)
            or diagnostics.get("irrelevant", 0)
        )
        if not reviewed and not explicit_rejection:
            fallback_candidates = _provider_image_candidates(results)[:image_limit]
            if fallback_candidates:
                reviewed = [{
                    **candidate,
                    "description": str(candidate.get("source_title") or "搜索结果文章主图")[:240],
                    "vision_reviewed": False,
                    "vision_fallback": True,
                } for candidate in fallback_candidates]
                diagnostics = {
                    **diagnostics,
                    "provider_fallback": len(reviewed),
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


def evidence_for_model(
    metadata: dict[str, Any], *, require_relevant_image: bool = False,
) -> str:
    sources = "\n".join(
        f"- {item.get('id') or 'source'} | 类型={item.get('source') or 'web'} | [{item['title']}]({item['url']})"
        f" | 发布日期={item.get('date') or '未标注'} | 摘要={item['snippet']}"
        for item in metadata.get("results", [])
    )
    media = "\n".join(
        f"- {item.get('id') or 'media'} | source_id={item.get('source_id') or 'none'}"
        f" | 图片说明={item['caption']} | 图片URL={item['url']}"
        f" | 来源={item.get('source_title') or item.get('source_url') or '未知'}"
        f"{' | 视觉审核暂不可用，仅作文章主图降级' if item.get('vision_fallback') or item.get('vision_reviewed') is False else ''}"
        for item in metadata.get("media", [])
    ) or "无通过视觉筛选的图片，不要插图。"
    media_status = (
        "图片正在后台审核。本轮只写正文与来源链接，不要插图，也不要声称正在生成图片。"
        if metadata.get("media_pending")
        else
        "这里只列出审核通过的图片；若正文采用相应事实，请正常引用该图片 source_id 对应的网页来源。"
        "前端会按 source_id 把图片放在同源引用段落后；没有精确来源引用时不会插图。"
    )
    image_instruction = (
        "本轮语义计划器已判断真实图片能明显帮助理解；若采用相关事实，必须引用它对应的网页来源，"
        "但不要自行输出图片 Markdown。"
        if require_relevant_image and metadata.get("media")
        else
        "图片由前端确定性放置，不属于回答正文协议。"
    )
    temporal_instruction = (
        f"本轮要求严格限定发布日期为 {metadata.get('target_date')}。"
        "上方为空即表示没有核实到当日来源；必须直接说明这一证据边界，"
        "不得用其他日期、未标日期或模型记忆补成当日新闻。\n\n"
        if metadata.get("strict_date") and metadata.get("target_date")
        else ""
    )
    return (
        temporal_instruction
        + f"可选网页/视频素材：\n{sources or '无'}\n\n"
        f"经视觉模型审核的可选图片素材：\n{media}\n{media_status}\n\n"
        f"这些只是事实素材，不是回答提纲。由你决定采用哪些事实以及以什么顺序呈现。{image_instruction}"
        "若采用网页或视频，直接在相关段落使用上面给出的 Markdown 链接。"
        "不要输出任何媒体占位符，不要自行输出图片 Markdown，不要使用未提供的图片 URL。"
    )
