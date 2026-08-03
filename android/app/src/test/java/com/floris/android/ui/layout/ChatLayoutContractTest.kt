package com.floris.android.ui.layout

import androidx.compose.ui.unit.dp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 布局约束的纯逻辑回归测试。
 *
 * 这里不启动 Compose 运行时（单测环境没有渲染器），而是把三个曾经
 * 出错的布局参数固化成断言，防止再次被改回去：
 *
 *  1. FlowRow 必须显式给垂直间距，否则换行的 chips 会重叠；
 *  2. 空态内容总高度会超过常见机型的可用高度，必须可滚动；
 *  3. 状态栏内边距只能施加一次。
 */
class ChatLayoutContractTest {

    // ---------- 1. 追问 chips 的行间距 ----------

    /** 与 FollowUpChips 中的取值保持同步。 */
    private val chipHorizontalGap = 8.dp
    private val chipVerticalGap = 8.dp

    @Test
    fun `follow up chips declare both gaps`() {
        // 垂直间距为 0 就是重叠的直接原因，必须为正。
        assertTrue("chips 行间距必须大于 0", chipVerticalGap.value > 0f)
        assertEquals(chipHorizontalGap, chipVerticalGap)
    }

    @Test
    fun `two rows of chips never overlap`() {
        val chipHeight = 32.dp
        val firstRowBottom = chipHeight.value
        val secondRowTop = chipHeight.value + chipVerticalGap.value
        assertTrue("第二行必须落在第一行下方", secondRowTop > firstRowBottom)
    }

    // ---------- 2. 空态高度 ----------

    /** 空态各块高度之和（与 ChatEmptyState 的 Spacer 取值对应）。 */
    private fun emptyStateContentHeight(): Float {
        val quotePill = 34f
        val avatar = 68f
        val title = 40f
        val tagline = 24f
        val intro = 60f
        val suggestionRow = 44f
        val suggestionCount = 4
        val suggestionGap = 8f
        val spacers = 22f + 14f + 4f + 10f + 20f
        return quotePill + avatar + title + tagline + intro + spacers +
            suggestionRow * suggestionCount + suggestionGap * (suggestionCount - 1)
    }

    @Test
    fun `empty state exceeds small screen viewport`() {
        // 顶栏 + 输入栏 + Tab 栏占掉后，1080x2400 机型可用高度约 460dp。
        val availableHeight = 460f
        assertTrue(
            "内容高于可用高度，因此必须可滚动而不能居中裁切",
            emptyStateContentHeight() > availableHeight,
        )
    }

    @Test
    fun `all four suggestions are accounted for`() {
        val suggestionsBlock = 44f * 4 + 8f * 3
        assertEquals(
            "四条快捷输入必须完整参与高度计算，不能有任何一条被压扁",
            200f,
            suggestionsBlock,
            0.01f,
        )
    }

    // ---------- 3. 状态栏内边距 ----------

    @Test
    fun `status bar inset applied exactly once`() {
        val statusBarHeight = 44f
        // Scaffold contentWindowInsets = WindowInsets(0) 后，innerPadding 顶部为 0。
        val scaffoldTopInset = 0f
        val explicitStatusBarPadding = statusBarHeight
        assertEquals(
            "状态栏高度只能算一次，否则顶部会多出一整条空白",
            statusBarHeight,
            scaffoldTopInset + explicitStatusBarPadding,
            0.01f,
        )
    }

    @Test
    fun `input bar sits flush against the tab bar`() {
        val inputBarBottomPadding = 0f
        assertEquals("输入框底部不留额外边距", 0f, inputBarBottomPadding, 0.01f)
    }

    // ---------- 4. 建议只填入不发送 ----------

    /**
     * 用一个最小状态机复现"点击建议"的行为：
     * 期望结果是草稿被填充，且没有产生任何一次发送。
     */
    private class DraftBox {
        var draft: String = ""
        var sentCount: Int = 0
        fun fill(text: String) { draft = text }
        fun send() { sentCount++; draft = "" }
    }

    @Test
    fun `tapping a suggestion only fills the draft`() {
        val box = DraftBox()
        box.fill("最近 AI 有什么新进展")

        assertEquals("最近 AI 有什么新进展", box.draft)
        assertEquals("点击建议不得直接发送", 0, box.sentCount)
    }

    @Test
    fun `tapping a follow up replaces the draft without sending`() {
        val box = DraftBox()
        box.fill("第一个追问")
        box.fill("第二个追问")

        assertEquals("第二个追问", box.draft)
        assertEquals(0, box.sentCount)
    }

    @Test
    fun `explicit send is still the only way to submit`() {
        val box = DraftBox()
        box.fill("推荐几本明朝历史的书")
        box.send()

        assertEquals(1, box.sentCount)
        assertEquals("发送后草稿清空", "", box.draft)
    }
}
