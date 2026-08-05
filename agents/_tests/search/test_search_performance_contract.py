from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from agents._infrastructure.providers.rich_search import _extract_candidates
from tools.search_critical_path import run_fake_critical_path


class SearchCriticalPathContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_media_budget_accepts_an_empty_source_set(self):
        self.assertEqual(
            await _extract_candidates([], timeout_seconds=0.05),
            [],
        )

    async def test_page_media_budget_keeps_fast_sources_when_another_source_stalls(self):
        results = [{
            "url": "https://fast.example/news",
            "title": "Fast source",
            "provider_images": [],
        }, {
            "url": "https://slow.example/news",
            "title": "Slow source",
            "provider_images": [],
        }]

        async def collect(url, _limit):
            if "slow" in url:
                await asyncio.sleep(1)
            return [{
                "url": f"{url}/hero.jpg",
                "context": "verified editorial image",
                "alt": "editorial image",
            }]

        with patch(
            "agents._infrastructure.providers.rich_search.collect_page_media",
            new=collect,
        ):
            candidates = await _extract_candidates(
                results,
                parallel=True,
                timeout_seconds=0.05,
            )

        self.assertEqual(
            [item["source_url"] for item in candidates],
            ["https://fast.example/news"],
        )

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
