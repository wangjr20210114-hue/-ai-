package com.floris.android.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.unit.dp

/**
 * Floris 统一的“可爱精简猫系”图标集。
 *
 * 全部用简单几何（圆、圆角矩形、三角耳）手工构建，保持同一圆润风格：
 * 导航、新对话、日程、阅读、提醒与加号都用猫耳/爪印元素，其他功能图标
 * 统一使用 Outlined 风格 Material 图标，避免 filled/outlined 混用。
 */
object CatIcons {

    /** 地点：地图钉 + 爪印。 */
    val PawPin: ImageVector by lazy { catIcon("PawPin") { pawPin() } }

    /** 日程：带猫耳的日历。 */
    val CatCalendar: ImageVector by lazy { catIcon("CatCalendar") { catCalendar() } }

    /** 阅读：翻开的书 + 爪印。 */
    val CatBook: ImageVector by lazy { catIcon("CatBook") { catBook() } }

    /** 新对话 / 添加：带猫耳的圆角加号。 */
    val CatPlus: ImageVector by lazy { catIcon("CatPlus") { catPlus() } }

    /** 提醒：带猫耳的铃铛。 */
    val CatBell: ImageVector by lazy { catIcon("CatBell") { catBell() } }
}

private fun catIcon(name: String, block: PathBuilder.() -> Unit): ImageVector =
    ImageVector.Builder(
        name = name,
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f,
    ).addPath(
        pathData = PathBuilder().apply(block).nodes,
        pathFillType = PathFillType.NonZero,
        fill = SolidColor(Color.Black),
    ).build()

private fun PathBuilder.circle(cx: Float, cy: Float, r: Float) {
    val k = 0.5522847498f * r
    moveTo(cx, cy - r)
    curveTo(cx + k, cy - r, cx + r, cy - k, cx + r, cy)
    curveTo(cx + r, cy + k, cx + k, cy + r, cx, cy + r)
    curveTo(cx - k, cy + r, cx - r, cy + k, cx - r, cy)
    curveTo(cx - r, cy - k, cx - k, cy - r, cx, cy - r)
    close()
}

private fun PathBuilder.roundRect(
    left: Float,
    top: Float,
    right: Float,
    bottom: Float,
    corner: Float,
) {
    val k = 0.5522847498f * corner
    moveTo(left + corner, top)
    lineTo(right - corner, top)
    curveTo(right - corner + k, top, right, top + corner - k, right, top + corner)
    lineTo(right, bottom - corner)
    curveTo(right, bottom - corner + k, right - corner + k, bottom, right - corner, bottom)
    lineTo(left + corner, bottom)
    curveTo(left + corner - k, bottom, left, bottom - corner + k, left, bottom - corner)
    lineTo(left, top + corner)
    curveTo(left, top + corner - k, left + corner - k, top, left + corner, top)
    close()
}

private fun PathBuilder.triangle(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) {
    moveTo(x1, y1)
    lineTo(x2, y2)
    lineTo(x3, y3)
    close()
}

private fun PathBuilder.paw(cx: Float, cy: Float, scale: Float) {
    circle(cx - 2.6f * scale, cy - 2.2f * scale, 1.15f * scale)
    circle(cx, cy - 3.2f * scale, 1.15f * scale)
    circle(cx + 2.6f * scale, cy - 2.2f * scale, 1.15f * scale)
    circle(cx, cy + 0.6f * scale, 2.25f * scale)
}

private fun PathBuilder.pawPin() {
    circle(12f, 8.6f, 5.6f)
    triangle(9.6f, 12.6f, 12f, 21f, 14.4f, 12.6f)
    paw(12f, 8.1f, 0.72f)
}

private fun PathBuilder.catCalendar() {
    roundRect(5f, 7f, 19f, 20f, 2.6f)
    triangle(6.2f, 9.2f, 7.6f, 4.4f, 9.4f, 9.0f)
    triangle(14.6f, 9.0f, 16.4f, 4.4f, 17.8f, 9.2f)
    circle(9f, 9.5f, 0.85f)
    circle(15f, 9.5f, 0.85f)
    roundRect(6.5f, 12.8f, 13.5f, 14.2f, 0.7f)
    roundRect(6.5f, 16.0f, 9.5f, 17.4f, 0.7f)
}

private fun PathBuilder.catBook() {
    roundRect(4f, 8f, 11.2f, 18f, 1.8f)
    roundRect(12.8f, 8f, 20f, 18f, 1.8f)
    roundRect(11.4f, 8f, 12.6f, 18f, 0.6f)
    paw(16.4f, 12.6f, 0.62f)
}

private fun PathBuilder.catPlus() {
    roundRect(4.5f, 4.5f, 19.5f, 19.5f, 4.2f)
    triangle(6.0f, 7.2f, 7.4f, 3.0f, 9.0f, 7.0f)
    triangle(15.0f, 7.0f, 16.6f, 3.0f, 18.0f, 7.2f)
    roundRect(11.2f, 9.0f, 12.8f, 15.0f, 0.8f)
    roundRect(9.0f, 11.2f, 15.0f, 12.8f, 0.8f)
}

private fun PathBuilder.catBell() {
    moveTo(7.2f, 14.5f)
    curveTo(7.2f, 9.8f, 9.6f, 7.2f, 12f, 7.2f)
    curveTo(14.4f, 7.2f, 16.8f, 9.8f, 16.8f, 14.5f)
    lineTo(16.8f, 16.4f)
    lineTo(7.2f, 16.4f)
    close()
    triangle(8.0f, 10.6f, 9.2f, 5.8f, 10.8f, 10.2f)
    triangle(13.2f, 10.2f, 14.8f, 5.8f, 16.0f, 10.6f)
    circle(12f, 19.2f, 1.5f)
    roundRect(10.0f, 17.0f, 14.0f, 18.2f, 0.6f)
}
