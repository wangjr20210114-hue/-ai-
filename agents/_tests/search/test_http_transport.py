from __future__ import annotations

import unittest

from agents._infrastructure.providers import http_transport


class HttpTransportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await http_transport.close_http_transport()

    async def asyncTearDown(self) -> None:
        await http_transport.close_http_transport()

    async def test_shared_client_is_reused_until_explicit_shutdown(self):
        first = http_transport._client()
        second = http_transport._client()

        self.assertIs(first, second)
        self.assertFalse(first.is_closed)

        await http_transport.close_http_transport()

        self.assertTrue(first.is_closed)
        replacement = http_transport._client()
        self.assertIsNot(first, replacement)
        self.assertFalse(replacement.is_closed)


if __name__ == "__main__":
    unittest.main()
