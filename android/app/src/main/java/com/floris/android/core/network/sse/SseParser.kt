package com.floris.android.core.network.sse

/** Result of feeding a text chunk into [SseParser]. */
data class SseSplit(val frames: List<String>, val rest: String)

/**
 * Splits an incremental SSE buffer into complete frames.
 *
 * Frames are separated by a blank line; `data:` lines inside one frame are
 * joined with '\n' (mirrors the Web client's splitSseFrames). The trailing
 * partial frame is returned as [SseSplit.rest] for the next feed.
 */
object SseParser {

    fun split(buffer: String): SseSplit {
        val normalized = buffer.replace("\r\n", "\n")
        val chunks = normalized.split("\n\n")
        val rest = chunks.last()
        val frames = chunks.dropLast(1)
            .map(::extractData)
            .filter { it.isNotEmpty() }
        return SseSplit(frames, rest)
    }

    /** Flush any terminated data lines still held in the rest buffer at EOF. */
    fun flush(rest: String): String? {
        val data = extractData(rest.trim())
        return data.ifEmpty { null }
    }

    private fun extractData(chunk: String): String =
        chunk.split('\n')
            .filter { it.startsWith("data:") }
            .joinToString("\n") { it.substring(5).trimStart() }
            .trim()
}
