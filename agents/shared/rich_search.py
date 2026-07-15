"""Makers adapter for the mature v4.2 rich-search pipeline.

Search pages provide image candidates and surrounding text.  Hy3 then reviews
the real pixels against both the user question and page context.  Only reviewed
images are exposed to the answer model as ordinary Markdown resources.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from typing import Any

from .web_media import collect_page_media


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
        results.append({
            "source": "wsa", "title": str(page.get("title") or page.get("name") or url)[:200],
            "snippet": str(page.get("passage") or page.get("snippet") or page.get("description") or "")[:500],
            "url": url, "image": str(page.get("image") or page.get("image_url") or page.get("thumbnail") or ""),
            "date": str(page.get("date") or page.get("publish_time") or "")[:40],
        })
        if len(results) >= limit:
            break
    return results


async def _extract_candidates(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for result in results:
        image = str(result.get("image") or "").strip()
        if image.startswith(("http://", "https://")):
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


def _review_image(env: dict[str, Any], candidate: dict[str, str], query: str) -> str:
    api_key = str(env.get("HUNYUAN_API_KEY") or "").strip()
    if not api_key:
        return ""
    base_url = str(env.get("HUNYUAN_BASE_URL") or "https://api.lkeap.cloud.tencent.com/plan/v3").rstrip("/")
    model = str(env.get("HUNYUAN_VISION_MODEL") or env.get("HUNYUAN_MODEL") or "hy3")
    if model == "hunyuan-vision":
        model = "hy3"
    prompt = (
        '分析图片与用户查询的关系，只返回 JSON：{"description":"准确描述图片实际内容","relevant":true或false}。\n'
        '以图片本身为准，网页上下文仅供参考。广告、促销价格、热线、二维码、Logo、图标、装饰、UI、占位图、纯文字截图或无关内容必须为 false；'
        '只有图片主体能直接帮助理解用户问题才为 true，不确定时为 false。\n'
        f'用户问题：{query[:120]}\n网页上下文：{(candidate.get("context") or candidate.get("alt") or candidate.get("source_title") or "")[:300]}'
    )
    payload = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": candidate["url"]}},
    ]}], "max_tokens": 160, "temperature": 0.2}
    data = None
    for attempt in range(2):
        try:
            data = _json_request(
                f"{base_url}/chat/completions", payload,
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, 20,
            )
            break
        except urllib.error.HTTPError as error:
            if attempt == 0 and (error.code == 429 or error.code >= 500):
                time.sleep(1.2)
                continue
            return ""
        except Exception:
            return ""
    try:
        if data is None:
            return ""
        raw = str(data["choices"][0]["message"]["content"]).strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
        reviewed = json.loads(raw)
        if reviewed.get("relevant") is True:
            return str(reviewed.get("description") or "").strip()[:240]
    except Exception:
        return ""
    return ""


async def _vision_filter(env: dict[str, Any], query: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    semaphore = asyncio.Semaphore(4)

    async def review(candidate: dict[str, str]):
        async with semaphore:
            description = await asyncio.to_thread(_review_image, env, candidate, query)
        return candidate, description

    # Review one bounded batch at a time. Stop only after enough images have
    # actually passed vision review; irrelevant/ad candidates trigger the next
    # batch instead of reducing quality.
    bounded = candidates[:30]
    for start in range(0, len(bounded), 8):
        reviewed = await asyncio.gather(*(review(item) for item in bounded[start:start + 8]))
        output.extend({**candidate, "description": description} for candidate, description in reviewed if description)
        if len(output) >= 4:
            break
    return output[:4]


async def rich_search(env: dict[str, Any], query: str, image_query: str = "", depth: str = "standard") -> dict[str, Any]:
    api_key = str(env.get("WSA_API_KEY") or "").strip()
    base_url = str(env.get("WSA_BASE_URL") or "https://api.wsa.cloud.tencent.com").rstrip("/")
    if not api_key:
        raise RuntimeError("富搜索缺少 WSA_API_KEY")
    limit = {"basic": 8, "standard": 12, "deep": 18}.get(depth, 12)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json; charset=utf-8"}
    data = await asyncio.to_thread(_json_request, f"{base_url}/SearchPro", {"Query": query[:300]}, headers, 25)
    results = _parse_pages(data, limit)
    visual_results = results
    if image_query and image_query.strip() != query.strip():
        visual_data = await asyncio.to_thread(
            _json_request, f"{base_url}/SearchPro", {"Query": image_query[:300]}, headers, 25,
        )
        visual_results = _parse_pages(visual_data, 8)
    sources = [{
        "id": f"source-{index}", "source": item["source"], "title": item["title"],
        "snippet": item["snippet"][:240], "url": item["url"], "date": item["date"],
    } for index, item in enumerate(results, 1)]
    source_by_url = {item["url"]: item for item in sources}
    visual_candidates = await _extract_candidates(visual_results)
    reviewed = await _vision_filter(env, query, visual_candidates)
    if not reviewed and visual_results is not results:
        # Image-oriented search can occasionally return pages with blocked or
        # decorative assets. Re-review candidates from the factual source set;
        # nothing bypasses vision approval.
        seen = {item["url"] for item in visual_candidates}
        fact_candidates = [
            item for item in await _extract_candidates(results)
            if item["url"] not in seen
        ]
        reviewed = await _vision_filter(env, query, fact_candidates)
    media = []
    for index, candidate in enumerate(reviewed, 1):
        source = source_by_url.get(candidate["source_url"], {})
        caption = candidate["description"]
        media.append({
            "id": f"media-{index}", "kind": "image", "url": candidate["url"],
            "source_id": source.get("id", ""), "source_url": candidate["source_url"], "source_title": candidate["source_title"],
            "alt": caption, "caption": caption, "attribution": candidate["source_title"], "generated": False,
        })
    return {
        "schema_version": 2, "query": query, "results": sources, "media": media,
        "images": [item["url"] for item in media], "sources_used": ["wsa"] if sources else [], "total": len(sources),
    }


def evidence_for_model(metadata: dict[str, Any]) -> str:
    sources = "\n".join(
        f"- [{item['source']}] {item['title']}：{item['snippet']}\n  {item['url']}"
        for item in metadata.get("results", [])
    )
    media = "\n".join(
        f"- ![{item['caption']}]({item['url']})"
        for item in metadata.get("media", [])
    ) or "无通过视觉筛选的图片，不要插图。"
    return (
        f"搜索结果：\n{sources or '无'}\n\n"
        f"视觉模型已筛除广告和无关内容，以下标准 Markdown 图片可供排版：\n{media}\n\n"
        "只在图片与当前段落直接相关时插入；可以改写 ALT，使其既准确描述图片本身，也说明图片在当前上下文中的意义。"
        "不要使用未提供的图片 URL，不要为了凑图插入无关图片。来源链接可自然放入相关段落或推荐阅读。"
    )
