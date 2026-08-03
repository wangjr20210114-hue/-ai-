"""Bounded public-page media provider; not an Agent route."""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from html import unescape
from html.parser import HTMLParser

from .http_transport import request_page


MAX_HTML_BYTES = 5 * 1024 * 1024


def _response_charset(headers) -> str:
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
    match = re.search(r"charset\s*=\s*['\"]?([\w.-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _public_host(hostname: str) -> None:
    if not hostname:
        raise ValueError("网页 URL 缺少主机名")
    for info in socket.getaddrinfo(hostname, None):
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError("不允许抓取私网、回环或保留地址")


class _ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "meta" and str(values.get("property") or values.get("name") or "").lower() in {"og:image", "twitter:image"}:
            if values.get("content"):
                self.urls.append(values["content"])
        if tag in {"img", "source"}:
            for key in ("src", "data-src", "data-original", "data-lazy-src"):
                if values.get(key):
                    self.urls.append(values[key])
            srcset = values.get("srcset") or values.get("data-srcset") or ""
            for candidate in srcset.split(","):
                if candidate.strip():
                    self.urls.append(candidate.strip().split()[0])


async def _collect(page_url: str, limit: int) -> list[str]:
    parsed = urllib.parse.urlparse(page_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("网页 URL 必须使用 http 或 https")
    _public_host(parsed.hostname or "")
    final_url, headers, body = await request_page(
        page_url,
        {"User-Agent": "Mozilla/5.0 YuanbaoMedia/1.0"},
        timeout=15,
        max_bytes=MAX_HTML_BYTES,
    )
    final = urllib.parse.urlparse(final_url)
    _public_host(final.hostname or "")
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        raise ValueError("目标不是 HTML 网页")
    parser = _ImageParser()
    parser.feed(body.decode(_response_charset(headers), errors="replace"))
    output: list[str] = []
    seen: set[str] = set()
    for candidate in parser.urls:
        url = urllib.parse.urljoin(final_url, candidate.strip())
        item = urllib.parse.urlparse(url)
        if item.scheme not in {"http", "https"} or not item.hostname:
            continue
        normalized = urllib.parse.urlunparse(item._replace(fragment=""))
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


async def collect_page_images(page_url: str, limit: int = 30) -> list[str]:
    return await _collect(page_url, max(1, min(30, int(limit))))


async def _collect_media(page_url: str, limit: int) -> list[dict[str, str]]:
    parsed = urllib.parse.urlparse(page_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("网页 URL 必须使用 http 或 https")
    _public_host(parsed.hostname or "")
    final_url, headers, body = await request_page(
        page_url,
        {"User-Agent": "Mozilla/5.0 YuanbaoMedia/2.0"},
        timeout=15,
        max_bytes=MAX_HTML_BYTES,
    )
    _public_host(urllib.parse.urlparse(final_url).hostname or "")
    if "text/html" not in str(headers.get("content-type") or headers.get("Content-Type") or "").lower():
        return []
    html = body.decode(_response_charset(headers), errors="replace")
    candidates: list[dict[str, str]] = []

    def add(value: str, alt: str = "", context: str = "") -> None:
        url = urllib.parse.urljoin(final_url, unescape(value).strip())
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path.lower()
        # TokenHub vision accepts raster JPG/PNG/WebP, not SVG/GIF/icon assets.
        if not url.startswith(("http://", "https://")) or path.endswith((".svg", ".gif", ".ico")):
            return
        candidates.append({"url": url, "alt": unescape(alt)[:160], "context": unescape(context)[:300]})

    for match in re.finditer(r'<meta[^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', html, re.I):
        add(match.group(1), context="页面主图")
    for match in re.finditer(r'<img\b[^>]*>', html, re.I):
        tag = match.group(0)
        source = re.search(r'(?:src|data-src|data-original|data-lazy-src)=["\']([^"\']+)', tag, re.I)
        if not source:
            continue
        alt_match = re.search(r'alt=["\']([^"\']*)', tag, re.I)
        alt = re.sub(r'<[^>]+>', ' ', alt_match.group(1) if alt_match else '')
        start, end = max(0, match.start() - 220), min(len(html), match.end() + 220)
        context = re.sub(r'<[^>]+>', ' ', html[start:end])
        add(source.group(1), alt=alt, context=re.sub(r'\s+', ' ', context).strip())

    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate["url"] in seen:
            continue
        seen.add(candidate["url"])
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


async def collect_page_media(page_url: str, limit: int = 10) -> list[dict[str, str]]:
    return await _collect_media(page_url, max(1, min(10, int(limit))))
