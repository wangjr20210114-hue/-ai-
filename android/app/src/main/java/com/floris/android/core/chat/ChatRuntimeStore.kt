package com.floris.android.core.chat

import android.annotation.SuppressLint
import android.content.Context
import com.floris.android.core.location.ClientLocationFix
import com.floris.android.core.location.ClientLocationRequest
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/** One client-owned turn waiting behind the active Maker run. */
@Serializable
data class PendingChatTurn(
    val id: String,
    val text: String,
    val referenceImages: List<String> = emptyList(),
    val createdAt: Long = System.currentTimeMillis(),
    val currentLocation: ClientLocationFix? = null,
    val locationRequest: ClientLocationRequest = ClientLocationRequest(),
    val locationRetry: Boolean = false,
    /** Legacy queue fields retained only so pre-upgrade drafts still decode. */
    val latitude: Double? = null,
    val longitude: Double? = null,
    /** Maker 活动类型（如 route_calendar_offer_accepted）；普通提问为 null。 */
    val activity: String? = null,
    /** 路线转日程所需的路由计划 ID（仅 route_calendar_offer_accepted 使用）。 */
    val routePlanId: String? = null,
)

/**
 * Small durable adapter for client-only runtime state.
 *
 * Maker remains authoritative for an admitted turn. Android owns only the
 * waiting FIFO and an unconfirmed manual-stop intent, matching the Web client.
 */
class ChatRuntimeStore(context: Context, private val json: Json) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "floris_chat_runtime",
        Context.MODE_PRIVATE,
    )

    @Synchronized
    fun loadQueue(conversationId: String): List<PendingChatTurn> =
        preferences.getString(queueKey(conversationId), null)?.let { raw ->
            runCatching {
                json.decodeFromString(ListSerializer(PendingChatTurn.serializer()), raw)
            }.getOrNull()
        }.orEmpty().take(MAX_WAITING_TURNS)

    @Synchronized
    fun saveQueue(conversationId: String, turns: List<PendingChatTurn>) {
        val key = queueKey(conversationId)
        if (turns.isEmpty()) {
            preferences.edit().remove(key).apply()
            return
        }
        val encoded = json.encodeToString(
            ListSerializer(PendingChatTurn.serializer()),
            turns.take(MAX_WAITING_TURNS),
        )
        preferences.edit().putString(key, encoded).apply()
    }

    fun stoppedClientMessageId(conversationId: String): String =
        preferences.getString(stopKey(conversationId), "").orEmpty()

    @SuppressLint("ApplySharedPref") // Must survive an immediate process kill after tapping stop.
    fun markStopIntent(conversationId: String, clientMessageId: String) {
        preferences.edit().putString(stopKey(conversationId), clientMessageId).commit()
    }

    fun clearStopIntent(conversationId: String, clientMessageId: String = "") {
        val key = stopKey(conversationId)
        val stored = preferences.getString(key, "").orEmpty()
        if (clientMessageId.isBlank() || stored.isBlank() || stored == clientMessageId) {
            preferences.edit().remove(key).apply()
        }
    }

    fun loadActiveTurn(conversationId: String): PendingChatTurn? =
        preferences.getString(activeKey(conversationId), null)?.let { raw ->
            runCatching { json.decodeFromString(PendingChatTurn.serializer(), raw) }.getOrNull()
        }

    @SuppressLint("ApplySharedPref") // Must survive an immediate process kill before the network starts.
    fun saveActiveTurn(conversationId: String, turn: PendingChatTurn) {
        preferences.edit().putString(
            activeKey(conversationId),
            json.encodeToString(PendingChatTurn.serializer(), turn),
        ).commit()
    }

    @SuppressLint("ApplySharedPref") // Completion and local recovery state must change atomically.
    fun clearActiveTurn(conversationId: String, clientMessageId: String = "") {
        val key = activeKey(conversationId)
        val active = loadActiveTurn(conversationId)
        if (clientMessageId.isBlank() || active == null || active.id == clientMessageId) {
            preferences.edit().remove(key).commit()
        }
    }

    fun loadLocationRetry(conversationId: String): PendingChatTurn? =
        preferences.getString(locationRetryKey(conversationId), null)?.let { raw ->
            runCatching { json.decodeFromString(PendingChatTurn.serializer(), raw) }.getOrNull()
        }

    @SuppressLint("ApplySharedPref") // The retry must survive process death while permission UI is open.
    fun saveLocationRetry(conversationId: String, turn: PendingChatTurn) {
        preferences.edit().putString(
            locationRetryKey(conversationId),
            json.encodeToString(PendingChatTurn.serializer(), turn),
        ).commit()
    }

    fun clearLocationRetry(conversationId: String) {
        preferences.edit().remove(locationRetryKey(conversationId)).apply()
    }

    @SuppressLint("ApplySharedPref") // Sign-out must synchronously remove every account-scoped turn.
    @Synchronized
    fun clearAll() {
        preferences.edit().clear().commit()
    }

    private fun queueKey(conversationId: String) = "queue:$conversationId"
    private fun stopKey(conversationId: String) = "stop:$conversationId"
    private fun activeKey(conversationId: String) = "active:$conversationId"
    private fun locationRetryKey(conversationId: String) = "location-retry:$conversationId"

    companion object {
        const val MAX_WAITING_TURNS = 5
    }
}
