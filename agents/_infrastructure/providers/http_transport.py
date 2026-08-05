"""Small async HTTP transport shared by read-only provider adapters.

The transport deliberately lives below SearchPro and page-media adapters.  A
single ``httpx.AsyncClient`` per running event loop provides keep-alive
connection reuse while ``asyncio.wait_for`` gives callers one cancellable
deadline.  No provider credentials or tenant state are stored in the client.
"""

from __future__ import annotations

import asyncio
import io
import json
import urllib.error
import weakref
from collections.abc import Mapping
from typing import Any

import httpx


_CLIENTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def _client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            follow_redirects=True,
            trust_env=False,
            limits=httpx.Limits(
                max_connections=16,
                max_keepalive_connections=8,
                keepalive_expiry=30.0,
            ),
        )
        _CLIENTS[loop] = client
    return client


async def close_http_transport() -> None:
    """Close the current loop's shared client during worker/test shutdown.

    Makers keeps a warm event loop for normal requests, so callers should not
    use this between requests.  It is an explicit lifecycle hook for bounded
    workers, local benchmarks and graceful shutdown; keeping it explicit avoids
    defeating connection reuse on every chat turn.
    """
    loop = asyncio.get_running_loop()
    client = _CLIENTS.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()


def _timeout(value: float) -> httpx.Timeout:
    bounded = max(1.0, min(60.0, float(value)))
    return httpx.Timeout(
        timeout=bounded,
        connect=min(8.0, bounded),
        pool=min(8.0, bounded),
    )


def _http_error(url: str, response: httpx.Response, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url,
        int(response.status_code),
        str(response.reason_phrase or "provider request failed"),
        response.headers,
        io.BytesIO(body),
    )


async def request_json(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    *,
    timeout: float,
    max_bytes: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    """POST JSON with bounded body size and cancellation propagation."""
    deadline = max(1.0, min(60.0, float(timeout))) + 0.25

    async def send() -> tuple[httpx.Response, bytes]:
        response = await _client().post(
            url,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=dict(headers),
            timeout=_timeout(timeout),
        )
        return response, await response.aread()

    try:
        response, body = await asyncio.wait_for(send(), timeout=deadline)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        raise
    except httpx.TimeoutException as exc:
        raise asyncio.TimeoutError() from exc
    except httpx.RequestError as exc:
        raise ConnectionError(str(exc)) from exc
    if len(body) > max_bytes:
        raise ValueError("provider response body is too large")
    if not 200 <= int(response.status_code) < 300:
        raise _http_error(url, response, body)
    decoded = json.loads(body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("provider JSON response must be an object")
    return decoded


async def request_page(
    url: str,
    headers: Mapping[str, str],
    *,
    timeout: float,
    max_bytes: int,
) -> tuple[str, Mapping[str, str], bytes]:
    """GET a bounded public page, retaining final URL and response headers."""
    deadline = max(1.0, min(60.0, float(timeout))) + 0.25

    async def fetch() -> tuple[str, Mapping[str, str], bytes]:
        async with _client().stream(
            "GET",
            url,
            headers=dict(headers),
            timeout=_timeout(timeout),
        ) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError("page response body is too large")
            raw = bytes(body)
            final_url = str(response.url)
            response_headers = response.headers
            if not 200 <= int(response.status_code) < 300:
                raise _http_error(url, response, raw)
            return final_url, response_headers, raw

    try:
        return await asyncio.wait_for(fetch(), timeout=deadline)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        raise
    except httpx.TimeoutException as exc:
        raise asyncio.TimeoutError() from exc
    except httpx.RequestError as exc:
        raise ConnectionError(str(exc)) from exc
