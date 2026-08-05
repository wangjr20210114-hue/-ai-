package com.floris.android.core.chat

import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.SearchSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceBoundMediaTest {
    private val source = SearchSource(
        id = "source-1",
        title = "AI update",
        url = "https://news.example/ai",
    )
    private val reviewed = MediaItem(
        id = "media-1",
        url = "https://cdn.example/ai.jpg",
        source_id = source.id,
        source_url = source.url,
        vision_reviewed = true,
    )

    @Test
    fun placesReviewedImageAfterExactCitation() {
        val segments = sourceBoundSegments(
            "第一段 [来源](${source.url})。\n\n第二段。",
            SearchMeta(results = listOf(source), media = listOf(reviewed)),
        )

        assertEquals(2, segments.size)
        assertEquals(listOf(reviewed), segments.first().media)
        assertTrue(segments.last().markdown.contains("第二段"))
    }

    @Test
    fun neverFallsBackWhenAnswerDoesNotCiteSource() {
        val segments = sourceBoundSegments(
            "这里只写了综合结论。",
            SearchMeta(results = listOf(source), media = listOf(reviewed)),
        )

        assertEquals(1, segments.size)
        assertTrue(segments.single().media.isEmpty())
    }

    @Test
    fun rejectsUnreviewedOrMismatchedMedia() {
        val content = "结论 [来源](${source.url})。"
        val rejected = listOf(
            reviewed.copy(vision_reviewed = false),
            reviewed.copy(id = "media-2", source_id = "other"),
            reviewed.copy(id = "media-3", source_url = "https://news.example/other"),
        )

        val segments = sourceBoundSegments(
            content,
            SearchMeta(results = listOf(source), media = rejected),
        )
        assertTrue(segments.single().media.isEmpty())
    }

    @Test
    fun stripsLegacyPlaceholdersWithoutUsingThemForPlacement() {
        val segments = sourceBoundSegments(
            "正文\n\n[[YUANBAO_MEDIA: 0]]\n\n结束",
            SearchMeta(results = listOf(source), media = listOf(reviewed)),
        )

        assertEquals(1, segments.size)
        assertTrue("legacy placeholder remains", !segments.single().markdown.contains("YUANBAO"))
        assertTrue(segments.single().media.isEmpty())
    }
}
