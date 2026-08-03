from __future__ import annotations

import unittest

from tools.search_critical_path import run_fake_critical_path


class SearchCriticalPathContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_compatible_answer_waits_for_complete_rich_evidence(self):
        metrics = await run_fake_critical_path(1)

        self.assertEqual(metrics.provider_requests, 1)
        self.assertIn("rich_search", metrics.graph_tool_names)
        self.assertGreater(metrics.first_token_ms, metrics.media_complete_ms)
        self.assertGreater(metrics.first_token_ms, 1_500)
        self.assertLess(
            metrics.event_order.index("media"),
            metrics.event_order.index("sources"),
        )
        self.assertLess(
            metrics.event_order.index("sources"),
            metrics.event_order.index("token"),
        )


if __name__ == "__main__":
    unittest.main()
