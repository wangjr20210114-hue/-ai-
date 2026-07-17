from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from services.rich_media_service import build_media_assets, build_source_references
from services.search_service import prepare_search_prompt
from services.search_system import _select_ranked_results


class RichSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_is_deduplicated_and_bound_to_source(self) -> None:
        results = [
            {
                "source": "web",
                "title": "官方架构说明",
                "snippet": "结构化输出",
                "url": "https://example.com/article",
            }
        ]
        sources = build_source_references(results)
        candidates = [
            {
                "url": "https://cdn.example.com/diagram.png",
                "source_url": "https://example.com/article",
                "source_title": "官方架构说明",
            },
            {
                "url": "https://cdn.example.com/diagram.png",
                "source_url": "https://example.com/article",
                "source_title": "重复项",
            },
        ]
        with patch(
            "services.rich_media_service.validate_public_url",
            new=AsyncMock(side_effect=lambda url: url),
        ):
            assets = await build_media_assets(
                candidates,
                [{"url": candidates[0]["url"], "description": "主动式 Agent 架构图"}],
                sources,
            )

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].id, "media-1")
        self.assertEqual(assets[0].source_id, "source-1")
        self.assertEqual(assets[0].caption, "主动式 Agent 架构图")

    async def test_invalid_media_url_is_rejected(self) -> None:
        with patch(
            "services.rich_media_service.validate_public_url",
            new=AsyncMock(side_effect=ValueError("private address")),
        ):
            assets = await build_media_assets(
                [{"url": "http://127.0.0.1/private.png"}],
                [],
                [],
            )
        self.assertEqual(assets, [])

    def test_prompt_exposes_ids_instead_of_image_urls(self) -> None:
        results = [
            {
                "source": "web",
                "title": "可信来源",
                "snippet": "回答依据",
                "url": "https://example.com/source",
            }
        ]
        sources = [item.model_dump() for item in build_source_references(results)]
        media = [
            {
                "id": "media-1",
                "kind": "image",
                "url": "https://cdn.example.com/private-render-url.png",
                "source_id": "source-1",
                "source_url": "https://example.com/source",
                "source_title": "可信来源",
                "alt": "说明图",
                "caption": "结构说明图",
                "generated": False,
            }
        ]
        request, metadata = prepare_search_prompt(
            "什么是主动式 Agent",
            results,
            [media[0]["url"]],
            ["web"],
            media=media,
            source_references=sources,
        )
        user_prompt = request.messages[1]["content"]
        self.assertIn("media-1", user_prompt)
        self.assertNotIn(media[0]["url"], user_prompt)
        self.assertEqual(metadata["media"][0]["source_id"], "source-1")

    def test_result_selection_is_deterministic_and_diverse(self) -> None:
        ranked = [
            (9.0 - index / 10, {"source": "web" if index < 5 else "baike", "title": str(index)})
            for index in range(10)
        ]
        first = _select_ranked_results(ranked, "basic")
        second = _select_ranked_results(ranked, "basic")
        self.assertEqual(first, second)
        self.assertIn("baike", {item["source"] for item in first})


if __name__ == "__main__":
    unittest.main()
