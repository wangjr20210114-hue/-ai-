package com.floris.android.ui.profile

import com.floris.android.core.model.ProactiveNotification
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProactiveNotificationsTest {

    private val now = 1_700_000_000L

    /** 未读保留；已读/已忽略不展示。 */
    @Test
    fun `keeps unread and drops handled ones`() {
        val items = listOf(
            ProactiveNotification(id = "a", title = "未读", status = "unread"),
            ProactiveNotification(id = "b", title = "已读", status = "read"),
            ProactiveNotification(id = "c", title = "已忽略", status = "dismissed"),
        )
        assertEquals(listOf("a"), activeNotifications(items, now).map { it.id })
    }

    /** 推迟中的提醒在到期前仍然可见，过期后消失。 */
    @Test
    fun `snoozed visible only inside the window`() {
        val items = listOf(
            ProactiveNotification(id = "future", title = "还没到", status = "snoozed", snoozedUntil = now + 600),
            ProactiveNotification(id = "past", title = "已过期", status = "snoozed", snoozedUntil = now - 600),
            ProactiveNotification(id = "missing", title = "缺时间", status = "snoozed"),
        )
        assertEquals(listOf("future"), activeNotifications(items, now).map { it.id })
    }

    /** 最多展示 10 条，避免个人中心被提醒淹没。 */
    @Test
    fun `caps at ten items`() {
        val items = (1..25).map {
            ProactiveNotification(id = "n$it", title = "提醒 $it", status = "unread")
        }
        assertEquals(10, activeNotifications(items, now).size)
    }

    /** 空列表安全返回空。 */
    @Test
    fun `handles empty input`() {
        assertTrue(activeNotifications(emptyList(), now).isEmpty())
    }
}
