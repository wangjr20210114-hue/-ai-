from __future__ import annotations

import unittest

from tools.search_critical_path import run_fake_critical_path


class SearchCriticalPathContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_progressive_media_never_blocks_the_model_answer(self):
        metrics = await run_fake_critical_path(1)

        self.assertEqual(metrics.provider_requests, 1)
        self.assertIn("rich_search", metrics.graph_tool_names)
        self.assertLess(metrics.first_token_ms, metrics.media_complete_ms)
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
