from __future__ import annotations

import unittest

from tools.search_critical_path import run_fake_critical_path


class SearchCriticalPathContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_token_does_not_wait_for_progressive_media(self):
        metrics = await run_fake_critical_path(1)

        self.assertEqual(metrics.provider_requests, 1)
        self.assertNotIn("rich_search", metrics.answer_tool_names)
        self.assertLess(metrics.first_token_ms, 500)
        self.assertGreater(metrics.media_complete_ms, metrics.first_token_ms)
        self.assertLess(
            metrics.event_order.index("sources"),
            metrics.event_order.index("token"),
        )
        self.assertLess(
            metrics.event_order.index("token"),
            metrics.event_order.index("media"),
        )


if __name__ == "__main__":
    unittest.main()

