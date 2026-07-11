from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

import httpx

from services.safe_http import (
    ResponseLimitError,
    UnsafeUrlError,
    request_public_url,
    validate_public_url,
)


PUBLIC_DNS = [
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
]


class SafeHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_and_non_http_urls_are_rejected(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            await validate_public_url("file:///etc/passwd")
        with self.assertRaises(UnsafeUrlError):
            await validate_public_url("http://127.0.0.1/admin")
        with self.assertRaises(UnsafeUrlError):
            await validate_public_url("http://169.254.169.254/latest/meta-data")

    async def test_public_html_is_fetched_with_size_and_type_policy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "example.test")
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html>ok</html>")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("services.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
            response = await request_public_url(
                "GET",
                "https://example.test/page",
                client=client,
                allowed_content_types=("text/html",),
                max_bytes=1024,
            )
        self.assertEqual(response.text, "<html>ok</html>")
        await client.aclose()

    async def test_redirect_target_is_revalidated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("services.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
            with self.assertRaises(UnsafeUrlError):
                await request_public_url("GET", "https://example.test/start", client=client)
        await client.aclose()

    async def test_response_size_and_content_type_are_enforced(self) -> None:
        def big_handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 20)

        client = httpx.AsyncClient(transport=httpx.MockTransport(big_handler))
        with patch("services.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
            with self.assertRaises(ResponseLimitError):
                await request_public_url(
                    "GET",
                    "https://example.test/big",
                    client=client,
                    allowed_content_types=("text/html",),
                    max_bytes=10,
                )
        await client.aclose()


if __name__ == "__main__":
    unittest.main()
