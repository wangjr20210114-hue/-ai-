package com.floris.android.core.chat

import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.SearchSource
import com.floris.android.core.network.sse.ChatEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SearchProjectionTest {
    private val result = SearchMeta(
        query = "AI progress",
        results = listOf(SearchSource(id = "s1", title = "Source", url = "https://example.com/a")),
        total = 1,
        media_pending = true,
        timings_ms = mapOf("search" to 1_250.0),
    )
    private val media = SearchMeta(
        media = listOf(
            MediaItem(
                id = "m1",
                url = "https://cdn.example.com/a.jpg",
                source_id = "s1",
                source_url = "https://example.com/a",
                vision_reviewed = true,
            ),
        ),
        media_pending = false,
        timings_ms = mapOf("vision" to 420.0),
    )

    @Test
    fun `media then results retains both projections`() {
        val message = assistant()
            .reduce(ChatEvent.SearchMedia(media))
            .reduce(ChatEvent.SearchResults(result))

        assertEquals(listOf("s1"), message.searchResults?.results?.map { it.id })
        assertEquals(listOf("m1"), message.searchResults?.media?.map { it.id })
        assertEquals(1_250.0, message.searchResults?.timings_ms?.get("search"))
        assertEquals(420.0, message.searchResults?.timings_ms?.get("vision"))
        assertFalse(message.searchResults?.media_pending ?: true)
    }

    @Test
    fun `results then media retains both projections`() {
        val message = assistant()
            .reduce(ChatEvent.SearchResults(result))
            .reduce(ChatEvent.SearchMedia(media))

        assertEquals("AI progress", message.searchResults?.query)
        assertEquals(1, message.searchResults?.results?.size)
        assertEquals(1, message.searchResults?.media?.size)
        assertFalse(message.searchResults?.media_pending ?: true)
    }

    @Test
    fun `standalone stage timing supplies final search duration`() {
        val message = assistant().reduce(
            ChatEvent.StageTiming(mapOf("planning" to 12.0, "search" to 1_450.0)),
        )

        assertEquals(1_450.0, message.stageTimingsMs["search"])
        assertEquals("1.5", message.searchDurationSeconds)
    }

    private fun assistant() = ChatMessageUi(id = "a1", role = ChatMessageUi.Role.AI)
}
