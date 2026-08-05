package com.floris.android.core.notify

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.floris.android.FlorisApp
import com.floris.android.core.auth.AuthState
import com.floris.android.ui.prefs.StringKey
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Android scheduler only; Maker remains authoritative for reminder policy and content. */
object ProactiveSync {
    private const val WORK_NAME = "floris-proactive-sync-v1"

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<ProactiveSyncWorker>(
            30,
            TimeUnit.MINUTES,
        ).setConstraints(
            Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build(),
        ).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }
}

class ProactiveSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as? FlorisApp ?: return Result.failure()
        val container = app.container
        return try {
            if (container.authManager.state.value is AuthState.Loading) {
                container.authManager.restore()
            }
            val identity = (container.authManager.state.value as? AuthState.SignedIn)?.identity
                ?: return Result.success()
            val response = container.repository.proactive(
                container.repository.activeConversationId(),
                "tick",
            )
            val now = System.currentTimeMillis() / 1000
            val eligible = container.repository.parseProactiveNotifications(response)
                .filter { item ->
                    item.status == "unread" ||
                        (item.status == "snoozed" && (item.snoozedUntil ?: 0) > now)
                }
                .take(10)
            if (eligible.isNotEmpty() && ProactiveNotifier.hasPermission(applicationContext)) {
                val subject = identity.subject_id.ifBlank { identity.id }.ifBlank { identity.auth_type }
                val active = eligible.filter { deliveryStore().claim(subject, it) }
                ProactiveNotifier.notifyAll(
                    applicationContext,
                    active,
                    container.strings.get(StringKey.NotificationChannelName),
                    container.strings.get(StringKey.NotificationChannelDescription),
                )
            }
            Result.success()
        } catch (_: IOException) {
            Result.retry()
        } catch (_: Throwable) {
            // A malformed optional reminder must not put the scheduler into a retry storm.
            Result.success()
        }
    }

    private fun deliveryStore() = ProactiveDeliveryStore(applicationContext)
}

/** Small device-side delivery ledger; it never stores reminder content or policy. */
class ProactiveDeliveryStore(context: Context) {
    private val preferences = context.getSharedPreferences("floris_proactive_delivery", Context.MODE_PRIVATE)

    @Synchronized
    fun claim(
        subject: String,
        notification: com.floris.android.core.model.ProactiveNotification,
    ): Boolean {
        val key = "delivered:${subject.hashCode().toUInt()}:${notification.id}"
        if (preferences.contains(key)) return false
        val entries = preferences.all.entries
            .filter { it.key.startsWith("delivered:") }
            .sortedByDescending { (it.value as? Long) ?: 0L }
        val editor = preferences.edit().putLong(key, System.currentTimeMillis())
        entries.drop(MAX_DELIVERED_IDS - 1).forEach { editor.remove(it.key) }
        editor.apply()
        return true
    }

    private companion object {
        const val MAX_DELIVERED_IDS = 100
    }
}
