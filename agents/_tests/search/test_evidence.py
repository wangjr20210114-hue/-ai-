from __future__ import annotations

import unittest

from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)


class SearchEvidenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
