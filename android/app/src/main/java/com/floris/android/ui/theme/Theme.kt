package com.floris.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ---------- Floris 暖橙橘猫 palette (from web tokens.css) ----------

// Light: 橙色暖调
val BrandLight = Color(0xFFDF6B2D)
val BrandHoverLight = Color(0xFFF28B42)
val BrandActiveLight = Color(0xFFBD4F1D)
val BrandDeepLight = Color(0xFF923A15)
val BrandContainerLight = Color(0xFFFFE4CC)
val BrandSoftLight = Color(0xFFFFF4E8)
val BubbleStartLight = Color(0xFFF28B42)
val BubbleEndLight = Color(0xFFDF632D)

val BgLight = Color(0xFFFFF8F0)
val PanelLight = Color(0xFFFFFDF9)
val Panel2Light = Color(0xFFFFF5E8)
val TextLight = Color(0xFF34261D)
val Text2Light = Color(0xFF745F50)
val BorderLight = Color(0x1F754322)

// Dark: 紫色夜空
val BrandDark = Color(0xFFA78BFA)
val BrandHoverDark = Color(0xFFC4B5FD)
val BrandActiveDark = Color(0xFF8B5CF6)
val BrandDeepDark = Color(0xFFDDD6FE)
val BrandContainerDark = Color(0xFF352552)
val BrandSoftDark = Color(0xFF211739)
val BubbleStartDark = Color(0xFF7C3AED)
val BubbleEndDark = Color(0xFFA855F7)

val BgDark = Color(0xFF100C1D)
val PanelDark = Color(0xFF181325)
val Panel2Dark = Color(0xFF211A32)
val AiBubbleDark = Color(0xFF241B35)
val TextDark = Color(0xF0F8F4FF)
val Text2Dark = Color(0xADE5DBFF)
val BorderDark = Color(0x1AD6C4FF)

// Semantic
val GreenLight = Color(0xFF34A853)
val GreenDark = Color(0xFF30D158)
val RedLight = Color(0xFFD64541)
val RedDark = Color(0xFFFF6961)

private val LightColors = lightColorScheme(
    primary = BrandLight,
    onPrimary = Color.White,
    primaryContainer = BrandContainerLight,
    onPrimaryContainer = BrandDeepLight,
    secondary = BrandActiveLight,
    onSecondary = Color.White,
    secondaryContainer = BrandSoftLight,
    onSecondaryContainer = BrandActiveLight,
    tertiary = GreenLight,
    error = RedLight,
    background = BgLight,
    onBackground = TextLight,
    surface = PanelLight,
    onSurface = TextLight,
    surfaceVariant = Panel2Light,
    onSurfaceVariant = Text2Light,
    outline = BorderLight,
    surfaceContainerLowest = PanelLight,
    surfaceContainerLow = Panel2Light,
    surfaceContainer = PanelLight,
    surfaceContainerHigh = Panel2Light,
    surfaceContainerHighest = Panel2Light,
)

private val DarkColors = darkColorScheme(
    primary = BrandDark,
    onPrimary = Color(0xFF1A1030),
    primaryContainer = BrandContainerDark,
    onPrimaryContainer = BrandDeepDark,
    secondary = BrandHoverDark,
    onSecondary = Color(0xFF1A1030),
    secondaryContainer = BrandSoftDark,
    onSecondaryContainer = BrandHoverDark,
    tertiary = GreenDark,
    error = RedDark,
    background = BgDark,
    onBackground = TextDark,
    surface = PanelDark,
    onSurface = TextDark,
    surfaceVariant = Panel2Dark,
    onSurfaceVariant = Text2Dark,
    outline = BorderDark,
    surfaceContainerLowest = BgDark,
    surfaceContainerLow = PanelDark,
    surfaceContainer = PanelDark,
    surfaceContainerHigh = AiBubbleDark,
    surfaceContainerHighest = Panel2Dark,
)

/** 当前是否为深色，供背景皮肤等场景读取（不受系统设置直接影响）。 */
val LocalDarkTheme = androidx.compose.runtime.compositionLocalOf { false }

/** 用户气泡渐变（网页端 --app-user-bubble 同款 135° 渐变）。 */
val userBubbleBrushLight = Brush.linearGradient(listOf(BubbleStartLight, BubbleEndLight))
val userBubbleBrushDark = Brush.linearGradient(listOf(BubbleStartDark, BubbleEndDark))

@Composable
fun userBubbleBrush(): Brush =
    if (LocalDarkTheme.current) userBubbleBrushDark else userBubbleBrushLight

@Composable
fun orbBrush(): Brush = if (LocalDarkTheme.current) {
    Brush.linearGradient(listOf(BubbleStartDark, BrandDark, BrandHoverDark))
} else {
    Brush.linearGradient(listOf(BubbleStartLight, BrandLight, Color(0xFFFFC270)))
}

private val DisplayFamily = FontFamily.Serif
private val BodyFamily = FontFamily.Default

val FlorisTypography = Typography(
    displayMedium = TextStyle(
        fontFamily = DisplayFamily, fontWeight = FontWeight.Bold,
        fontSize = 34.sp, lineHeight = 41.sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = DisplayFamily, fontWeight = FontWeight.Bold,
        fontSize = 28.sp, lineHeight = 34.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = DisplayFamily, fontWeight = FontWeight.Bold,
        fontSize = 22.sp, lineHeight = 28.sp,
    ),
    headlineSmall = TextStyle(
        fontFamily = DisplayFamily, fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp, lineHeight = 26.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp, lineHeight = 22.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp, lineHeight = 21.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Normal,
        fontSize = 17.sp, lineHeight = 23.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Normal,
        fontSize = 16.sp, lineHeight = 22.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Normal,
        fontSize = 15.sp, lineHeight = 20.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Medium,
        fontSize = 13.sp, lineHeight = 18.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Normal,
        fontSize = 13.sp, lineHeight = 18.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = BodyFamily, fontWeight = FontWeight.Normal,
        fontSize = 12.sp, lineHeight = 16.sp,
    ),
)

@Composable
fun FlorisTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    androidx.compose.runtime.CompositionLocalProvider(LocalDarkTheme provides darkTheme) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColors else LightColors,
            typography = FlorisTypography,
            content = content,
        )
    }
}
