package com.floris.android.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.core.model.ProgressComponent
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.delay

/**
 * 处理进度：与网页端 ProgressRenderer 一一对应。
 *
 * 结构（网页端 .structured-progress-shell）：
 *  1. 顶部一行：呼吸光点 + 当前状态文案 + 搜索计时 + 省略号动画；
 *  2. 正文还没到时，展开阶段时间线（最多 5 条，✓ / – / • 前缀）。
 *
 * 阶段与活动文案取自契约允许的 stage/activity 取值，未知值降级为通用文案，
 * 不展示任何模型隐藏思维。
 */
@Composable
fun SearchProgress(
    message: ChatMessageUi,
    modifier: Modifier = Modifier,
) {
    val steps = message.progressTrail
    val webSearchActive = steps.any { it.activity == "web_search" && it.status == "active" }
    val searchTurnActive = message.searchStartedAt != null || webSearchActive

    // 秒表：仅在联网搜索进行中且后端还没给出耗时时自增。
    var elapsedSeconds by remember(message.id) { mutableIntStateOf(0) }
    var startedAt by remember(message.id, message.turnStartedAt) {
        mutableLongStateOf(message.turnStartedAt ?: System.currentTimeMillis())
    }
    LaunchedEffect(message.streaming, searchTurnActive) {
        if (!message.streaming || !searchTurnActive) return@LaunchedEffect
        while (true) {
            elapsedSeconds = ((System.currentTimeMillis() - startedAt) / 1000).toInt().coerceAtLeast(1)
            delay(1000)
        }
    }

    val searchTiming = when {
        searchTurnActive && message.streaming ->
            t(StringKey.SearchingForSeconds, elapsedSeconds.coerceAtLeast(1))
        else -> ""
    }

    // 与网页端同序：有正文就报"整理中"，否则报最新的活跃阶段。
    val activeStep = steps.lastOrNull { it.status == "active" } ?: steps.lastOrNull()
    val statusText = when {
        message.content.isNotBlank() ->
            if (message.searchResults?.media_pending == true) t(StringKey.WritingReviewing)
            else if (message.searchResults != null) t(StringKey.OrganizingVerifiedAnswer)
            else t(StringKey.OrganizingAnswer)
        activeStep != null -> t(progressLabelKey(activeStep))
        else -> t(StringKey.UnderstandingRequest)
    }

    Column(modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            BreathingDot(active = message.streaming)
            Spacer(Modifier.width(8.dp))
            AnimatedContent(
                targetState = statusText,
                transitionSpec = {
                    (slideInVertically { it / 2 } + fadeIn(tween(220))) togetherWith
                        (slideOutVertically { -it / 2 } + fadeOut(tween(160)))
                },
                label = "progressStatus",
            ) { text ->
                Text(
                    text,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (message.streaming) {
                EllipsisDots()
            }
            if (searchTiming.isNotEmpty()) {
                Spacer(Modifier.width(8.dp))
                Text(
                    searchTiming,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                    maxLines = 1,
                )
            }
        }

        // 正文还没开始时展开阶段时间线，正文一出现立刻收起（同网页端）。
        val trail = steps.filter { it.stage != "complete" }.takeLast(5)
        if (message.content.isBlank() && trail.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                trail.forEach { step ->
                    TrailRow(step)
                }
            }
        }
    }
}

/** 流式结束后的一行统计：N 个来源 · 搜索 X 秒。 */
@Composable
fun SearchCompleteMeta(message: ChatMessageUi, modifier: Modifier = Modifier) {
    val seconds = message.searchDurationSeconds ?: return
    val sources = message.searchResults?.results?.size ?: 0
    if (sources <= 0) return
    Text(
        t(StringKey.SearchCompleteMeta, sources, seconds),
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f),
        modifier = modifier.padding(top = 6.dp),
    )
}

@Composable
private fun TrailRow(step: ProgressComponent) {
    val done = step.status == "completed"
    val skipped = step.status == "skipped"
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(14.dp), contentAlignment = Alignment.Center) {
            when {
                done -> Icon(
                    Icons.Default.Check,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.size(11.dp),
                )
                skipped -> Text(
                    "–",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                )
                else -> Box(
                    Modifier
                        .size(5.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.primary),
                )
            }
        }
        Spacer(Modifier.width(6.dp))
        Text(
            t(progressLabelKey(step)),
            style = MaterialTheme.typography.labelSmall,
            color = if (step.status == "active") MaterialTheme.colorScheme.onSurface
            else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = if (skipped) 0.5f else 0.78f),
            fontWeight = if (step.status == "active") FontWeight.Medium else FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** 呼吸光点：网页端 .image-generating-spinner 的移动端等价物。 */
@Composable
private fun BreathingDot(active: Boolean) {
    if (!active) {
        Box(
            Modifier
                .size(14.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.tertiary.copy(alpha = 0.22f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Default.Check,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.size(10.dp),
            )
        }
        return
    }
    val transition = rememberInfiniteTransition(label = "breath")
    val scale by transition.animateFloat(
        initialValue = 0.7f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(900, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "breathScale",
    )
    val halo by transition.animateFloat(
        initialValue = 0.18f,
        targetValue = 0.42f,
        animationSpec = infiniteRepeatable(
            animation = tween(900, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "breathHalo",
    )
    val primary = MaterialTheme.colorScheme.primary
    Box(Modifier.size(14.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(14.dp)
                .graphicsLayer { alpha = halo }
                .clip(CircleShape)
                .background(primary.copy(alpha = 0.35f)),
        )
        Box(
            Modifier
                .size(7.dp)
                .graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                }
                .clip(CircleShape)
                .background(primary),
        )
    }
}

/** 三点省略号：与网页端 .image-generating-dots 相同的错峰淡入。 */
@Composable
private fun EllipsisDots() {
    val transition = rememberInfiniteTransition(label = "dots")
    Row(Modifier.padding(start = 3.dp), verticalAlignment = Alignment.Bottom) {
        repeat(3) { index ->
            val alpha by transition.animateFloat(
                initialValue = 0.15f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(1200, easing = LinearEasing),
                    repeatMode = RepeatMode.Reverse,
                    initialStartOffset = androidx.compose.animation.core.StartOffset(index * 180),
                ),
                label = "dot$index",
            )
            Text(
                ".",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha),
            )
        }
    }
}

/** stage / activity → 文案键，映射规则与网页端 progressTranslationKey 完全一致。 */
private fun progressLabelKey(step: ProgressComponent): StringKey {
    val byActivity = when (step.activity) {
        "web_search" -> StringKey.ProgressWebSearch
        "paper_search" -> StringKey.ProgressPaperSearch
        "place_search" -> StringKey.ProgressPlaceSearch
        "route_planning" -> StringKey.ProgressRoutePlanning
        "calendar_preparation" -> StringKey.ProgressCalendarPreparation
        "meeting_preparation" -> StringKey.ProgressMeetingPreparation
        "image_generation" -> StringKey.ProgressImageGeneration
        "image_review" -> StringKey.ProgressImageReview
        "component_action" -> StringKey.ProgressComponentAction
        else -> null
    }
    if (byActivity != null) return byActivity
    return when (step.stage) {
        "planning" -> StringKey.ProgressPlanning
        "retrieval" -> StringKey.ProgressRetrieval
        "verification" -> StringKey.ProgressVerification
        "synthesis" -> StringKey.ProgressSynthesis
        "finalizing" -> StringKey.ProgressFinalizing
        "complete" -> StringKey.ProgressComplete
        else -> StringKey.ProgressPlanning
    }
}

/**
 * 生图专属动画：与网页端 ImageCreationProgress 一致，
 * 四段文案每 1.8s 轮换一次。
 */
@Composable
fun ImageCreationProgress(message: ChatMessageUi, modifier: Modifier = Modifier) {
    val steps = listOf(
        t(StringKey.PaintingUnderstand),
        t(StringKey.PaintingCompose),
        t(StringKey.PaintingDetail),
        t(StringKey.PaintingReveal),
    )
    var index by remember(message.id) { mutableIntStateOf(0) }
    LaunchedEffect(message.id) {
        while (true) {
            delay(1800)
            index = (index + 1) % steps.size
        }
    }
    Column(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            BreathingDot(active = true)
            Spacer(Modifier.width(8.dp))
            AnimatedContent(
                targetState = steps[index],
                transitionSpec = {
                    (slideInVertically { it / 2 } + fadeIn(tween(260))) togetherWith
                        (slideOutVertically { -it / 2 } + fadeOut(tween(180)))
                },
                label = "paintingStep",
            ) { text ->
                Text(
                    text,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            EllipsisDots()
        }
        Spacer(Modifier.height(4.dp))
        Text(
            t(StringKey.PaintingWait),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.65f),
        )
    }
}
