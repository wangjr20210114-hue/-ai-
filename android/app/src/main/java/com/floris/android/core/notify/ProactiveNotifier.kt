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
 * Displays proactive reminders produced by the Maker backend.
 * Android owns notification presentation only; reminder policy and state stay server-authoritative.
 */
object ProactiveNotifier {

    const val CHANNEL_ID = "floris_proactive"
    const val EXTRA_NOTIFICATION_ID = "floris_notification_id"
    const val EXTRA_ACTION_PROMPT = "floris_action_prompt"

    /** Stable private range avoids collisions with unrelated notification channels. */
    private const val ID_BASE = 41_000

    fun ensureChannel(context: Context, name: String, descriptionText: String) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            name,
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = descriptionText
            setShowBadge(true)
        }
        manager.createNotificationChannel(channel)
    }

    fun hasPermission(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    /** Returns the number actually shown so callers can reconcile backend delivery state. */
    fun notifyAll(
        context: Context,
        items: List<ProactiveNotification>,
        channelName: String,
        channelDescription: String,
    ): Int {
        if (items.isEmpty() || !hasPermission(context)) return 0
        ensureChannel(context, channelName, channelDescription)
        val manager = NotificationManagerCompat.from(context)
        var pushed = 0
        items.forEachIndexed { index, item ->
            val notification = build(context, item) ?: return@forEachIndexed
            if (!hasPermission(context)) return@forEachIndexed
            try {
                manager.notify(ID_BASE + (item.id.hashCode() and 0xFFF) + index, notification)
                pushed++
            } catch (_: SecurityException) {
                // Permission can be revoked between the check and notify call.
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
            // Pass the backend-provided action into the composer; do not invent client-side copy.
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
