package com.floris.android.core.notify

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.floris.android.MainActivity
import com.floris.android.R
import com.floris.android.core.model.ProactiveNotification

/**
 * 主动提醒的系统通知栏推送——这是移动端相对网页端的优势：
 * 应用没打开也能看到 Floris 的提醒。
 *
 * 原则：只做「展示」。提醒内容、状态流转全部由后端 /proactive 决定，
 * 客户端不自行生成提醒，也不在本地判断该不该提醒。
 */
object ProactiveNotifier {

    const val CHANNEL_ID = "floris_proactive"
    const val EXTRA_NOTIFICATION_ID = "floris_notification_id"
    const val EXTRA_ACTION_PROMPT = "floris_action_prompt"

    /** 通知 id 从固定基数递增，避免和别的通知撞号。 */
    private const val ID_BASE = 41_000

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Floris 主动提醒",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "Floris 主动发现的日程、待办与值得关注的信息"
            setShowBadge(true)
        }
        manager.createNotificationChannel(channel)
    }

    fun hasPermission(context: Context): Boolean {
        // Android 13 起需要显式的 POST_NOTIFICATIONS 授权。
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * 推送一批提醒。返回实际推送出去的条数，便于调用方做去重记账。
     * 已读 / 已忽略的条目由调用方过滤，这里不做业务判断。
     */
    fun notifyAll(context: Context, items: List<ProactiveNotification>): Int {
        if (items.isEmpty() || !hasPermission(context)) return 0
        ensureChannel(context)
        val manager = NotificationManagerCompat.from(context)
        var pushed = 0
        items.forEachIndexed { index, item ->
            val notification = build(context, item) ?: return@forEachIndexed
            runCatching {
                manager.notify(ID_BASE + (item.id.hashCode() and 0xFFF) + index, notification)
                pushed++
            }
        }
        return pushed
    }

    private fun build(
        context: Context,
        item: ProactiveNotification,
    ): android.app.Notification? {
        if (item.title.isBlank()) return null
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_NOTIFICATION_ID, item.id)
            // 点开直接把后端建议的处理话术带进输入框。
            item.actionPrompt?.let { putExtra(EXTRA_ACTION_PROMPT, it) }
        }
        val pending = PendingIntent.getActivity(
            context,
            item.id.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val body = item.body?.takeIf { it.isNotBlank() }
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_floris)
            .setContentTitle(item.title)
            .apply {
                if (body != null) {
                    setContentText(body)
                    setStyle(NotificationCompat.BigTextStyle().bigText(body))
                }
            }
            .setPriority(
                if (item.priority == "high") NotificationCompat.PRIORITY_HIGH
                else NotificationCompat.PRIORITY_DEFAULT,
            )
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
    }
}
