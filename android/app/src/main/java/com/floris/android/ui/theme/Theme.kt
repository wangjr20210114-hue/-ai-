package com.floris.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Aurora palette (iOS system colors)
val AccentLight = Color(0xFF007AFF)
val AccentDark = Color(0xFF0A84FF)
val AuroraIndigo = Color(0xFF5E5CE6)
val AuroraCyan = Color(0xFF64D2FF)
val GreenLight = Color(0xFF34C759)
val GreenDark = Color(0xFF30D158)
val OrangeLight = Color(0xFFFF9500)
val OrangeDark = Color(0xFFFF9F0A)
val RedLight = Color(0xFFFF3B30)
val RedDark = Color(0xFFFF453A)
val PurpleLight = Color(0xFFAF52DE)
val PurpleDark = Color(0xFFBF5AF2)

val BgGroupedLight = Color(0xFFF2F2F7)
val CardLight = Color(0xFFFFFFFF)
val CardSecondaryLight = Color(0xFFF9F9FB)
val LabelSecondaryLight = Color(0x993C3C43)
val SeparatorLight = Color(0x1F3C3C43)

val BgGroupedDark = Color(0xFF000000)
val CardDark = Color(0xFF1C1C1E)
val CardSecondaryDark = Color(0xFF2C2C2E)
val LabelSecondaryDark = Color(0x99EBEBF5)
val SeparatorDark = Color(0x1FEBEBF5)

private val LightColors = lightColorScheme(
    primary = AccentLight,
    onPrimary = Color.White,
    primaryContainer = AccentLight.copy(alpha = 0.12f),
    onPrimaryContainer = AccentLight,
    secondary = PurpleLight,
    onSecondary = Color.White,
    secondaryContainer = PurpleLight.copy(alpha = 0.12f),
    onSecondaryContainer = PurpleLight,
    tertiary = GreenLight,
    error = RedLight,
    background = BgGroupedLight,
    onBackground = Color(0xFF000000),
    surface = CardLight,
    onSurface = Color(0xFF000000),
    surfaceVariant = CardSecondaryLight,
    onSurfaceVariant = LabelSecondaryLight,
    outline = SeparatorLight,
    surfaceContainerLowest = CardLight,
    surfaceContainerLow = CardSecondaryLight,
    surfaceContainer = CardLight,
    surfaceContainerHigh = CardLight,
    surfaceContainerHighest = CardSecondaryLight,
)

private val DarkColors = darkColorScheme(
    primary = AccentDark,
    onPrimary = Color.White,
    primaryContainer = AccentDark.copy(alpha = 0.16f),
    onPrimaryContainer = AccentDark,
    secondary = PurpleDark,
    onSecondary = Color.White,
    secondaryContainer = PurpleDark.copy(alpha = 0.16f),
    onSecondaryContainer = PurpleDark,
    tertiary = GreenDark,
    error = RedDark,
    background = BgGroupedDark,
    onBackground = Color(0xFFFFFFFF),
    surface = CardDark,
    onSurface = Color(0xFFFFFFFF),
    surfaceVariant = CardSecondaryDark,
    onSurfaceVariant = LabelSecondaryDark,
    outline = SeparatorDark,
    surfaceContainerLowest = BgGroupedDark,
    surfaceContainerLow = CardDark,
    surfaceContainer = CardDark,
    surfaceContainerHigh = CardSecondaryDark,
    surfaceContainerHighest = CardSecondaryDark,
)

val FlorisTypography = Typography(
    displayMedium = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Bold,
        fontSize = 34.sp, lineHeight = 41.sp, letterSpacing = 0.37.sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Bold,
        fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = 0.36.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Bold,
        fontSize = 22.sp, lineHeight = 28.sp, letterSpacing = 0.35.sp,
    ),
    headlineSmall = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp, lineHeight = 26.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp, lineHeight = 22.sp, letterSpacing = (-0.43).sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp, lineHeight = 21.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Normal,
        fontSize = 17.sp, lineHeight = 23.sp, letterSpacing = (-0.43).sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Normal,
        fontSize = 16.sp, lineHeight = 22.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Normal,
        fontSize = 15.sp, lineHeight = 20.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Medium,
        fontSize = 13.sp, lineHeight = 18.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Normal,
        fontSize = 13.sp, lineHeight = 18.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Default, fontWeight = FontWeight.Normal,
        fontSize = 12.sp, lineHeight = 16.sp,
    ),
)

@Composable
fun FlorisTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = FlorisTypography,
        content = content,
    )
}
