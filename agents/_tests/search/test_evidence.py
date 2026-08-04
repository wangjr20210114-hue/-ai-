from __future__ import annotations

import unittest

from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)
from agents._application.search.evidence_presenter import present_search_evidence


class SearchEvidenceTests(unittest.TestCase):
    def test_model_evidence_contains_sources_but_no_generated_answer_or_media_markup(self):
        evidence = SearchEvidence(
            query="Floris 架构",
            sources=(
                SearchSource(
                    id="source-1",
                    title="架构资料",
                    url="https://example.test/architecture",
                    snippet="经过检索的事实",
                    published_at="2026-07-31",
                ),
            ),
            media=(
                ReviewedMedia(
                    id="media-1",
                    url="https://cdn.example.test/architecture.jpg",
                    source_id="source-1",
                    source_url="https://example.test/architecture",
                    vision_reviewed=True,
                    caption="Floris 界面",
                ),
            ),
            total=1,
        )

        model_evidence = present_search_evidence(evidence)

        self.assertIn("[架构资料](https://example.test/architecture)", model_evidence)
        self.assertIn("source-1", model_evidence)
        self.assertIn("source_id=source-1", model_evidence)
        self.assertIn("发布者域=example.test", model_evidence)
        self.assertNotIn("最终回答", model_evidence)
        self.assertNotIn("![", model_evidence)
        self.assertNotIn("MEDIA_SLOT", model_evidence)

    def test_rejects_duplicate_source_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate source id"):
            SearchEvidence(
                query="深圳天气",
                sources=(
                    SearchSource(
                        id="source-1",
                        title="气象局",
                        url="https://a.test/1",
                        snippet="晴",
                    ),
                    SearchSource(
                        id="source-1",
                        title="另一来源",
                        url="https://b.test/1",
                        snippet="多云",
                    ),
                ),
            )

    def test_rejects_empty_source_identity(self):
        with self.assertRaisesRegex(ValueError, "source id"):
            SearchSource(id="", title="气象局", url="https://a.test/1", snippet="晴")
        with self.assertRaisesRegex(ValueError, "source url"):
            SearchSource(id="source-1", title="气象局", url="", snippet="晴")

    def test_serialization_round_trip_preserves_immutable_evidence(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(
                SearchSource(
                    id="source-1",
                    title="气象局",
                    url="https://a.test/1",
                    snippet="晴",
                    published_at="2026-07-31",
                    publisher="Example Publisher",
                    publisher_domain="a.test",
                    relevance_score=0.91,
                ),
            ),
            media=(
                ReviewedMedia(
                    id="media-1",
                    url="https://img.test/1.jpg",
                    source_id="source-1",
                    source_url="https://a.test/1",
                    vision_reviewed=True,
                    caption="深圳天气",
                ),
            ),
            total=1,
            media_pending=False,
        )

        restored = SearchEvidence.from_dict(evidence.to_dict())

        self.assertEqual(restored, evidence)
        self.assertIsInstance(restored.sources, tuple)
        self.assertIsInstance(restored.media, tuple)
        self.assertEqual(restored.sources[0].publisher, "Example Publisher")
        self.assertEqual(restored.sources[0].publisher_domain, "a.test")
        self.assertEqual(restored.sources[0].relevance_score, 0.91)


if __name__ == "__main__":
    unittest.main()
