package com.floris.android.ui.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.animateRectAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathOperation
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.Canvas
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.pressable
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlin.math.max

private const val FEATURE_DOC_URL =
    "https://github.com/wangjr20210114-hue/-ai-/blob/main/README.md"

/** 漫游步骤要落在哪个页面上（客户端会自动切换过去）。 */
enum class TourTarget { CHAT, SKILLS, CALENDAR, READING, PROFILE }

private data class TourStep(
    val copy: StringKey,
    val icon: ImageVector,
    val target: TourTarget,
    val label: String,
    /** 聚光灯锚点，按顺序取第一个可见的。 */
    val anchors: List<String>,
)

/**
 * 漫游步骤：覆盖 README 列出的全部界面与能力。
 * 相比网页端多补了「输入框」「个人中心」两步，因为移动端这两处是独立入口。
 */
private val steps = listOf(
    TourStep(
        StringKey.OnboardingNewConversation, Icons.Default.AddCircle, TourTarget.CHAT,
        "新对话", listOf(TourStepKey.NEW_CONVERSATION),
    ),
    TourStep(
        StringKey.OnboardingHistory, Icons.Default.History, TourTarget.CHAT,
        "历史记录", listOf(TourStepKey.HISTORY),
    ),
    TourStep(
        StringKey.OnboardingChatInput, Icons.Default.Send, TourTarget.CHAT,
        "对话输入", listOf(TourStepKey.INPUT),
    ),
    TourStep(
        StringKey.OnboardingSkills, Icons.Default.Star, TourTarget.SKILLS,
        "Skills 广场", listOf(TourStepKey.SKILLS),
    ),
    TourStep(
        StringKey.OnboardingCalendar, Icons.Default.DateRange, TourTarget.CALENDAR,
        "日程", listOf(TourStepKey.CALENDAR),
    ),
    TourStep(
        StringKey.OnboardingReading, Icons.Default.MenuBook, TourTarget.READING,
        "我的阅读", listOf(TourStepKey.READING),
    ),
    TourStep(
        StringKey.OnboardingMap, Icons.Default.Place, TourTarget.PROFILE,
        "地图工作区", listOf(TourStepKey.MAP),
    ),
    TourStep(
        StringKey.OnboardingReminders, Icons.Default.Notifications, TourTarget.PROFILE,
        "主动提醒", listOf(TourStepKey.REMINDERS),
    ),
    TourStep(
        StringKey.OnboardingProfileCenter, Icons.Default.Person, TourTarget.PROFILE,
        "个人中心", listOf(TourStepKey.PROFILE),
    ),
    TourStep(
        StringKey.OnboardingSettings, Icons.Default.Settings, TourTarget.PROFILE,
        "设置", listOf(TourStepKey.SETTINGS),
    ),
    TourStep(
        StringKey.OnboardingTheme, Icons.Default.WbSunny, TourTarget.PROFILE,
        "白天 / 黑夜", listOf(TourStepKey.THEME, TourStepKey.SETTINGS),
    ),
    TourStep(
        StringKey.OnboardingGithub, Icons.Default.Info, TourTarget.PROFILE,
        "功能文档", listOf(TourStepKey.GITHUB),
    ),
)

private enum class Phase { WELCOME, TOUR, SKIP_HINT }

/**
 * 新手引导（对齐网页端 FlorisOnboarding）：
 * 半透明遮罩把整屏压暗，只在当前组件位置挖出一个圆角洞并加高亮描边，
 * 说明气泡贴着该组件出现；遮罩吃掉所有手势，用户不会误触到底层控件。
 */
@Composable
fun OnboardingOverlay(
    onNavigate: (TourTarget) -> Unit,
    onFinish: () -> Unit,
) {
    var phase by remember { mutableStateOf(Phase.WELCOME) }
    var index by remember { mutableIntStateOf(0) }
    val uriHandler = LocalUriHandler.current
    val targets = LocalOnboardingTargets.current
    val step = steps[index]

    LaunchedEffect(phase, index) {
        if (phase == Phase.TOUR) onNavigate(step.target)
    }

    // 目标区域：切页后组件需要一帧完成布局，取不到时退化为居中卡片。
    val spotlight: Rect? = if (phase == Phase.TOUR) targets.firstVisible(step.anchors) else null

    Box(
        Modifier
            .fillMaxSize()
            // 引导期间吞掉全部手势，等价于网页端的 interaction lock。
            .pointerInput(phase, index) { awaitPointerEventScope { while (true) awaitPointerEvent() } },
    ) {
        SpotlightScrim(spotlight = spotlight, dimmed = phase != Phase.TOUR)

        when (phase) {
            Phase.WELCOME -> WelcomeCard(
                modifier = Modifier.align(Alignment.Center).padding(24.dp),
                onStart = { phase = Phase.TOUR },
                onSkip = { phase = Phase.SKIP_HINT },
            )

            Phase.TOUR -> TourCallout(
                step = step,
                index = index,
                total = steps.size,
                spotlight = spotlight,
                onNext = { if (index == steps.lastIndex) onFinish() else index++ },
                onSkip = onFinish,
                onOpenDoc = { runCatching { uriHandler.openUri(FEATURE_DOC_URL) } },
            )

            Phase.SKIP_HINT -> HintCard(
                modifier = Modifier.align(Alignment.Center).padding(28.dp),
                onDismiss = onFinish,
            )
        }
    }
}

/**
 * 虚化遮罩 + 聚光灯洞口。用 even-odd 差集把目标区域从遮罩里减掉，
 * 洞口位置随步骤平滑过渡（对应网页端 blurTiles + focus-ring）。
 */
@Composable
private fun SpotlightScrim(spotlight: Rect?, dimmed: Boolean) {
    val scrimAlpha by animateFloatAsState(
        targetValue = if (dimmed) 0.62f else 0.72f,
        animationSpec = tween(240),
        label = "scrimAlpha",
    )
    val density = LocalDensity.current
    val gutter = with(density) { 8.dp.toPx() }
    val corner = with(density) { 16.dp.toPx() }
    val primary = MaterialTheme.colorScheme.primary

    // 洞口在步骤之间做弹性位移，视觉上像光圈滑过去。
    val hole = spotlight ?: Rect.Zero
    val animated by animateRectAsState(
        targetValue = hole,
        animationSpec = spring(stiffness = Spring.StiffnessMediumLow, dampingRatio = 0.85f),
        label = "spotlightRect",
    )

    Canvas(Modifier.fillMaxSize()) {
        val scrim = Color.Black.copy(alpha = scrimAlpha)
        if (spotlight == null || animated.width <= 2f || animated.height <= 2f) {
            drawRect(color = scrim)
            return@Canvas
        }
        val expanded = Rect(
            left = max(0f, animated.left - gutter),
            top = max(0f, animated.top - gutter),
            right = animated.right + gutter,
            bottom = animated.bottom + gutter,
        )
        val roundHole = RoundRect(expanded, CornerRadius(corner, corner))
        val overlay = Path().apply { addRect(Rect(Offset.Zero, size)) }
        val cutout = Path().apply { addRoundRect(roundHole) }
        val masked = Path.combine(PathOperation.Difference, overlay, cutout)
        drawPath(masked, color = scrim)
        // 高亮描边（focus ring）
        drawRoundRect(
            color = primary,
            topLeft = Offset(expanded.left, expanded.top),
            size = Size(expanded.width, expanded.height),
            cornerRadius = CornerRadius(corner, corner),
            style = Stroke(width = with(density) { 2.dp.toPx() }),
        )
    }
}

/**
 * 说明气泡：优先贴在目标下方，空间不够时翻到上方，
 * 完全取不到目标时居中（与网页端 popoverStyle 同策略）。
 */
@Composable
private fun TourCallout(
    step: TourStep,
    index: Int,
    total: Int,
    spotlight: Rect?,
    onNext: () -> Unit,
    onSkip: () -> Unit,
    onOpenDoc: () -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val density = LocalDensity.current
        val screenHeightPx = with(density) { maxHeight.toPx() }
        val estimatedCardPx = with(density) { 190.dp.toPx() }
        val marginPx = with(density) { 18.dp.toPx() }

        val topOffset: Dp = when {
            spotlight == null -> (maxHeight - 190.dp) / 2
            spotlight.bottom + marginPx + estimatedCardPx <= screenHeightPx ->
                with(density) { (spotlight.bottom + marginPx).toDp() }
            spotlight.top - marginPx - estimatedCardPx >= 0f ->
                with(density) { (spotlight.top - marginPx - estimatedCardPx).toDp() }
            else -> (maxHeight - 190.dp) / 2
        }.coerceIn(12.dp, (maxHeight - 120.dp).coerceAtLeast(12.dp))

        TourCard(
            step = step,
            index = index,
            total = total,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(start = 16.dp, end = 16.dp)
                .padding(top = topOffset),
            onNext = onNext,
            onSkip = onSkip,
            onOpenDoc = onOpenDoc,
        )
    }
}

@Composable
private fun WelcomeCard(
    modifier: Modifier,
    onStart: () -> Unit,
    onSkip: () -> Unit,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(26.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 24.dp, vertical = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CatAvatar(size = 66.dp)
        Spacer(Modifier.height(14.dp))
        Text(
            t(StringKey.OnboardingWelcomeTitle),
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(16.dp))
        listOf(
            t(StringKey.OnboardingOwners),
            t(StringKey.OnboardingGithubWelcome),
            t(StringKey.OnboardingIntroOffer),
        ).forEach { line ->
            Text(
                line,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        }
        Spacer(Modifier.height(12.dp))
        PillButton(
            text = t(StringKey.OnboardingStart),
            onClick = onStart,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(6.dp))
        PillButton(
            text = t(StringKey.OnboardingSkip),
            onClick = onSkip,
            style = PillStyle.Ghost,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun TourCard(
    step: TourStep,
    index: Int,
    total: Int,
    modifier: Modifier,
    onNext: () -> Unit,
    onSkip: () -> Unit,
    onOpenDoc: () -> Unit,
) {
    val isLast = index == total - 1
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(24.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 18.dp, vertical = 18.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(38.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    step.icon, null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.size(19.dp),
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(step.label, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${index + 1}/$total",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            CatAvatar(size = 32.dp)
        }

        Spacer(Modifier.height(12.dp))
        AnimatedContent(
            targetState = step.copy,
            transitionSpec = {
                (slideInHorizontally { it / 4 } + fadeIn(tween(260))) togetherWith
                    (slideOutHorizontally { -it / 4 } + fadeOut(tween(200)))
            },
            label = "tourCopy",
        ) { copy ->
            Text(
                t(copy),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }

        Spacer(Modifier.height(16.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                repeat(total) { dot ->
                    val active = dot == index
                    val width by animateFloatAsState(
                        if (active) 16f else 5f,
                        animationSpec = spring(stiffness = Spring.StiffnessMediumLow, dampingRatio = 0.75f),
                        label = "dotWidth",
                    )
                    Box(
                        Modifier
                            .height(5.dp)
                            .width(width.dp)
                            .clip(CircleShape)
                            .background(
                                if (active) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.outline.copy(alpha = 0.4f),
                            ),
                    )
                }
            }
            Spacer(Modifier.width(10.dp))
            if (!isLast) {
                Text(
                    t(StringKey.OnboardingSkip),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier
                        .pressable(onClick = onSkip)
                        .padding(horizontal = 8.dp, vertical = 6.dp),
                )
                Spacer(Modifier.width(4.dp))
            }
            PillButton(
                text = if (isLast) t(StringKey.OnboardingFinish) else t(StringKey.OnboardingNext),
                onClick = {
                    if (isLast) onOpenDoc()
                    onNext()
                },
                compact = true,
            )
        }
    }
}

@Composable
private fun HintCard(modifier: Modifier, onDismiss: () -> Unit) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(22.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 22.dp, vertical = 22.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CatAvatar(size = 48.dp)
        Spacer(Modifier.height(12.dp))
        Text(
            t(StringKey.OnboardingSkipHint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(16.dp))
        PillButton(
            text = t(StringKey.OnboardingGotIt),
            onClick = onDismiss,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
