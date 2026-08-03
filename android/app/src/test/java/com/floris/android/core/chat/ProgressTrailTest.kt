package com.floris.android.core.chat

import com.floris.android.core.model.ProgressComponent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProgressTrailTest {

    private fun step(
        stage: String,
        activity: String = "general",
        status: String = "active",
    ) = ProgressComponent(stage = stage, activity = activity, status = status)

    /** 同一 stage:activity 原地更新，不重复堆叠。 */
    @Test
    fun `updates in place for the same stage and activity`() {
        val trail = emptyList<ProgressComponent>()
            .mergeProgress(step("retrieval", "web_search"))
            .mergeProgress(step("retrieval", "web_search", status = "completed"))

        assertEquals(1, trail.size)
        assertEquals("completed", trail.first().status)
    }

    /** 不同活动各占一行，保持到达顺序。 */
    @Test
    fun `appends distinct activities in order`() {
        val trail = emptyList<ProgressComponent>()
            .mergeProgress(step("planning"))
            .mergeProgress(step("retrieval", "web_search"))
            .mergeProgress(step("verification", "place_search"))

        assertEquals(listOf("planning", "retrieval", "verification"), trail.map { it.stage })
    }

    /** complete/completed 到达时，所有仍在 active 的阶段一并收尾。 */
    @Test
    fun `complete closes every active step`() {
        val trail = emptyList<ProgressComponent>()
            .mergeProgress(step("planning"))
            .mergeProgress(step("retrieval", "web_search"))
            .mergeProgress(step("complete", status = "completed"))

        assertTrue(trail.none { it.status == "active" })
    }

    /** 最多保留 8 条，防止长会话无限增长。 */
    @Test
    fun `keeps at most eight steps`() {
        var trail = emptyList<ProgressComponent>()
        repeat(12) { index -> trail = trail.mergeProgress(step("planning", "activity$index")) }
        assertEquals(8, trail.size)
    }
}
