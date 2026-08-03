package com.floris.android.ui.onboarding

import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow

/**
 * 引导目标登记表。
 *
 * 与网页端 `data-onboarding="..."` 选择器等价：页面上的组件通过
 * [Modifier.onboardingTarget] 上报自己在窗口中的位置，引导层据此
 * 把背景虚化并挖出聚光灯洞口。
 */
class OnboardingTargets {
    private val rects = mutableStateMapOf<String, Rect>()

    fun report(key: String, rect: Rect) {
        rects[key] = rect
    }

    fun forget(key: String) {
        rects.remove(key)
    }

    /** 取第一个已登记且可见的目标区域。 */
    fun firstVisible(keys: List<String>): Rect? =
        keys.firstNotNullOfOrNull { key ->
            rects[key]?.takeIf { it.width > 2f && it.height > 2f }
        }
}

val LocalOnboardingTargets = compositionLocalOf { OnboardingTargets() }

/**
 * 把当前组件登记为引导目标。`key` 与 [TourStepKey] 中的常量一致。
 * 不影响布局与绘制，只上报窗口坐标。
 */
@Composable
fun Modifier.onboardingTarget(key: String): Modifier {
    val targets = LocalOnboardingTargets.current
    return this.onGloballyPositioned { coordinates ->
        val size = coordinates.size
        if (size.width <= 0 || size.height <= 0) {
            targets.forget(key)
            return@onGloballyPositioned
        }
        val origin = coordinates.positionInWindow()
        targets.report(
            key,
            Rect(
                left = origin.x,
                top = origin.y,
                right = origin.x + size.width,
                bottom = origin.y + size.height,
            ),
        )
    }
}

/** 引导步骤锚点键，逐条对应网页端 STEPS 的 selectors。 */
object TourStepKey {
    const val NEW_CONVERSATION = "new-conversation"
    const val HISTORY = "conversation-history"
    const val INPUT = "chat-input"
    const val MAP = "map"
    const val CALENDAR = "calendar"
    const val READING = "reading"
    const val REMINDERS = "reminders"
    const val SKILLS = "skills"
    const val SETTINGS = "settings"
    const val THEME = "theme"
    const val GITHUB = "github"
    const val PROFILE = "profile"
}
