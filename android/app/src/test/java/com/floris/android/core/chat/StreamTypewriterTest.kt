package com.floris.android.core.chat

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StreamTypewriterTest {

    /** 核心保证：不论节奏怎么切，最终文本必须与后端下发的完全一致。 */
    @Test
    fun `preserves every character across frames`() {
        val typewriter = StreamTypewriter()
        val chunks = listOf("这是第一段较长的回答文本，", "接着是第二段，", "最后一段。")
        chunks.forEach(typewriter::offer)

        val rendered = StringBuilder()
        repeat(200) {
            rendered.append(typewriter.nextFrame())
        }
        typewriter.finish()
        rendered.append(typewriter.nextFrame())

        assertEquals(chunks.joinToString(""), rendered.toString())
    }

    /** 一次性收到大块文本时，必须拆成多帧渲染，而不是一帧全吐。 */
    @Test
    fun `splits a large chunk into multiple frames`() {
        val typewriter = StreamTypewriter()
        typewriter.offer("字".repeat(120))

        val first = typewriter.nextFrame()
        assertTrue("首帧应少于全部内容", first.length < 120)
        assertTrue("首帧应有内容", first.isNotEmpty())
        assertTrue(typewriter.hasPending)
    }

    /** finish() 之后剩余字符一次性放出，不再排队。 */
    @Test
    fun `finish flushes everything at once`() {
        val typewriter = StreamTypewriter()
        typewriter.offer("剩余内容需要立刻补齐")
        typewriter.finish()

        assertEquals("剩余内容需要立刻补齐", typewriter.nextFrame())
        assertFalse(typewriter.hasPending)
        assertEquals("", typewriter.nextFrame())
    }

    /** 空缓冲不产生任何帧，避免无谓重组。 */
    @Test
    fun `empty buffer yields nothing`() {
        val typewriter = StreamTypewriter()
        assertEquals("", typewriter.nextFrame())
        typewriter.offer("")
        assertEquals("", typewriter.nextFrame())
    }

    /** reset 对应 ai_response_reset：缓冲清空并可继续接收。 */
    @Test
    fun `reset clears pending text`() {
        val typewriter = StreamTypewriter()
        typewriter.offer("要被丢弃的草稿")
        typewriter.reset()

        assertFalse(typewriter.hasPending)
        typewriter.offer("新的正文")
        typewriter.finish()
        assertEquals("新的正文", typewriter.nextFrame())
    }

    /** 积压越多，单帧吐出的字符越多，保证不会落后于后端。 */
    @Test
    fun `drains faster when backlog grows`() {
        val small = StreamTypewriter()
        small.offer("字".repeat(20))
        val large = StreamTypewriter()
        large.offer("字".repeat(400))

        assertTrue(large.nextFrame().length > small.nextFrame().length)
    }
}
