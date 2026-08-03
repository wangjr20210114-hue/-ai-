package com.floris.android.ui.layout

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * 横竖屏适配的统一入口。
 *
 * 横屏时可用高度只有竖屏的四成左右，直接沿用竖屏的间距会让
 * 头像、标题、按钮挤成一团甚至被裁掉。这里集中给出两套尺寸，
 * 各页只需要读取，不必各自判断方向。
 */
object Responsive {

    /** 当前是否横屏。 */
    val isLandscape: Boolean
        @Composable @ReadOnlyComposable
        get() = LocalConfiguration.current.screenWidthDp > LocalConfiguration.current.screenHeightDp

    /** 屏幕短边（dp），用于判断是否为平板/折叠屏展开态。 */
    val shortestSide: Int
        @Composable @ReadOnlyComposable
        get() = LocalConfiguration.current.smallestScreenWidthDp

    /** 宽屏（平板、折叠屏展开）：内容需要限宽居中，否则一行太长难读。 */
    val isWide: Boolean
        @Composable @ReadOnlyComposable
        get() = shortestSide >= 600

    /** 内容最大宽度：宽屏限到 640dp 居中，手机上不限制。 */
    val contentMaxWidth: Dp
        @Composable @ReadOnlyComposable
        get() = if (isWide) 640.dp else Dp.Unspecified

    /** 页面左右留白。 */
    val horizontalPadding: Dp
        @Composable @ReadOnlyComposable
        get() = when {
            isWide -> 28.dp
            isLandscape -> 24.dp
            else -> 16.dp
        }

    /** 品牌头像尺寸：横屏明显收小，给内容腾出竖向空间。 */
    val brandAvatar: Dp
        @Composable @ReadOnlyComposable
        get() = if (isLandscape) 44.dp else 68.dp

    /** 登录页头像。 */
    val loginAvatar: Dp
        @Composable @ReadOnlyComposable
        get() = if (isLandscape) 52.dp else 84.dp

    /** 竖向区块间距的缩放系数。 */
    val verticalScale: Float
        @Composable @ReadOnlyComposable
        get() = if (isLandscape) 0.5f else 1f

    /** 按系数缩放一个竖向间距，最小保留 4dp。 */
    @Composable
    @ReadOnlyComposable
    fun gap(value: Dp): Dp {
        val scaled = value * verticalScale
        return if (scaled < 4.dp) 4.dp else scaled
    }
}
