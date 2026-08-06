package com.floris.android.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.floris.android.R
import com.floris.android.core.model.SkillAccess
import com.floris.android.core.model.SkillAccessStatus
import com.floris.android.ui.theme.LocalDarkTheme
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import com.floris.android.ui.theme.orbBrush
import kotlinx.coroutines.delay

// ---------- Motion ----------

val SpringGentle = spring<Float>(stiffness = Spring.StiffnessLow, dampingRatio = 0.82f)
val SpringSnappy = spring<Float>(stiffness = Spring.StiffnessMediumLow, dampingRatio = 0.78f)

/** 统一按压反馈：弹性缩放 + 触感，无水波纹。 */
fun Modifier.pressable(
    enabled: Boolean = true,
    scaleDown: Float = 0.96f,
    onClick: () -> Unit,
): Modifier = composed {
    val interactionSource = remember { MutableInteractionSource() }
    val pressed by interactionSource.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed && enabled) scaleDown else 1f,
        animationSpec = spring(stiffness = Spring.StiffnessMedium, dampingRatio = 0.62f),
        label = "pressScale",
    )
    val haptics = LocalHapticFeedback.current
    this
        .graphicsLayer { scaleX = scale; scaleY = scale }
        .clickable(interactionSource = interactionSource, indication = null, enabled = enabled) {
            haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
            onClick()
        }
}

// ---------- Buttons ----------

enum class PillStyle { Primary, Tonal, Ghost, Danger }

/**
 * 高级感药丸按钮：主按钮为品牌渐变，次按钮为柔和底色，
 * 幽灵按钮仅文字。全部走弹性按压，无 Material 阴影与描边。
 */
@Composable
fun PillButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    style: PillStyle = PillStyle.Primary,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
    compact: Boolean = false,
) {
    val scheme = MaterialTheme.colorScheme
    val brush: Brush? = if (style == PillStyle.Primary && enabled) {
        Brush.horizontalGradient(
            listOf(scheme.primary, scheme.secondary),
        )
    } else null
    val flatColor = when {
        !enabled -> scheme.surfaceVariant
        style == PillStyle.Tonal -> scheme.primaryContainer
        style == PillStyle.Danger -> scheme.error.copy(alpha = 0.12f)
        style == PillStyle.Ghost -> Color.Transparent
        else -> scheme.primary
    }
    val contentColor = when {
        !enabled -> scheme.onSurfaceVariant
        style == PillStyle.Primary -> Color.White
        style == PillStyle.Tonal -> scheme.onPrimaryContainer
        style == PillStyle.Danger -> scheme.error
        else -> scheme.primary
    }
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .then(if (brush != null) Modifier.background(brush) else Modifier.background(flatColor))
            .pressable(enabled = enabled, onClick = onClick)
            .padding(
                horizontal = if (compact) 14.dp else 20.dp,
                vertical = if (compact) 8.dp else 11.dp,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            leadingIcon?.let {
                Icon(it, null, tint = contentColor, modifier = Modifier.size(15.dp))
                Spacer(Modifier.width(6.dp))
            }
            Text(
                text,
                style = MaterialTheme.typography.labelLarge,
                color = contentColor,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
        }
    }
}

/** 圆形图标按钮：透明底 + 弹性按压，用于顶栏与输入栏。 */
@Composable
fun IconPill(
    icon: ImageVector,
    contentDescription: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    size: Dp = 38.dp,
    iconSize: Dp = 20.dp,
    tint: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    background: Color = Color.Transparent,
    enabled: Boolean = true,
) {
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(background)
            .pressable(enabled = enabled, scaleDown = 0.9f, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription, tint = tint, modifier = Modifier.size(iconSize))
    }
}

/** 主操作圆形按钮（发送 / 停止）：渐变 + 弹性。 */
@Composable
fun PrimaryIconButton(
    icon: ImageVector,
    contentDescription: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    danger: Boolean = false,
    size: Dp = 40.dp,
) {
    val scheme = MaterialTheme.colorScheme
    val brush = when {
        danger -> Brush.horizontalGradient(listOf(scheme.error, scheme.error))
        enabled -> Brush.horizontalGradient(listOf(scheme.primary, scheme.secondary))
        else -> Brush.horizontalGradient(
            listOf(scheme.primary.copy(alpha = 0.35f), scheme.secondary.copy(alpha = 0.35f)),
        )
    }
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(brush)
            .pressable(enabled = enabled, scaleDown = 0.9f, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription, tint = Color.White, modifier = Modifier.size(size * 0.44f))
    }
}

/** 位图猫系图标：统一用主题色染色，与矢量图标观感一致。 */
@Composable
fun CatIconImage(
    resId: Int,
    size: Dp,
    tint: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    contentDescription: String? = null,
    modifier: Modifier = Modifier,
) {
    Image(
        painter = painterResource(resId),
        contentDescription = contentDescription,
        colorFilter = ColorFilter.tint(tint),
        modifier = modifier.size(size),
    )
}

/** 与 [IconPill] 同款的位图图标药丸按钮（GPT 生成的猫系 PNG 图标）。 */
@Composable
fun CatIconPill(
    resId: Int,
    contentDescription: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    size: Dp = 38.dp,
    iconSize: Dp = 24.dp,
    tint: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    background: Color = Color.Transparent,
    enabled: Boolean = true,
) {
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(background)
            .pressable(enabled = enabled, scaleDown = 0.9f, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        CatIconImage(
            resId = resId,
            size = iconSize,
            tint = tint,
            contentDescription = contentDescription,
        )
    }
}

/** 主操作圆形按钮的位图版本（发送按钮使用猫系图标）。 */
@Composable
fun PrimaryIconButtonImage(
    resId: Int,
    contentDescription: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    danger: Boolean = false,
    size: Dp = 40.dp,
) {
    val scheme = MaterialTheme.colorScheme
    val brush = when {
        danger -> Brush.horizontalGradient(listOf(scheme.error, scheme.error))
        enabled -> Brush.horizontalGradient(listOf(scheme.primary, scheme.secondary))
        else -> Brush.horizontalGradient(
            listOf(scheme.primary.copy(alpha = 0.35f), scheme.secondary.copy(alpha = 0.35f)),
        )
    }
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(brush)
            .pressable(enabled = enabled, scaleDown = 0.9f, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        CatIconImage(
            resId = resId,
            size = size * 0.6f,
            tint = Color.White,
            contentDescription = contentDescription,
        )
    }
}

/** iOS 式分段控件，滑块带弹性位移。 */
@Composable
fun SegmentedControl(
    options: List<String>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(3.dp),
    ) {
        options.forEachIndexed { index, label ->
            val selected = index == selectedIndex
            val background by animateColorAsState(
                if (selected) MaterialTheme.colorScheme.surface else Color.Transparent,
                animationSpec = tween(220),
                label = "segBg",
            )
            val textColor by animateColorAsState(
                if (selected) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant,
                animationSpec = tween(220),
                label = "segText",
            )
            Box(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(999.dp))
                    .background(background)
                    .pressable(scaleDown = 0.97f) { onSelect(index) }
                    .padding(vertical = 8.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    style = MaterialTheme.typography.labelLarge,
                    color = textColor,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                )
            }
        }
    }
}

/** 自绘开关：轨道与滑块均为弹性动画，比 Material Switch 更轻。 */
@Composable
fun FlorisSwitch(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val scheme = MaterialTheme.colorScheme
    val track by animateColorAsState(
        when {
            !enabled -> scheme.surfaceVariant
            checked -> scheme.primary
            else -> scheme.outline.copy(alpha = 0.35f)
        },
        animationSpec = tween(220),
        label = "trackColor",
    )
    val offset by animateDpAsState(
        if (checked) 20.dp else 2.dp,
        animationSpec = spring(stiffness = Spring.StiffnessMedium, dampingRatio = 0.68f),
        label = "knobOffset",
    )
    Box(
        modifier = modifier
            .size(width = 44.dp, height = 26.dp)
            .clip(RoundedCornerShape(999.dp))
            .background(track)
            .pressable(enabled = enabled, scaleDown = 0.94f) { onCheckedChange(!checked) },
    ) {
        Box(
            Modifier
                .padding(top = 2.dp, start = offset)
                .size(22.dp)
                .clip(CircleShape)
                .background(Color.White),
        )
    }
}

/** 步进器：用于富搜索数量等数值偏好。 */
@Composable
fun Stepper(
    value: Int,
    onValueChange: (Int) -> Unit,
    modifier: Modifier = Modifier,
    range: IntRange = 0..12,
) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconPill(
            icon = Icons.Default.Remove,
            contentDescription = t(StringKey.Decrease),
            onClick = { onValueChange((value - 1).coerceIn(range)) },
            size = 32.dp,
            iconSize = 16.dp,
            enabled = value > range.first,
            tint = if (value > range.first) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
        )
        AnimatedContent(
            targetState = value,
            transitionSpec = {
                if (targetState > initialState) {
                    (slideInVertically { it } + fadeIn()) togetherWith
                        (slideOutVertically { -it } + fadeOut())
                } else {
                    (slideInVertically { -it } + fadeIn()) togetherWith
                        (slideOutVertically { it } + fadeOut())
                }
            },
            label = "stepValue",
        ) { current ->
            Text(
                "$current",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface,
                textAlign = TextAlign.Center,
                modifier = Modifier.width(28.dp),
            )
        }
        IconPill(
            icon = Icons.Default.Add,
            contentDescription = t(StringKey.Increase),
            onClick = { onValueChange((value + 1).coerceIn(range)) },
            size = 32.dp,
            iconSize = 16.dp,
            enabled = value < range.last,
            tint = if (value < range.last) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
        )
    }
}

// ---------- Surfaces ----------

/**
 * 卡片容器。对齐网页端 --app-panel + --app-border + --app-shadow：
 * 纯色底衬在背景图上会"糊"成一片，所以必须同时有描边和投影才能分层。
 */
@Composable
fun FlorisCard(
    modifier: Modifier = Modifier,
    corner: Dp = 16.dp,
    containerColor: Color = MaterialTheme.colorScheme.surface,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(corner)
    val base = modifier
        .shadow(
            elevation = 6.dp,
            shape = shape,
            ambientColor = panelShadowColor(),
            spotColor = panelShadowColor(),
        )
        .clip(shape)
        .background(containerColor)
        .border(1.dp, panelBorderColor(), shape)
        .fillMaxWidth()
    Column(
        modifier = if (onClick != null) base.pressable(scaleDown = 0.985f, onClick = onClick) else base,
        content = content,
    )
}

/** 对齐网页端 --app-border：浅色是暖棕透明，深色是淡紫透明。 */
@Composable
fun panelBorderColor(): Color =
    if (LocalDarkTheme.current) Color(0x1AD6C4FF) else Color(0x1A754322)

/** 对齐网页端 --app-shadow 的投影色调。 */
@Composable
fun panelShadowColor(): Color =
    if (LocalDarkTheme.current) Color(0x66050208) else Color(0x1F6F3B1C)

/**
 * 游客提示条：柔和底衬 + 图标 + 文案（可选行动按钮）。
 * 用于技能页与个人中心，提醒游客登录以解锁全部能力。
 */
@Composable
fun GuestNotice(
    text: String,
    actionText: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.55f))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Outlined.Info, contentDescription = null,
            tint = MaterialTheme.colorScheme.onSecondaryContainer,
            modifier = Modifier.size(15.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSecondaryContainer,
            modifier = Modifier.weight(1f),
        )
        if (actionText != null && onAction != null) {
            Spacer(Modifier.width(8.dp))
            PillButton(text = actionText, onClick = onAction, compact = true)
        }
    }
}

/** A single user-facing renderer for Maker-owned feature access decisions. */
@Composable
fun SkillAccessNotice(
    access: SkillAccess,
    onRequestLogin: () -> Unit,
    onOpenSkills: () -> Unit,
) {
    when (access.status) {
        SkillAccessStatus.Loading -> Box(
            Modifier.fillMaxWidth().padding(vertical = 20.dp),
            contentAlignment = Alignment.Center,
        ) { InlineLoading() }
        SkillAccessStatus.LoginRequired -> GuestNotice(
            text = t(StringKey.FeatureSignInRequired),
            actionText = t(StringKey.GuestSignInCta),
            onAction = onRequestLogin,
        )
        SkillAccessStatus.Disabled -> GuestNotice(
            text = t(StringKey.FeatureSkillDisabled),
            actionText = t(StringKey.FeatureOpenSkills),
            onAction = onOpenSkills,
        )
        SkillAccessStatus.Unavailable -> GuestNotice(t(StringKey.FeatureUnavailable))
        SkillAccessStatus.Available -> Unit
    }
}

/** 设置类列表行：标题 + 说明 + 右侧内容槽。 */
@Composable
fun SettingRow(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    icon: ImageVector? = null,
    onClick: (() -> Unit)? = null,
    trailing: @Composable (() -> Unit)? = null,
) {
    FlorisCard(modifier = modifier, onClick = onClick) {
        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            icon?.let {
                Box(
                    Modifier
                        .size(34.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(MaterialTheme.colorScheme.primaryContainer),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        it, null,
                        tint = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.size(18.dp),
                    )
                }
                Spacer(Modifier.width(12.dp))
            }
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                subtitle?.let {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            trailing?.let {
                Spacer(Modifier.width(12.dp))
                it()
            }
        }
    }
}

@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier) {
    Text(
        text = title,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier.padding(start = 4.dp, top = 18.dp, bottom = 8.dp),
    )
}

@Composable
fun EmptyState(
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        CatAvatar(size = 58.dp)
        Spacer(Modifier.height(16.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(
            subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

// ---------- Brand ----------

/** 橘猫头像（网页端同款）——只代表 Floris 自己。 */
@Composable
fun CatAvatar(size: Dp, modifier: Modifier = Modifier) {
    Image(
        painter = painterResource(R.drawable.floris_avatar),
        contentDescription = "Floris",
        modifier = modifier
            .size(size)
            .clip(RoundedCornerShape(size * 0.3f)),
    )
}

/**
 * 用户头像。与网页端一致：没有自定义头像时用木偶铃铛猫
 * （default-user-avatar-anime.png），绝不复用 Floris 自己的橘猫。
 */
@Composable
fun UserAvatar(size: Dp, modifier: Modifier = Modifier) {
    Image(
        painter = painterResource(R.drawable.default_user_avatar),
        contentDescription = t(StringKey.Self),
        modifier = modifier
            .size(size)
            .clip(CircleShape),
    )
}

/** 品牌光晕（登录 / 启动）。 */
@Composable
fun AuroraOrb(size: Dp, modifier: Modifier = Modifier) {
    val transition = androidx.compose.animation.core.rememberInfiniteTransition(label = "aurora")
    val pulse by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(tween(2400, easing = LinearEasing), RepeatMode.Reverse),
        label = "pulse",
    )
    Box(
        modifier = modifier
            .size(size)
            .graphicsLayer { scaleX = pulse; scaleY = pulse }
            .clip(CircleShape)
            .background(orbBrush()),
    )
}

/** 顶栏轮播暖心语录（网页端同款）。 */
@Composable
fun QuotePill(modifier: Modifier = Modifier) {
    val quotes = listOf(
        t(StringKey.QuoteOne), t(StringKey.QuoteTwo), t(StringKey.QuoteThree),
        t(StringKey.QuoteFour), t(StringKey.QuoteFive),
    )
    var index by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(6500)
            index = (index + 1) % quotes.size
        }
    }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.82f))
            .padding(horizontal = 14.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("🐾", style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.width(6.dp))
        AnimatedContent(
            targetState = quotes[index],
            transitionSpec = {
                (fadeIn(tween(320)) + slideInVertically { it / 2 }) togetherWith
                    (fadeOut(tween(320)) + slideOutVertically { -it / 2 })
            },
            label = "quote",
        ) { quote ->
            Text(
                quote,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

// ---------- Feedback ----------

@Composable
fun ShimmerBox(modifier: Modifier = Modifier, corner: Dp = 12.dp) {
    val transition = androidx.compose.animation.core.rememberInfiniteTransition(label = "shimmer")
    val offset by transition.animateFloat(
        initialValue = -400f,
        targetValue = 1200f,
        animationSpec = infiniteRepeatable(tween(1500, easing = LinearEasing)),
        label = "offset",
    )
    val base = MaterialTheme.colorScheme.surfaceVariant
    val highlight = MaterialTheme.colorScheme.primary.copy(alpha = 0.25f)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(corner))
            .background(
                Brush.linearGradient(
                    colors = listOf(base, highlight, base),
                    start = androidx.compose.ui.geometry.Offset(offset, 0f),
                    end = androidx.compose.ui.geometry.Offset(offset + 400f, 0f),
                ),
            ),
    )
}

@Composable
fun InlineLoading(modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        horizontalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator(
            modifier = Modifier.size(20.dp),
            strokeWidth = 2.dp,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}

@Composable
fun StatusChip(text: String, color: Color, modifier: Modifier = Modifier) {
    val background by animateColorAsState(color.copy(alpha = 0.13f), label = "chipBg")
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .padding(horizontal = 9.dp, vertical = 4.dp),
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = color,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
        )
    }
}

/** 勾选标记，用于选中项。 */
@Composable
fun CheckMark(visible: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(visible = visible, enter = fadeIn(), exit = fadeOut()) {
        Icon(
            Icons.Default.Check, null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = modifier.size(18.dp),
        )
    }
}

/** 列表进入动画（交错淡入上滑）。 */
@Composable
fun AnimateIn(index: Int, content: @Composable () -> Unit) {
    AnimatedVisibility(
        visible = true,
        enter = fadeIn(tween(260)) + slideInVertically(
            animationSpec = spring(stiffness = Spring.StiffnessLow, dampingRatio = 0.85f),
            initialOffsetY = { it / 8 },
        ),
    ) { content() }
}
