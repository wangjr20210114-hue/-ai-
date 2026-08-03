package com.floris.android.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.ParagraphStyle
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextIndent
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Lightweight Markdown renderer tuned for chat output:
 * headings, bold/italic, inline code, fenced code blocks, lists,
 * blockquotes, links and horizontal rules. Streaming-safe (renders any
 * prefix of a document without crashing).
 */
@Composable
fun MarkdownText(
    markdown: String,
    modifier: Modifier = Modifier,
    streaming: Boolean = false,
) {
    val blocks = rememberMarkdownBlocks(markdown)
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        blocks.forEach { block ->
            when (block) {
                is MdBlock.Heading -> Text(
                    parseInline(block.text),
                    style = when (block.level) {
                        1 -> MaterialTheme.typography.headlineMedium
                        2 -> MaterialTheme.typography.headlineSmall
                        else -> MaterialTheme.typography.titleLarge
                    },
                )
                is MdBlock.Code -> CodeBlock(block.code)
                is MdBlock.Quote -> Row {
                    Box(
                        Modifier.width(3.dp).height(20.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.5f)),
                    )
                    Spacer8()
                    Text(
                        parseInline(block.text),
                        style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                is MdBlock.Bullet -> Text(
                    parseInline(block.text),
                    style = MaterialTheme.typography.bodyMedium.copy(
                        textIndent = TextIndent(firstLine = 0.sp, restLine = 14.sp),
                    ),
                    modifier = Modifier.padding(start = ((block.indent) * 14).dp),
                )
                is MdBlock.Rule -> Box(
                    Modifier.fillMaxWidth().height(1.dp)
                        .background(MaterialTheme.colorScheme.outline),
                )
                is MdBlock.Paragraph -> Text(
                    parseInline(block.text),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
        if (streaming) StreamingCaret()
    }
}

@Composable
private fun Spacer8() = androidx.compose.foundation.layout.Spacer(Modifier.width(8.dp))

@Composable
private fun StreamingCaret() {
    val transition = rememberInfiniteTransition(label = "caret")
    val alpha by transition.animateFloat(
        initialValue = 0.2f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(450), RepeatMode.Reverse),
        label = "alpha",
    )
    Box(
        Modifier
            .width(9.dp)
            .height(18.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(MaterialTheme.colorScheme.primary.copy(alpha = alpha)),
    )
}

@Composable
private fun CodeBlock(code: String) {
    SelectionContainer {
        Box(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .horizontalScroll(rememberScrollState())
                .padding(12.dp),
        ) {
            Text(
                code.trimEnd(),
                style = MaterialTheme.typography.labelLarge.copy(fontFamily = FontFamily.Monospace),
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

// ---------- Parsing ----------

internal sealed interface MdBlock {
    data class Heading(val level: Int, val text: String) : MdBlock
    data class Code(val code: String) : MdBlock
    data class Quote(val text: String) : MdBlock
    data class Bullet(val text: String, val indent: Int) : MdBlock
    data object Rule : MdBlock
    data class Paragraph(val text: String) : MdBlock
}

@Composable
private fun rememberMarkdownBlocks(markdown: String): List<MdBlock> =
    androidx.compose.runtime.remember(markdown) { parseBlocks(markdown) }

private fun parseBlocks(markdown: String): List<MdBlock> {
    val blocks = mutableListOf<MdBlock>()
    val lines = markdown.split('\n')
    var index = 0
    val paragraph = StringBuilder()

    fun flushParagraph() {
        val text = paragraph.toString().trim()
        if (text.isNotEmpty()) blocks += MdBlock.Paragraph(text)
        paragraph.clear()
    }

    while (index < lines.size) {
        val line = lines[index]
        when {
            line.trimStart().startsWith("```") -> {
                flushParagraph()
                val code = StringBuilder()
                index++
                while (index < lines.size && !lines[index].trimStart().startsWith("```")) {
                    code.append(lines[index]).append('\n')
                    index++
                }
                blocks += MdBlock.Code(code.toString())
            }
            line.startsWith("#") -> {
                flushParagraph()
                val level = line.takeWhile { it == '#' }.length.coerceIn(1, 6)
                blocks += MdBlock.Heading(level, line.drop(level).trim())
            }
            line.trim().matches(Regex("^(-{3,}|\\*{3,}|_{3,})$")) -> {
                flushParagraph()
                blocks += MdBlock.Rule
            }
            line.trimStart().startsWith("> ") -> {
                flushParagraph()
                blocks += MdBlock.Quote(line.trimStart().removePrefix("> ").trim())
            }
            line.trimStart().matches(Regex("^([-*+] |\\d+\\. ).*")) -> {
                flushParagraph()
                val indent = (line.length - line.trimStart().length) / 2
                val trimmed = line.trim()
                val body = when {
                    trimmed.matches(Regex("^\\d+\\. .*")) -> trimmed
                    else -> "• " + trimmed.drop(2)
                }
                blocks += MdBlock.Bullet(body, indent)
            }
            line.isBlank() -> flushParagraph()
            else -> {
                if (paragraph.isNotEmpty()) paragraph.append('\n')
                paragraph.append(line.trimEnd())
            }
        }
        index++
    }
    flushParagraph()
    return blocks
}

/** Inline parsing: **bold**, *italic*, `code`, [label](url). */
@Composable
private fun parseInline(text: String): AnnotatedString {
    val codeBackground = MaterialTheme.colorScheme.surfaceVariant
    val linkColor = MaterialTheme.colorScheme.primary
    val uriHandler = LocalUriHandler.current
    return buildAnnotatedString {
        var i = 0
        while (i < text.length) {
            when {
                text.startsWith("**", i) -> {
                    val end = text.indexOf("**", i + 2)
                    if (end > i + 2) {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                            append(parseInlinePlain(text.substring(i + 2, end)))
                        }
                        i = end + 2
                    } else { append(text[i]); i++ }
                }
                text.startsWith("`", i) -> {
                    val end = text.indexOf('`', i + 1)
                    if (end > i + 1) {
                        withStyle(
                            SpanStyle(
                                fontFamily = FontFamily.Monospace,
                                background = codeBackground,
                                fontSize = 13.sp,
                            ),
                        ) { append(text.substring(i + 1, end)) }
                        i = end + 1
                    } else { append(text[i]); i++ }
                }
                text.startsWith("[", i) -> {
                    val labelEnd = text.indexOf("](", i)
                    val urlEnd = if (labelEnd > 0) text.indexOf(')', labelEnd + 2) else -1
                    if (labelEnd > 0 && urlEnd > labelEnd + 2) {
                        val label = text.substring(i + 1, labelEnd)
                        val url = text.substring(labelEnd + 2, urlEnd)
                        pushLink(
                            LinkAnnotation.Clickable(
                                tag = "link",
                                styles = TextLinkStyles(style = SpanStyle(color = linkColor)),
                            ) { runCatching { uriHandler.openUri(url) } },
                        )
                        append(label)
                        pop()
                        i = urlEnd + 1
                    } else { append(text[i]); i++ }
                }
                text.startsWith("*", i) && !text.startsWith("**", i) -> {
                    val end = text.indexOf('*', i + 1)
                    if (end > i + 1) {
                        withStyle(SpanStyle(fontStyle = FontStyle.Italic)) {
                            append(text.substring(i + 1, end))
                        }
                        i = end + 1
                    } else { append(text[i]); i++ }
                }
                else -> { append(text[i]); i++ }
            }
        }
    }
}

private fun parseInlinePlain(text: String): String = text
    .replace("**", "")
    .replace("`", "")
