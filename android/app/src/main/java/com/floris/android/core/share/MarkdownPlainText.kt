package com.floris.android.core.share

/**
 * 把回答里的 Markdown 还原成可直接粘贴的纯文本（对齐网页端"复制纯文字"）。
 *
 * 只剥离标记、保留人读内容与段落结构：
 *  - 代码块保留正文，去掉围栏与语言标注；
 *  - 链接与图片保留可读文字（必要时补上地址）；
 *  - 标题、引用、列表符号去掉，列表改用「· 」；
 *  - 表格保留单元格文本，用空格分隔，去掉分隔行。
 */
object MarkdownPlainText {

    private val fencedBlock = Regex("```[^\\n]*\\n([\\s\\S]*?)```")
    private val image = Regex("!\\[([^]]*)]\\(([^)\\s]+)[^)]*\\)")
    private val link = Regex("\\[([^]]+)]\\(([^)\\s]+)[^)]*\\)")
    private val heading = Regex("^\\s{0,3}#{1,6}\\s+", RegexOption.MULTILINE)
    private val quote = Regex("^\\s{0,3}>\\s?", RegexOption.MULTILINE)
    private val bullet = Regex("^(\\s*)[-*+]\\s+", RegexOption.MULTILINE)
    private val ordered = Regex("^(\\s*)(\\d+)[.)]\\s+", RegexOption.MULTILINE)
    private val thematicBreak = Regex("([-*_])\\s*(\\1\\s*){2,}")
    private val tableDivider = Regex("\\|?[\\s:|-]*-[\\s:|-]*\\|?")
    private val inlineCode = Regex("`([^`\\n]+)`")
    private val bold = Regex("(\\*\\*|__)(?=\\S)(.+?)(?<=\\S)\\1")
    private val italic = Regex("(?<![*_\\w])([*_])(?=\\S)(.+?)(?<=\\S)\\1(?![*_\\w])")
    private val strike = Regex("~~(?=\\S)(.+?)(?<=\\S)~~")
    private val footnote = Regex("\\[\\^[^]]+]")
    private val blankRun = Regex("\\n{3,}")
    private val trailingSpace = Regex("[ \\t]+(?=\\n)")

    fun convert(markdown: String): String {
        if (markdown.isBlank()) return ""
        var text = markdown.replace("\r\n", "\n")

        text = fencedBlock.replace(text) { match -> match.groupValues[1].trimEnd() }
        text = image.replace(text) { match ->
            match.groupValues[1].ifBlank { match.groupValues[2] }
        }
        text = link.replace(text) { match ->
            val label = match.groupValues[1].trim()
            val url = match.groupValues[2].trim()
            // 文字与地址相同则不重复输出。
            if (label.isEmpty() || label == url) url else "$label（$url）"
        }
        text = footnote.replace(text, "")

        // 先按整行剔除分割线与表格分隔行，再做行内替换：
        // 否则 "---" 会被无序列表规则误当成列表项。
        text = text.lines().mapNotNull { line ->
            val trimmed = line.trim()
            when {
                trimmed.isEmpty() -> line
                thematicBreak.matches(trimmed) -> null
                tableDivider.matches(trimmed) -> null
                trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.length > 1 ->
                    trimmed.trim('|').split('|').map { it.trim() }
                        .filter { it.isNotEmpty() }
                        .joinToString("  ")
                else -> line
            }
        }.joinToString("\n")

        text = heading.replace(text, "")
        text = quote.replace(text, "")
        text = bullet.replace(text) { match -> match.groupValues[1] + "· " }
        text = ordered.replace(text) { match ->
            match.groupValues[1] + match.groupValues[2] + ". "
        }
        text = inlineCode.replace(text) { it.groupValues[1] }
        text = bold.replace(text) { it.groupValues[2] }
        text = italic.replace(text) { it.groupValues[2] }
        text = strike.replace(text) { it.groupValues[1] }

        text = trailingSpace.replace(text, "")
        text = blankRun.replace(text, "\n\n")
        return text.trim()
    }
}
