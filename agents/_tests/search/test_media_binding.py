from __future__ import annotations

import unittest

from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)
from agents._domain.search.media_binding import bind_reviewed_media


def source(source_id: str = "source-1", url: str = "https://a.test/1") -> SearchSource:
    return SearchSource(
        id=source_id,
        title=f"来源 {source_id}",
        url=url,
        snippet="已核验事实",
    )


def media(
    media_id: str = "media-1",
    *,
    source_id: str = "source-1",
    source_url: str = "https://a.test/1",
    reviewed: bool = True,
    source_bound_fallback: bool = False,
) -> ReviewedMedia:
    return ReviewedMedia(
        id=media_id,
        url=f"https://img.test/{media_id}.jpg",
        source_id=source_id,
        source_url=source_url,
        vision_reviewed=reviewed,
        source_bound_fallback=source_bound_fallback,
    )


class MediaBindingTests(unittest.TestCase):
    def test_media_requires_review_and_exact_source_url(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(source_url="https://a.test/other"),),
        )

        self.assertEqual(bind_reviewed_media(evidence), ())

    def test_missing_source_id_fails_closed(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(source_id="source-missing"),),
        )

        self.assertEqual(bind_reviewed_media(evidence), ())

    def test_unreviewed_media_fails_closed(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(reviewed=False),),
        )

        self.assertEqual(bind_reviewed_media(evidence), ())

    def test_exact_reviewed_media_binds_to_its_source(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(),),
        )

        bindings = bind_reviewed_media(evidence)

        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].source.id, "source-1")
        self.assertEqual(bindings[0].media.id, "media-1")
        self.assertEqual(bindings[0].source_id, "source-1")

    def test_exact_source_bound_fallback_binds_without_vision_review(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(
                reviewed=False,
                source_bound_fallback=True,
            ),),
        )

        bindings = bind_reviewed_media(evidence)

        self.assertEqual(len(bindings), 1)
        self.assertTrue(bindings[0].media.source_bound_fallback)

    def test_source_bound_fallback_still_requires_exact_source_url(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(source(),),
            media=(media(
                reviewed=False,
                source_bound_fallback=True,
                source_url="https://a.test/other",
            ),),
        )

        self.assertEqual(bind_reviewed_media(evidence), ())

    def test_binding_order_is_media_order(self):
        evidence = SearchEvidence(
            query="深圳天气",
            sources=(
                source("source-1", "https://a.test/1"),
                source("source-2", "https://a.test/2"),
            ),
            media=(
                media(
                    "media-2",
                    source_id="source-2",
                    source_url="https://a.test/2",
                ),
                media(
                    "media-1",
                    source_id="source-1",
                    source_url="https://a.test/1",
                ),
            ),
        )

        bindings = bind_reviewed_media(evidence)

        self.assertEqual(
            [binding.media.id for binding in bindings],
            ["media-2", "media-1"],
        )


if __name__ == "__main__":
    unittest.main()
