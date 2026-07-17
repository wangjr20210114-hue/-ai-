"""Restricted HTTP client for URLs discovered from untrusted search results."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import httpx


class UnsafeUrlError(ValueError):
    """The URL can reach a local/private target or violates fetch policy."""


class ResponseLimitError(ValueError):
    """The remote response exceeds configured safety limits."""


@dataclass(frozen=True, slots=True)
class SafeHttpResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return self.content.decode(encoding or "utf-8", errors="replace")


def _is_forbidden_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


async def validate_public_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("只允许 http/https URL")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeUrlError("URL 主机无效或包含凭证")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise UnsafeUrlError("拒绝访问本地主机")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise UnsafeUrlError("URL 域名无法解析") from error
    addresses = {item[4][0].split("%", 1)[0] for item in infos}
    if not addresses:
        raise UnsafeUrlError("URL 没有可用地址")
    for address in addresses:
        try:
            if _is_forbidden_ip(address):
                raise UnsafeUrlError("拒绝访问私有、回环或保留地址")
        except ValueError as error:
            raise UnsafeUrlError("URL DNS 返回无效地址") from error
    return url


async def request_public_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 8.0,
    max_redirects: int = 3,
    max_bytes: int = 2 * 1024 * 1024,
    allowed_content_types: Iterable[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> SafeHttpResponse:
    current = url
    allowed = tuple(item.lower() for item in (allowed_content_types or ()))
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0)),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        for redirect_count in range(max_redirects + 1):
            await validate_public_url(current)
            async with active_client.stream(method.upper(), current, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeUrlError("重定向缺少 Location")
                    if redirect_count >= max_redirects:
                        raise UnsafeUrlError("重定向次数过多")
                    current = urljoin(str(response.url), location)
                    if response.status_code == 303:
                        method = "GET"
                    continue

                content_type = response.headers.get("content-type", "").lower()
                if allowed and not any(content_type.startswith(item) for item in allowed):
                    raise ResponseLimitError(f"不允许的 Content-Type：{content_type or 'unknown'}")
                content_length = response.headers.get("content-length")
                if method.upper() != "HEAD" and content_length and int(content_length) > max_bytes:
                    raise ResponseLimitError("响应超过大小限制")
                body = bytearray()
                if method.upper() != "HEAD":
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise ResponseLimitError("响应超过大小限制")
                return SafeHttpResponse(
                    status_code=response.status_code,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    content=bytes(body),
                    url=str(response.url),
                )
        raise UnsafeUrlError("重定向次数过多")
    finally:
        if owns_client:
            await active_client.aclose()


async def safe_head_or_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 6.0,
) -> SafeHttpResponse:
    response = await request_public_url(
        "HEAD",
        url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        max_bytes=0,
    )
    if response.status_code == 405:
        return await request_public_url(
            "GET",
            url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_bytes=64 * 1024,
        )
    return response
