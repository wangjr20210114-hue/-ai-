from __future__ import annotations

import json
import unittest

from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)
from agents._presenters.chat_stream import ChatStreamPresenter


def decode(frame: bytes) -> tuple[str, dict]:
    text = frame.decode("utf-8")
    event = next(
        line.removeprefix("event:").strip()
        for line in text.splitlines()
        if line.startswith("event:")
    )
    data = next(
        line.removeprefix("data:").strip()
        for line in text.splitlines()
        if line.startswith("data:")
    )
    return event, json.loads(data)


def evidence() -> SearchEvidence:
    return SearchEvidence(
        query="深圳天气",
        sources=(
            SearchSource(
                id="source-1",
                title="深圳气象局",
                url="https://weather.test/shenzhen",
                snippet="今天晴",
            ),
        ),
        media=(
            ReviewedMedia(
                id="media-1",
                url="https://img.test/weather.jpg",
                source_id="source-1",
                source_url="https://weather.test/shenzhen",
                vision_reviewed=True,
            ),
        ),
        total=1,
    )


class ChatStreamPresenterTests(unittest.TestCase):
    def test_stage_exposes_progress_without_hidden_reasoning(self):
        frame = ChatStreamPresenter().stage(
            "retrieval",
            {
                "status": "active",
                "activity": "web_search",
                "provider": "SearchPro",
                "source_count": 0,
                "chain_of_thought": "private",
            },
            132,
        )

        event, payload = decode(frame)

        self.assertEqual(event, "stage")
        self.assertEqual(payload["type"], "progress_event")
        self.assertEqual(payload["payload"]["provider"], "SearchPro")
        self.assertEqual(payload["payload"]["elapsed_ms"], 132)
        serialized = frame.decode("utf-8")
        self.assertNotIn("chain_of_thought", serialized)
        self.assertNotIn("reasoning_content", serialized)

    def test_utf8_tokens_remain_public_protocol_compatible(self):
        frame = ChatStreamPresenter().token("你好，深圳")

        event, payload = decode(frame)

        self.assertEqual(event, "token")
        self.assertEqual(payload, {"type": "ai_response", "content": "你好，深圳"})
        self.assertIn("你好，深圳", frame.decode("utf-8"))

    def test_sources_and_media_use_existing_frontend_payload_shape(self):
        presenter = ChatStreamPresenter()

        source_event, source_payload = decode(presenter.sources(evidence()))
        media_event, media_payload = decode(presenter.media(evidence()))

        self.assertEqual(source_event, "sources")
        self.assertEqual(source_payload["type"], "search_results")
        self.assertEqual(source_payload["payload"]["results"][0]["id"], "source-1")
        self.assertEqual(media_event, "media")
        self.assertEqual(media_payload["type"], "search_media")
        self.assertEqual(media_payload["payload"]["media"][0]["id"], "media-1")

    def test_contract_order_and_safe_terminal_error(self):
        presenter = ChatStreamPresenter()
        frames = [
            presenter.stage("planning", {"status": "completed"}, 1),
            presenter.sources(evidence()),
            presenter.token("结论"),
            presenter.media(evidence()),
            presenter.done("turn-1"),
        ]

        self.assertEqual(
            [decode(frame)[0] for frame in frames],
            ["stage", "sources", "token", "media", "done"],
        )
        event, payload = decode(
            presenter.error("provider_error", "搜索服务暂时不可用"),
        )
        self.assertEqual(event, "error")
        self.assertEqual(payload["code"], "provider_error")
        self.assertNotIn("exception", json.dumps(payload))
        self.assertNotIn("traceback", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
