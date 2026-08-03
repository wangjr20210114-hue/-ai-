package com.floris.android

import com.floris.android.core.network.sse.SseParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SseParserTest {

    @Test
    fun `complete frame is emitted and rest is empty`() {
        val split = SseParser.split("data: {\"type\":\"ping\",\"ts\":1}\n\n")
        assertEquals(listOf("{\"type\":\"ping\",\"ts\":1}"), split.frames)
        assertEquals("", split.rest)
    }

    @Test
    fun `partial frame is retained for the next chunk`() {
        val first = SseParser.split("data: {\"type\":\"ai_re")
        assertEquals(emptyList<String>(), first.frames)

        val second = SseParser.split(first.rest + "sponse\",\"content\":\"hi\"}\n\n")
        assertEquals(listOf("{\"type\":\"ai_response\",\"content\":\"hi\"}"), second.frames)
    }

    @Test
    fun `multiple frames in one chunk are all emitted in order`() {
        val buffer = "data: a\n\ndata: b\n\ndata: c\n\n"
        val split = SseParser.split(buffer)
        assertEquals(listOf("a", "b", "c"), split.frames)
    }

    @Test
    fun `multi-line data inside a frame is joined with newline`() {
        val split = SseParser.split("data: line1\ndata: line2\n\n")
        assertEquals(listOf("line1\nline2"), split.frames)
    }

    @Test
    fun `crlf line endings are normalized`() {
        val split = SseParser.split("data: x\r\n\r\ndata: y\r\n\r\n")
        assertEquals(listOf("x", "y"), split.frames)
    }

    @Test
    fun `comment and event lines are ignored`() {
        val split = SseParser.split(": comment\nevent: message\ndata: payload\n\n")
        assertEquals(listOf("payload"), split.frames)
    }

    @Test
    fun `frame without data lines produces nothing`() {
        val split = SseParser.split("event: ping\n\n")
        assertEquals(emptyList<String>(), split.frames)
    }

    @Test
    fun `flush emits trailing terminated frame at eof`() {
        assertEquals("tail", SseParser.flush("data: tail"))
        assertNull(SseParser.flush(""))
        assertNull(SseParser.flush("event: none"))
    }
}
