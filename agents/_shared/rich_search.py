"""Makers adapter for the rich-search pipeline; not an Agent route.

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


def _json_request(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 425, 429} and error.code < 500:
                break
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        if attempt < 2:
            time.sleep(0.35 * (attempt + 1))
    logging.warning("rich search provider request failed url=%s error=%s", url, type(last_error).__name__)
    raise RuntimeError("联网搜索服务暂时不可达，请稍后重试") from last_error


async def _safe_search_request(
    url: str, payload: dict, headers: dict, timeout: int,
) -> tuple[dict[str, Any], str]:
    try:
        return await asyncio.to_thread(_json_request, url, payload, headers, timeout), ""
    except Exception as error:
        logging.warning("rich search query failed query=%s error=%s", payload.get("Query", "")[:120], error)
        return {}, "network_unavailable"


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
        results.append({
            "source": source_kind, "title": str(page.get("title") or page.get("name") or url)[:200],
            "snippet": str(page.get("passage") or page.get("snippet") or page.get("description") or "")[:500],
            "url": url, "image": str(page.get("image") or page.get("image_url") or page.get("thumbnail") or ""),
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
        if re.search(r"今天|今日|刚刚|\d+\s*(?:分钟|小时)前", raw_date):
            published = target.isoformat()
        else:
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


async def _extract_candidates(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for result in results:
        image = unescape(str(result.get("image") or "").strip())
        path = urllib.parse.urlparse(image).path.lower()
        if image.startswith(("http://", "https://")) and not path.endswith((".svg", ".gif", ".ico")):
            candidates.append({"url": image, "alt": "", "context": "搜索结果主图", "source_url": result["url"], "source_title": result["title"]})

    async def page(result: dict[str, Any]) -> list[dict[str, str]]:
        try:
            items = await collect_page_media(result["url"], 10)
        except Exception:
            return []
        return [{**item, "source_url": result["url"], "source_title": result["title"]} for item in items]

    for batch in await asyncio.gather(*(page(result) for result in results[:6])):
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
        or env.get("HUNYUAN_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return "", "missing_api_key"
    model = str(env.get("HUNYUAN_VISION_MODEL") or "hy-vision-2.0-instruct")
    prompt = (
        '分析图片与用户查询的关系，只返回 JSON：{"description":"准确描述图片实际内容","relevant":true或false}。\n'
        '以图片本身为准，网页上下文仅供参考。广告、促销价格、热线、二维码、Logo、图标、装饰、UI、占位图、纯文字截图或无关内容必须为 false；'
        '只有图片主体能直接帮助理解用户问题才为 true，不确定时为 false。\n'
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
        if reviewed.get("relevant") is True:
            description = str(reviewed.get("description") or "").strip()[:240]
            return (description, "approved") if description else ("", "missing_description")
        description = str(reviewed.get("description") or "")
        if any(marker in description for marker in ("未提供图片", "没有图片", "无法描述图片", "看不到图片")):
            return "", "image_not_seen"
        return "", "irrelevant"
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return "", "invalid_response"


async def _vision_filter(
    env: dict[str, Any], query: str, candidates: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    output: list[dict[str, str]] = []
    diagnostics: Counter[str] = Counter()
    semaphore = asyncio.Semaphore(4)

    async def review(candidate: dict[str, str]):
        async with semaphore:
            description, outcome = await asyncio.to_thread(_review_image, env, candidate, query)
        return candidate, description, outcome

    # Review one bounded batch at a time. Stop only after enough images have
    # actually passed vision review; irrelevant/ad candidates trigger the next
    # batch instead of reducing quality.
    bounded = candidates[:30]
    for start in range(0, len(bounded), 8):
        reviewed = await asyncio.gather(*(review(item) for item in bounded[start:start + 8]))
        diagnostics.update(outcome for _candidate, _description, outcome in reviewed)
        output.extend(
            {**candidate, "description": description}
            for candidate, description, _outcome in reviewed if description
        )
        if len(output) >= 4:
            break
    diagnostics["candidates"] = len(bounded)
    diagnostics["reviewed"] = sum(
        count for key, count in diagnostics.items() if key not in {"candidates", "reviewed"}
    )
    return output[:4], dict(diagnostics)


async def rich_search(
    env: dict[str, Any],
    query: str,
    image_query: str = "",
    depth: str = "standard",
    *,
    parallel_queries: bool = True,
    target_date: str = "",
    strict_date: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    api_key = str(env.get("WSA_API_KEY") or "").strip()
    base_url = str(env.get("WSA_BASE_URL") or "https://api.wsa.cloud.tencent.com").rstrip("/")
    if not api_key:
        raise RuntimeError("富搜索缺少 WSA_API_KEY")
    limit = {"basic": 8, "standard": 12, "deep": 18}.get(depth, 12)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json; charset=utf-8"}
    provider_query = query
    if target_date:
        provider_query += (
            f"\n当前日期：{target_date}。"
            + (f"只返回发布日期可核验为 {target_date} 的当日内容，每条结果必须带发布日期。" if strict_date
               else "检索和排序必须以该日期为时间基准，不要混用旧年份信息。")
        )
    distinct_visual_query = bool(image_query and image_query.strip() != query.strip())
    visual_provider_query = image_query
    if target_date and visual_provider_query:
        visual_provider_query += f" {target_date} 当日发布 现场照片 新闻图片"
    fact_request = _safe_search_request(
        f"{base_url}/SearchPro", {"Query": provider_query[:500]}, headers, 25,
    )
    visual_request = _safe_search_request(
        f"{base_url}/SearchPro", {"Query": visual_provider_query[:500]}, headers, 25,
    ) if distinct_visual_query else None
    if distinct_visual_query and parallel_queries:
        (data, fact_error), (visual_data, visual_error) = await asyncio.gather(fact_request, visual_request)
    elif distinct_visual_query:
        data, fact_error = await fact_request
        visual_data, visual_error = await visual_request
    else:
        data, fact_error = await fact_request
        visual_data, visual_error = data, ""
    searched_at = time.perf_counter()
    results = _parse_pages(data, limit)
    visual_results = results
    if distinct_visual_query:
        visual_results = _parse_pages(visual_data, 8)
    date_filter = {"received": len(results), "kept": len(results), "undated": 0, "mismatched": 0}
    if strict_date and target_date:
        results, date_filter = _filter_for_target_date(results, target_date)
        if distinct_visual_query:
            visual_results, _ = _filter_for_target_date(visual_results, target_date)
    sources = [{
        "id": f"source-{index}", "source": item["source"], "title": item["title"],
        "snippet": item["snippet"][:240], "url": item["url"], "date": item["date"],
    } for index, item in enumerate(results, 1)]
    base_metadata = {
        "schema_version": 2, "query": query, "results": sources, "media": [],
        "images": [], "sources_used": ["wsa"] if sources else [], "total": len(sources),
        "search_errors": [error for error in (fact_error, visual_error) if error],
        "target_date": target_date, "strict_date": strict_date, "date_filter": date_filter,
        "media_pending": media_callback is not None and background_tasks is not None,
        "timings_ms": {
            "search": round((searched_at - started) * 1000),
            "page_media": 0, "vision": 0,
            "total": round((searched_at - started) * 1000),
        },
    }

    async def enrich_media() -> dict[str, Any]:
        source_by_url = {item["url"]: item for item in sources}
        visual_candidates = await _extract_candidates(visual_results)
        extracted_at = time.perf_counter()
        review_goal = image_query.strip() or query
        reviewed, diagnostics = await _vision_filter(env, review_goal, visual_candidates)
        if not reviewed and visual_results is not results:
            # A second factual-source pass is still vision-gated; it never
            # promotes an unreviewed candidate.
            seen = {item["url"] for item in visual_candidates}
            fact_candidates = [
                item for item in await _extract_candidates(results)
                if item["url"] not in seen
            ]
            reviewed, second_diagnostics = await _vision_filter(env, review_goal, fact_candidates)
            diagnostics = {
                key: diagnostics.get(key, 0) + second_diagnostics.get(key, 0)
                for key in set(diagnostics) | set(second_diagnostics)
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

    if media_callback is not None and background_tasks is not None:
        task = asyncio.create_task(enrich_media())
        background_tasks.append(task)
        return base_metadata
    return await enrich_media()


def evidence_for_model(metadata: dict[str, Any]) -> str:
    sources = "\n".join(
        f"- {item.get('id') or 'source'} | 类型={item.get('source') or 'web'} | [{item['title']}]({item['url']})"
        f" | 发布日期={item.get('date') or '未标注'} | 摘要={item['snippet']}"
        for item in metadata.get("results", [])
    )
    media = "\n".join(
        f"- {item.get('id') or 'media'} | ![{item['caption']}]({item['url']}) | 来源={item.get('source_title') or item.get('source_url') or '未知'}"
        for item in metadata.get("media", [])
    ) or "无通过视觉筛选的图片，不要插图。"
    return (
        f"可选网页/视频素材：\n{sources or '无'}\n\n"
        f"经视觉模型审核的可选图片素材：\n{media}\n\n"
        "这些只是素材，不是回答提纲。由你决定采用哪些、放在何处以及以什么顺序呈现，也可以全部不用。"
        "若采用网页或视频，直接在相关段落使用上面给出的 Markdown 链接；若采用图片，直接在相关段落使用上面给出的 Markdown 图片。"
        "前端会就地渲染为网页卡片、视频卡片或带来源图片。不要把资源统一罗列或堆在回答末尾。"
        "不要使用未提供的图片 URL，不要插入无关素材。"
    )
