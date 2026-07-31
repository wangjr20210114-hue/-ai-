from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from agents._application.search.search_use_case import SearchRequest
from agents._infrastructure.providers.searchpro import SearchProGateway


def request(*, image_limit: int = 0, media_mode: str = "disabled") -> SearchRequest:
    return SearchRequest(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        query="AI 进展",
        image_query="AI 芯片实物",
        depth="standard",
        result_limit=8,
        image_limit=image_limit,
        media_mode=media_mode,
    )


class SearchProGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_distinct_image_query_is_merged_into_one_searchpro_call(self):
        response = {
            "Pages": [
                {
                    "url": "https://example.test/news",
                    "title": "AI 新闻",
                    "passage": "经过检索的事实",
                },
            ],
        }
        calls: list[str] = []

        def json_request(url, payload, headers, timeout):
            calls.append(url)
            return response

        gateway = SearchProGateway(
            {
                "WSA_API_KEY": "test-key",
                "WSA_BASE_URL": "https://search.test",
            },
        )
        with patch("agents._shared.rich_search._json_request", side_effect=json_request):
            execution = await gateway.search(request())

        self.assertEqual(calls, ["https://search.test/SearchPro"])
        self.assertEqual(execution.provider_request_count, 1)
        self.assertEqual(execution.evidence.sources[0].id, "source-1")

    async def test_unreviewed_provider_fallback_is_not_domain_media(self):
        provider_result = {
            "query": "AI 进展",
            "results": [
                {
                    "id": "source-1",
                    "title": "AI 新闻",
                    "url": "https://example.test/news",
                    "snippet": "经过检索的事实",
                },
            ],
            "media": [
                {
                    "id": "media-unreviewed",
                    "url": "https://img.test/unreviewed.jpg",
                    "source_id": "source-1",
                    "source_url": "https://example.test/news",
                    "vision_reviewed": False,
                },
                {
                    "id": "media-reviewed",
                    "url": "https://img.test/reviewed.jpg",
                    "source_id": "source-1",
                    "source_url": "https://example.test/news",
                    "vision_reviewed": True,
                },
            ],
            "total": 1,
            "media_pending": False,
            "search_config": {"provider_request_count": 1},
        }
        gateway = SearchProGateway({"WSA_API_KEY": "test-key"})

        with patch(
            "agents._infrastructure.providers.searchpro.provider_rich_search",
            new=AsyncMock(return_value=provider_result),
        ):
            execution = await gateway.search(
                request(image_limit=2, media_mode="blocking"),
            )

        self.assertEqual(
            [item.id for item in execution.evidence.media],
            ["media-reviewed"],
        )


if __name__ == "__main__":
    unittest.main()
