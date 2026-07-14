"""Multimodal search adapter built only from Makers-provided tools."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlparse


MAX_RESULTS = 12
MAX_PAGES_TO_FETCH = 6
MAX_MEDIA = 12
MAX_MEDIA_PER_SOURCE = 3
MAX_EXCERPT_CHARS = 2200
MAX_VISION_REVIEWS = 12
VISION_BATCH_SIZE = 4
VISION_MAX_CONCURRENCY = 3

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

_PAGE_MEDIA_SCRIPT = r"""
JSON.stringify({
  text: ((document.querySelector('article, main') || document.body)?.innerText || '').slice(0, 5000),
  media: [
    ...Array.from(document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]')).map(el => ({kind: 'image', url: el.content, caption: el.getAttribute('alt') || ''})),
    ...Array.from(document.images).slice(0, 30).map(el => ({kind: 'image', url: el.currentSrc || el.src, caption: el.alt || el.title || el.closest('figure')?.innerText?.slice(0, 160) || el.parentElement?.innerText?.slice(0, 160) || '', width: el.naturalWidth || el.width, height: el.naturalHeight || el.height, className: el.className || ''})),
    ...Array.from(document.querySelectorAll('video')).slice(0, 10).flatMap(el => [
      {kind: 'video', url: el.currentSrc || el.src, caption: el.title || ''},
      {kind: 'image', url: el.poster, caption: el.title || '视频封面'}
    ]),
    ...Array.from(document.querySelectorAll('iframe[src]')).filter(el => /youtube|youtu\.be|bilibili|v\.qq\.com/i.test(el.src)).slice(0, 10).map(el => ({kind: 'video', url: el.src, caption: el.title || '嵌入视频'}))
  ]
})
"""

_SKIP_SEARCH_PHRASES = (
    "你好", "谢谢", "再见", "你是谁", "帮我画", "生成图片", "翻译下面", "总结下面",
)
_MEDIA_BLOCK_WORDS = (
    "advert", "banner", "logo", "avatar", "icon", "sprite", "tracking",
    "pixel", "qrcode", "qr-code", "share", "loading", "placeholder",
    "广告", "二维码", "头像", "图标",
)
_WEAK_MEDIA_CAPTIONS = {
    "", "图片", "配图", "文章配图", "页面配图", "相关图片", "相关媒体",
    "页面视频", "视频封面", "嵌入视频", "image", "photo", "picture", "pic",
}


def should_search(message: str) -> bool:
    """Search substantive questions by default, matching the pre-migration UX."""

    text = re.sub(r"\s+", "", str(message or ""))
    if len(text) <= 5:
        return False
    return not any(phrase in text for phrase in _SKIP_SEARCH_PHRASES)


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _safe_public_url(value: Any, base_url: str = "") -> str:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("data:", "blob:", "javascript:")):
        return ""
    absolute = urljoin(base_url, raw)
    try:
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        if parsed.username or parsed.password:
            return ""
        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            return ""
    except (TypeError, ValueError):
        return ""
    return absolute


def _source_kind(url: str, site: str = "") -> str:
    haystack = f"{url} {site}".lower()
    if "weixin.qq.com" in haystack or "wechat" in haystack or "公众号" in haystack:
        return "wechat"
    if "zhihu.com" in haystack or "知乎" in haystack:
        return "zhihu"
    if "baike." in haystack or "百科" in haystack:
        return "baike"
    if site and site.lower() not in {"web", "网页"}:
        return "wsa"
    return "web"


def normalize_search_results(raw: Any) -> list[dict[str, Any]]:
    value = _json_value(raw)
    if isinstance(value, dict):
        value = value.get("results") or value.get("data") or value.get("pages") or []
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        url = _safe_public_url(item.get("href") or item.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        site = str(item.get("site") or item.get("source") or "").strip()
        normalized.append(
            {
                "id": f"source-{len(normalized) + 1}",
                "source": _source_kind(url, site),
                "title": str(item.get("title") or site or url).strip()[:240],
                "snippet": str(item.get("snippet") or item.get("content") or "").strip()[:600],
                "url": url,
                "site": site,
                "date": str(item.get("date") or "").strip(),
            }
        )
        if len(normalized) >= MAX_RESULTS:
            break
    return normalized


class _PageParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.media: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        if lowered == "meta":
            prop = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "")
            if prop in {"og:image", "twitter:image", "twitter:image:src"}:
                self._append_media("image", content, values.get("alt") or "页面配图", values)
            elif prop in {"og:video", "og:video:url", "og:video:secure_url"}:
                self._append_media("video", content, "页面视频", values)
            return
        if lowered == "img":
            src = values.get("src") or values.get("data-src") or values.get("data-original")
            if not src and values.get("srcset"):
                src = values["srcset"].split(",")[-1].strip().split(" ")[0]
            self._append_media("image", src or "", values.get("alt") or values.get("title") or "页面配图", values)
        elif lowered == "video":
            self._append_media("video", values.get("src", ""), values.get("title") or "页面视频", values)
            self._append_media("image", values.get("poster", ""), values.get("title") or "视频封面", values)
        elif lowered == "source" and str(values.get("type", "")).startswith("video/"):
            self._append_media("video", values.get("src", ""), "页面视频", values)
        elif lowered == "iframe":
            src = values.get("src", "")
            if any(domain in src.lower() for domain in ("youtube.com", "youtu.be", "bilibili.com", "v.qq.com")):
                self._append_media("video", src, values.get("title") or "嵌入视频", values)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if len(text) >= 2:
                self.text_parts.append(text)

    def _append_media(self, kind: str, raw_url: str, caption: str, attrs: dict[str, str]) -> None:
        url = _safe_public_url(raw_url, self.page_url)
        if not url:
            return
        descriptor = " ".join((url, caption, attrs.get("class", ""), attrs.get("id", ""))).lower()
        if any(word in descriptor for word in _MEDIA_BLOCK_WORDS):
            return
        width = int(re.sub(r"[^0-9]", "", attrs.get("width", "")) or 0)
        height = int(re.sub(r"[^0-9]", "", attrs.get("height", "")) or 0)
        if width and height and (width < 240 or height < 140):
            return
        self.media.append({"kind": kind, "url": url, "caption": caption.strip()[:180]})


def extract_page_content(raw: Any, source: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    value = _json_value(raw)
    if isinstance(value, dict):
        content = str(value.get("content") or value.get("html") or "")
        final_url = _safe_public_url(value.get("url") or value.get("href")) or source["url"]
    else:
        content = str(value or "")
        final_url = source["url"]
    parser = _PageParser(final_url)
    try:
        parser.feed(content)
    except (AssertionError, ValueError):
        pass
    excerpt = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()[:MAX_EXCERPT_CHARS]
    media = []
    seen: set[str] = set()
    for item in parser.media:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        media.append(
            {
                "id": "",
                "kind": item["kind"],
                "url": item["url"],
                "source_id": source["id"],
                "source_url": source["url"],
                "source_title": source["title"],
                "alt": item["caption"] or source["title"],
                "caption": item["caption"] or source["title"],
                "attribution": source["title"],
                "generated": False,
            }
        )
    return excerpt, media


def extract_evaluated_page(raw: Any, source: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    value = _json_value(raw)
    if isinstance(value, dict) and "data" in value:
        value = _json_value(value.get("data"))
    if not isinstance(value, dict):
        return "", []
    excerpt = re.sub(r"\s+", " ", str(value.get("text") or "")).strip()[:MAX_EXCERPT_CHARS]
    media = []
    for candidate in value.get("media", []):
        if not isinstance(candidate, dict):
            continue
        url = _safe_public_url(candidate.get("url"), source["url"])
        caption = str(candidate.get("caption") or "页面配图").strip()[:180]
        descriptor = f"{url} {caption} {candidate.get('className', '')}".lower()
        if not url or any(word in descriptor for word in _MEDIA_BLOCK_WORDS):
            continue
        try:
            width = int(candidate.get("width") or 0)
            height = int(candidate.get("height") or 0)
        except (TypeError, ValueError):
            width = height = 0
        if width and height and (width < 240 or height < 140):
            continue
        kind = "video" if candidate.get("kind") == "video" else "image"
        media.append({
            "id": "",
            "kind": kind,
            "url": url,
            "source_id": source["id"],
            "source_url": source["url"],
            "source_title": source["title"],
            "alt": caption,
            "caption": caption,
            "attribution": source["title"],
            "generated": False,
        })
    return excerpt, media


def select_media(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply only structural limits before visual review.

    Text in filenames, URLs, titles, and ALT attributes is not evidence that an
    image depicts the query, so it must never rank an image into the answer.
    """

    del query
    selected: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    seen: set[str] = set()
    for item in candidates:
        source_id = str(item.get("source_id") or "")
        if item["url"] in seen or source_counts.get(source_id, 0) >= MAX_MEDIA_PER_SOURCE:
            continue
        seen.add(item["url"])
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        selected.append({**item, "id": f"media-{len(selected) + 1}"})
        if len(selected) >= MAX_MEDIA:
            break
    return selected


async def _report_progress(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    **details: Any,
) -> None:
    if callback is None:
        return
    try:
        await callback({"stage": stage, "message": message, **details})
    except Exception:
        # Progress reporting must never make the search itself fail.
        pass


def _is_weak_caption(value: Any) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.lower() in _WEAK_MEDIA_CAPTIONS or len(text) < 3


def _contextual_alt(query: str, item: dict[str, Any]) -> str:
    """Build ALT from page semantics; visual review is only a safety gate."""

    caption = re.sub(r"\s+", " ", str(item.get("caption") or "")).strip()
    source_title = re.sub(r"\s+", " ", str(item.get("source_title") or "")).strip()
    if not _is_weak_caption(caption):
        return caption[:180]
    topic = re.sub(r"\s+", " ", query).strip()[:60]
    if source_title and topic:
        return f"{source_title}中与“{topic}”相关的图片"[:180]
    if source_title:
        return f"{source_title}的相关图片"[:180]
    return f"与“{topic}”相关的图片"[:180] if topic else "相关图片"


def _parse_vision_review(content: Any) -> dict[str, bool]:
    if isinstance(content, list):
        content = "".join(
            str(item.get("text") or "") if isinstance(item, dict) else str(item)
            for item in content
        )
    text = str(content or "").strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
    except (TypeError, ValueError):
        return {}
    decisions: dict[str, bool] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            decisions[str(item["id"])] = bool(item.get("keep")) and not bool(item.get("ad"))
    return decisions


async def review_images_with_vision(
    query: str,
    media: list[dict[str, Any]],
    vision_model: Any,
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    """Use vision only to reject ads and irrelevant images, never to author ALT."""

    images = [item for item in media if item.get("kind") == "image"]
    if not images:
        return [{**item, "alt": _contextual_alt(query, item)} for item in media]
    if vision_model is None:
        # Fail closed: unreviewed images must never appear in an answer.
        return [
            {**item, "alt": _contextual_alt(query, item)}
            for item in media
            if item.get("kind") != "image"
        ]

    await _report_progress(
        progress,
        "reviewing_media",
        f"正在用视觉模型筛选 {len(images)} 张图片，排除广告和无关内容…",
        current=0,
        total=len(images),
    )
    semaphore = asyncio.Semaphore(VISION_MAX_CONCURRENCY)

    async def review_batch(batch: list[dict[str, Any]]) -> tuple[dict[str, bool], int]:
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": (
                "你是搜索图片审核器。以图片画面为主要证据，判断每张图是否与用户问题高度相关并适合插入回答。"
                "来源标题和网页语义只能帮助理解上下文，不能替代对画面的判断。"
                "广告、促销海报、二维码、Logo、头像、界面装饰、占位图、与问题不高度相关或无法判断内容的图片必须丢弃。"
                "只返回 JSON 数组，每项格式为 {\"id\":\"media-1\",\"keep\":true,\"ad\":false}；"
                "不要生成图片描述或 ALT。\n"
                f"用户问题：{query[:300]}"
            ),
        }]
        for item in batch:
            content.extend([
                {
                    "type": "text",
                    "text": (
                        f"候选 {item['id']}；来源：{item.get('source_title') or '未知'}；"
                        f"网页语义：{item.get('caption') or '无'}"
                    ),
                },
                {"type": "image_url", "image_url": {"url": item["url"]}},
            ])
        decisions: dict[str, bool] = {}
        async with semaphore:
            try:
                from langchain_core.messages import HumanMessage

                response = await asyncio.wait_for(
                    vision_model.ainvoke(
                        [HumanMessage(content=content)],
                        config={"tags": ["internal_vision_review"]},
                    ),
                    timeout=45,
                )
                decisions.update(_parse_vision_review(getattr(response, "content", response)))
            except Exception:
                # Fail closed when the model cannot inspect the actual pixels.
                for item in batch:
                    decisions.setdefault(item["id"], False)
        return decisions, len(batch)

    batches = [
        images[offset:offset + VISION_BATCH_SIZE]
        for offset in range(0, len(images), VISION_BATCH_SIZE)
    ]
    reviewed: dict[str, bool] = {}
    completed = 0
    tasks = [asyncio.create_task(review_batch(batch)) for batch in batches]
    for task in asyncio.as_completed(tasks):
        decisions, batch_size = await task
        reviewed.update(decisions)
        completed += batch_size
        await _report_progress(
            progress,
            "reviewing_media",
            f"已审核 {completed}/{len(images)} 张图片…",
            current=completed,
            total=len(images),
        )

    kept: list[dict[str, Any]] = []
    for item in media:
        if item.get("kind") == "image" and not reviewed.get(str(item.get("id") or ""), False):
            continue
        kept.append({**item, "alt": _contextual_alt(query, item)})
    for index, item in enumerate(kept, start=1):
        item["id"] = f"media-{index}"
    return kept


async def build_rich_search_payload(
    query: str,
    search_tool: Any,
    browser_tool: Any = None,
    evaluate_tool: Any = None,
    vision_model: Any = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    await _report_progress(
        progress,
        "searching",
        f"正在检索“{query[:80]}”…",
        query=query[:300],
    )
    raw_results = await search_tool.ainvoke({"query": query, "maxResults": MAX_RESULTS})
    results = normalize_search_results(raw_results)
    await _report_progress(
        progress,
        "sources_found",
        f"找到 {len(results)} 个候选来源，准备逐页读取…",
        total=len(results),
    )
    candidates: list[dict[str, Any]] = []
    # WSA snippets sometimes already contain source-bound media tags.
    for source in results:
        _excerpt, snippet_media = extract_page_content(source.get("snippet", ""), source)
        candidates.extend(snippet_media)
    if browser_tool is not None:
        pages = results[:MAX_PAGES_TO_FETCH]
        for index, source in enumerate(pages, start=1):
            host = urlparse(source["url"]).hostname or source["url"]
            await _report_progress(
                progress,
                "fetching_page",
                f"正在读取 {index}/{len(pages)}：{source['title']}（{host}）",
                current=index,
                total=len(pages),
                source={
                    "title": source["title"],
                    "url": source["url"],
                    "source": source["source"],
                },
            )
            try:
                raw_page = await asyncio.wait_for(browser_tool.ainvoke({"url": source["url"]}), timeout=12)
            except Exception:
                continue
            excerpt, page_media = extract_page_content(raw_page, source)
            if evaluate_tool is not None:
                try:
                    evaluated = await asyncio.wait_for(
                        evaluate_tool.ainvoke({"script": _PAGE_MEDIA_SCRIPT}), timeout=8
                    )
                    evaluated_excerpt, evaluated_media = extract_evaluated_page(evaluated, source)
                    excerpt = evaluated_excerpt or excerpt
                    page_media.extend(evaluated_media)
                except Exception:
                    pass
            if excerpt:
                source["content_excerpt"] = excerpt
            candidates.extend(page_media)
    await _report_progress(
        progress,
        "selecting_media",
        f"已读取正文，正在从 {len(candidates)} 个媒体候选中筛选…",
        total=len(candidates),
    )
    media = select_media(query, candidates)
    media = await review_images_with_vision(
        query,
        media,
        vision_model,
        progress,
    )
    await _report_progress(
        progress,
        "composing",
        f"素材已就绪：{len(results)} 个来源、{len(media)} 个有效媒体，正在组织内容和排版…",
        sources=len(results),
        media=len(media),
    )
    payload = {
        "schema_version": 3,
        "query": query,
        "results": results,
        "images": [item["url"] for item in media if item["kind"] == "image"],
        "media": media,
        "sources_used": list(dict.fromkeys(item["source"] for item in results)),
        "total": len(results),
    }
    return payload


def search_meta_from_tool_content(content: Any) -> dict[str, Any] | None:
    value = _json_value(content)
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        return None
    results = []
    for item in value["results"][:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        url = _safe_public_url(item.get("url") or item.get("href"))
        if not url:
            continue
        results.append({
            "id": str(item.get("id") or f"source-{len(results) + 1}"),
            "source": str(item.get("source") or _source_kind(url)),
            "title": str(item.get("title") or url)[:240],
            "snippet": str(item.get("snippet") or "")[:600],
            "url": url,
        })
    media = []
    for item in value.get("media", [])[:MAX_MEDIA]:
        if not isinstance(item, dict):
            continue
        url = _safe_public_url(item.get("url"))
        if not url:
            continue
        media.append({
            "id": str(item.get("id") or f"media-{len(media) + 1}"),
            "kind": "video" if item.get("kind") == "video" else "image",
            "url": url,
            "source_id": str(item.get("source_id") or ""),
            "source_url": _safe_public_url(item.get("source_url")),
            "source_title": str(item.get("source_title") or "")[:240],
            "alt": str(item.get("alt") or item.get("caption") or "相关媒体")[:180],
            "caption": str(item.get("caption") or item.get("alt") or "相关媒体")[:180],
            "attribution": str(item.get("attribution") or "")[:240],
            "generated": False,
        })
    safe_meta = {
        "schema_version": int(value.get("schema_version") or 3),
        "query": str(value.get("query") or "")[:300],
        "results": results,
        "images": [item["url"] for item in media if item["kind"] == "image"],
        "media": media,
        "sources_used": list(dict.fromkeys(item["source"] for item in results)),
        "total": len(results),
    }
    return safe_meta


def create_rich_search_tool(
    structured_tool: Any,
    search_tool: Any,
    browser_tool: Any = None,
    evaluate_tool: Any = None,
    vision_model: Any = None,
    progress: ProgressCallback | None = None,
):
    async def rich_search(query: str, maxResults: int = MAX_RESULTS, site: str | None = None) -> str:
        del maxResults, site
        payload = await build_rich_search_payload(
            query,
            search_tool,
            browser_tool,
            evaluate_tool,
            vision_model,
            progress,
        )
        return json.dumps(payload, ensure_ascii=False)

    return structured_tool.from_function(
        coroutine=rich_search,
        name="web_search",
        description=(
            "搜索网页、公众号、百科等来源，并返回带来源绑定的图片、视频和正文摘要。"
            "回答时先排除广告和低相关候选；图片只使用 media 中给出的原始 URL，按语义相关性穿插到对应段落。"
        ),
    )
