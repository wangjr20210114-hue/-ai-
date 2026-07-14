import asyncio
import json
import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "agents" / "chat" / "_rich_search.py"
_SPEC = importlib.util.spec_from_file_location("edgeone_rich_search", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

build_rich_search_payload = _MODULE.build_rich_search_payload
extract_page_content = _MODULE.extract_page_content
extract_evaluated_page = _MODULE.extract_evaluated_page
normalize_search_results = _MODULE.normalize_search_results
search_meta_from_tool_content = _MODULE.search_meta_from_tool_content
should_search = _MODULE.should_search
review_images_with_vision = _MODULE.review_images_with_vision
select_media = _MODULE.select_media


class _FakeTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return self.result


class _FakeVisionModel:
    class _Response:
        content = json.dumps([
            {"id": "media-1", "keep": True, "ad": False},
            {"id": "media-2", "keep": False, "ad": True},
        ])

    async def ainvoke(self, _messages, config=None):
        self.config = config
        return self._Response()


class _ConcurrentVisionModel:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def ainvoke(self, messages, config=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.02)
            content = messages[0].content
            ids = []
            for item in content:
                text = item.get("text", "") if isinstance(item, dict) else ""
                if text.startswith("候选 "):
                    ids.append(text.split("；", 1)[0].removeprefix("候选 "))
            response = type("Response", (), {})()
            response.content = json.dumps([
                {"id": media_id, "keep": True, "ad": False}
                for media_id in ids
            ])
            return response
        finally:
            self.active -= 1


class _BrokenVisionModel:
    async def ainvoke(self, _messages, config=None):
        raise RuntimeError("image unavailable")


class EdgeOneRichSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_substantive_travel_question_triggers_search(self) -> None:
        self.assertTrue(should_search("北京去哪里玩比较好"))
        self.assertFalse(should_search("你好"))
        self.assertFalse(should_search("请帮我生成图片"))

    def test_search_results_are_normalized_and_private_urls_are_dropped(self) -> None:
        results = normalize_search_results(json.dumps([
            {"title": "北京文旅", "href": "https://example.com/beijing", "snippet": "景点推荐", "site": "网页"},
            {"title": "内网", "href": "http://127.0.0.1/secret", "snippet": "不应暴露"},
        ], ensure_ascii=False))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "source-1")
        self.assertEqual(results[0]["url"], "https://example.com/beijing")

    def test_page_media_is_source_bound_and_obvious_ads_are_filtered(self) -> None:
        source = {
            "id": "source-1",
            "source": "web",
            "title": "北京景点",
            "snippet": "",
            "url": "https://example.com/article",
        }
        html = """
        <html><head><meta property="og:image" content="/hero.jpg"></head>
        <body><p>故宫与景山公园适合安排在同一天游览。</p>
        <img src="/advert-banner.jpg" alt="广告">
        <video src="https://video.example.com/beijing.mp4" title="北京旅行视频"></video>
        </body></html>
        """
        excerpt, media = extract_page_content({"content": html}, source)
        self.assertIn("故宫", excerpt)
        self.assertEqual([item["kind"] for item in media], ["image", "video"])
        self.assertTrue(all(item["source_id"] == "source-1" for item in media))

    async def test_rich_payload_contains_sources_images_and_page_excerpt(self) -> None:
        search = _FakeTool(json.dumps([
            {"title": "北京景点", "href": "https://example.com/article", "snippet": "旅游推荐", "site": "网页"},
        ], ensure_ascii=False))
        browser = _FakeTool(json.dumps({
            "url": "https://example.com/article",
            "content": '<article>故宫旅游信息<img src="/palace.jpg" alt="北京故宫"></article>',
        }, ensure_ascii=False))
        progress = []

        async def capture(event):
            progress.append(event)

        payload = await build_rich_search_payload(
            "北京去哪里玩比较好", search, browser,
            vision_model=_FakeVisionModel(), progress=capture,
        )
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["media"][0]["url"], "https://example.com/palace.jpg")
        self.assertIn("故宫旅游信息", payload["results"][0]["content_excerpt"])
        safe_meta = search_meta_from_tool_content(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(safe_meta["media"][0]["source_id"], "source-1")
        self.assertNotIn("content_excerpt", safe_meta["results"][0])
        self.assertIn("fetching_page", [item["stage"] for item in progress])
        self.assertEqual(progress[-1]["stage"], "composing")

    async def test_vision_is_a_filter_and_alt_comes_from_page_context(self) -> None:
        media = [
            {
                "id": "media-1", "kind": "image", "url": "https://cdn.example.com/palace.jpg",
                "caption": "文章配图", "source_title": "北京故宫游览指南",
            },
            {
                "id": "media-2", "kind": "image", "url": "https://cdn.example.com/ad.jpg",
                "caption": "暑期优惠", "source_title": "广告",
            },
        ]
        kept = await review_images_with_vision(
            "北京去哪里玩比较好", media, _FakeVisionModel()
        )
        self.assertEqual([item["url"] for item in kept], ["https://cdn.example.com/palace.jpg"])
        self.assertEqual(
            kept[0]["alt"],
            "北京故宫游览指南中与“北京去哪里玩比较好”相关的图片",
        )

    async def test_vision_batches_run_concurrently(self) -> None:
        model = _ConcurrentVisionModel()
        media = [
            {
                "id": f"media-{index}",
                "kind": "image",
                "url": f"https://cdn.example.com/{index}.jpg",
                "caption": f"故宫图片 {index}",
                "source_title": "故宫资料",
            }
            for index in range(1, 10)
        ]

        kept = await review_images_with_vision("故宫", media, model)

        self.assertEqual(len(kept), 9)
        self.assertGreater(model.max_active, 1)
        self.assertLessEqual(model.max_active, _MODULE.VISION_MAX_CONCURRENCY)

    async def test_images_fail_closed_without_a_successful_visual_review(self) -> None:
        media = [{
            "id": "media-1", "kind": "image", "url": "https://cdn.example.com/palace.jpg",
            "caption": "故宫高清图片", "source_title": "故宫资料",
        }]

        self.assertEqual(await review_images_with_vision("故宫", media, None), [])
        self.assertEqual(await review_images_with_vision("故宫", media, _BrokenVisionModel()), [])

    def test_preselection_does_not_use_keywords_to_rank_images(self) -> None:
        candidates = [
            {"kind": "image", "url": "https://cdn.example.com/first.jpg", "source_id": "s1", "caption": "普通配图"},
            {"kind": "image", "url": "https://cdn.example.com/palace.jpg", "source_id": "s2", "caption": "故宫"},
        ]

        selected = select_media("故宫", candidates)

        self.assertEqual([item["url"] for item in selected], [
            "https://cdn.example.com/first.jpg",
            "https://cdn.example.com/palace.jpg",
        ])

    def test_browser_evaluation_media_is_filtered_and_source_bound(self) -> None:
        source = {"id": "source-1", "title": "北京景点", "url": "https://example.com/article"}
        excerpt, media = extract_evaluated_page({"data": json.dumps({
            "text": "故宫和景山公园游玩建议",
            "media": [
                {"kind": "image", "url": "/palace.jpg", "caption": "北京故宫", "width": 1200, "height": 800},
                {"kind": "image", "url": "/logo.png", "caption": "站点 logo", "width": 400, "height": 200},
            ],
        }, ensure_ascii=False)}, source)
        self.assertIn("故宫", excerpt)
        self.assertEqual([item["url"] for item in media], ["https://example.com/palace.jpg"])
        self.assertEqual(media[0]["source_id"], "source-1")


if __name__ == "__main__":
    unittest.main()
