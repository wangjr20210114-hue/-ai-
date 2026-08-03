package com.floris.android.core.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class MarkdownPlainTextTest {

    /** 标题、加粗、斜体、行内代码的标记全部剥掉，文字一个不少。 */
    @Test
    fun `strips inline markers and keeps words`() {
        val result = MarkdownPlainText.convert(
            "## 结论\n这是**重点**，也有*强调*和 `code` 片段。",
        )
        assertEquals("结论\n这是重点，也有强调和 code 片段。", result)
    }

    /** 代码块保留正文，去掉围栏与语言标注。 */
    @Test
    fun `keeps code block body without fences`() {
        val result = MarkdownPlainText.convert("说明：\n```kotlin\nval a = 1\n```")
        assertEquals("说明：\nval a = 1", result)
    }

    /** 链接保留文字并补上地址；文字与地址相同时不重复。 */
    @Test
    fun `link keeps label and url`() {
        assertEquals(
            "参考 Floris（https://floris.dev）",
            MarkdownPlainText.convert("参考 [Floris](https://floris.dev)"),
        )
        assertEquals(
            "https://floris.dev",
            MarkdownPlainText.convert("[https://floris.dev](https://floris.dev)"),
        )
    }

    /** 图片只留 alt 文字，没有 alt 时退回地址。 */
    @Test
    fun `image falls back to alt or url`() {
        assertEquals("封面图", MarkdownPlainText.convert("![封面图](https://x/y.png)"))
        assertEquals("https://x/y.png", MarkdownPlainText.convert("![](https://x/y.png)"))
    }

    /** 无序列表换成「· 」，有序列表保留序号。 */
    @Test
    fun `normalizes list markers`() {
        val result = MarkdownPlainText.convert("- 甲\n- 乙\n\n1. первый\n2. 第二")
        assertEquals("· 甲\n· 乙\n\n1. первый\n2. 第二", result)
    }

    /** 引用与分割线去掉，段落结构保留。 */
    @Test
    fun `removes quotes and rules`() {
        val result = MarkdownPlainText.convert("> 引用一句\n\n---\n\n正文")
        assertEquals("引用一句\n\n正文", result)
    }

    /** 表格保留单元格文本，分隔行去掉。 */
    @Test
    fun `flattens tables`() {
        val result = MarkdownPlainText.convert(
            "| 名称 | 数量 |\n| --- | --- |\n| 猫 | 1 |",
        )
        assertEquals("名称  数量\n猫  1", result)
    }

    /** 结果不应残留任何 markdown 标记字符组合。 */
    @Test
    fun `output has no leftover markers`() {
        val result = MarkdownPlainText.convert("**粗**\n## 标\n`c`\n> q\n- l")
        assertFalse(result.contains("**"))
        assertFalse(result.contains("`"))
        assertFalse(result.contains("#"))
        assertFalse(result.contains(">"))
    }

    /** 空输入安全返回空串。 */
    @Test
    fun `blank input returns empty`() {
        assertEquals("", MarkdownPlainText.convert(""))
        assertEquals("", MarkdownPlainText.convert("   \n  "))
    }

    /** 连续空行压缩为一个空行，行尾空格清掉。 */
    @Test
    fun `collapses blank runs`() {
        assertEquals("甲\n\n乙", MarkdownPlainText.convert("甲   \n\n\n\n乙"))
    }
}
