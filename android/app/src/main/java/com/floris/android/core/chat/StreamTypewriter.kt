package com.floris.android.core.chat

import kotlin.math.ceil
import kotlin.math.max

/**
 * 流式打字机缓冲。
 *
 * 后端 `ai_response` 事件是按模型分块下发的，一块可能是几十个字，
 * 直接 append 到 UI 上就会出现"一段一段跳出来"的观感。这里把收到的
 * 文本放入缓冲区，由固定节奏的时钟按字符匀速吐出，得到真正连续的
 * 流式效果；同时保证：
 *
 *  - 绝不改写、丢弃或补造任何字符（只改变呈现节奏）；
 *  - 缓冲积压越多，单帧吐出的字符越多，永远不会落后于后端；
 *  - `finish()` 后一次性放出剩余全部字符，终态与后端完全一致。
 */
class StreamTypewriter(
    private val frameMillis: Long = FRAME_MILLIS,
    private val minCharsPerFrame: Int = 1,
    private val targetDrainMillis: Long = 420,
) {
    private val buffer = StringBuilder()
    private var finished = false

    /** 收到一个 SSE 文本分块。 */
    fun offer(chunk: String) {
        if (chunk.isEmpty()) return
        buffer.append(chunk)
    }

    /** 后端流已结束：剩余字符不再排队。 */
    fun finish() {
        finished = true
    }

    val hasPending: Boolean get() = buffer.isNotEmpty()

    /** 取出这一帧应该显示的字符；没有可吐出的内容时返回空串。 */
    fun nextFrame(): String {
        if (buffer.isEmpty()) return ""
        if (finished) {
            val all = buffer.toString()
            buffer.setLength(0)
            return all
        }
        // 让缓冲区在 targetDrainMillis 内排空，积压越多吐字越快。
        val framesToDrain = max(1.0, targetDrainMillis.toDouble() / frameMillis)
        val perFrame = max(
            minCharsPerFrame,
            ceil(buffer.length / framesToDrain).toInt(),
        ).coerceAtMost(buffer.length)
        val slice = buffer.substring(0, perFrame)
        buffer.delete(0, perFrame)
        return slice
    }

    /** 重置（`ai_response_reset` 事件）。 */
    fun reset() {
        buffer.setLength(0)
        finished = false
    }

    companion object {
        /** ~60fps 的一半，足够顺滑且不会过度重组 Compose。 */
        const val FRAME_MILLIS = 32L
    }
}
