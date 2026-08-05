package com.floris.android.core.chat

import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.SearchMeta
import java.net.URI

data class SourceBoundSegment(
    val markdown: String,
    val media: List<MediaItem> = emptyList(),
)

private val legacyMediaMarker = Regex(
    "\\[\\[YUANBAO_MEDIA(?:\\s*:\\s*\\d+)?]]|\\[\\[YUANBAO_M[^\\r\\n]*",
    RegexOption.IGNORE_CASE,
)

/**
 * Places only vision-reviewed media after a paragraph that explicitly cites
 * the uniquely matching source URL. Missing citations intentionally produce
 * no image: there is no cover-image or end-of-answer fallback.
 */
fun sourceBoundSegments(content: String, search: SearchMeta?): List<SourceBoundSegment> {
    val cleaned = content.replace(legacyMediaMarker, "")
    if (cleaned.isEmpty() || search == null) return listOf(SourceBoundSegment(cleaned))

    val sourceCounts = search.results.groupingBy { it.id }.eachCount()
    val sources = search.results.associateBy { it.id }
    val eligible = search.media
        .asSequence()
        .filter { it.vision_reviewed == true && it.id.isNotBlank() && safeRemoteUrl(it.url) }
        .filter { item ->
            val sourceId = item.source_id ?: return@filter false
            val source = sources[sourceId]
            sourceCounts[sourceId] == 1 && source != null &&
                safeRemoteUrl(source.url) && item.source_url == source.url
        }
        .distinctBy { it.id }
        .toList()
    if (eligible.isEmpty()) return listOf(SourceBoundSegment(cleaned))

    val placements = linkedMapOf<Int, MutableList<MediaItem>>()
    eligible.forEach { item ->
        val source = sources[item.source_id] ?: return@forEach
        val citation = "](${source.url})"
        val citationIndex = cleaned.indexOf(citation)
        if (citationIndex < 0) return@forEach
        val paragraphEnd = cleaned.indexOf("\n\n", citationIndex + citation.length)
            .let { if (it < 0) cleaned.length else it }
        placements.getOrPut(paragraphEnd) { mutableListOf() }.add(item)
    }
    if (placements.isEmpty()) return listOf(SourceBoundSegment(cleaned))

    val output = mutableListOf<SourceBoundSegment>()
    var cursor = 0
    placements.toSortedMap().forEach { (end, media) ->
        if (end > cursor) output += SourceBoundSegment(cleaned.substring(cursor, end), media)
        cursor = end
    }
    if (cursor < cleaned.length) output += SourceBoundSegment(cleaned.substring(cursor))
    return output.ifEmpty { listOf(SourceBoundSegment(cleaned)) }
}

private fun safeRemoteUrl(value: String): Boolean = runCatching {
    val uri = URI(value)
    (uri.scheme == "https" || uri.scheme == "http") &&
        uri.host != null && uri.userInfo == null
}.getOrDefault(false)
