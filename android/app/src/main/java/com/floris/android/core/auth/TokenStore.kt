package com.floris.android.core.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.floris.android.core.model.Identity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json

private val Context.authDataStore by preferencesDataStore(name = "floris_auth")

/** Storage contract used by [AuthManager]; fakeable in unit tests. */
interface TokenStorage {
    suspend fun load(): TokenStore.Snapshot
    suspend fun saveCloudBaseSession(accessToken: String, refreshToken: String, expiresAt: Long)
    suspend fun saveFlorisSession(token: String, expiresInSeconds: Long, identity: Identity?)
    suspend fun savePendingVerification(email: String, verificationId: String)
    suspend fun loadPendingVerification(): Pair<String, String>?
    suspend fun clearPendingVerification()
    suspend fun clear()
}

/**
 * Persists the CloudBase refresh token and the short-lived Floris Bearer.
 * The CloudBase refresh token is the only durable credential (mobile-client-v1).
 */
class TokenStore(
    private val context: Context,
    private val json: Json,
) : TokenStorage {
    private object Keys {
        val CB_ACCESS = stringPreferencesKey("cloudbase_access_token")
        val CB_REFRESH = stringPreferencesKey("cloudbase_refresh_token")
        val CB_EXPIRES_AT = longPreferencesKey("cloudbase_expires_at")
        val FLORIS_TOKEN = stringPreferencesKey("floris_token")
        val FLORIS_EXPIRES_AT = longPreferencesKey("floris_expires_at")
        val IDENTITY = stringPreferencesKey("identity_json")
        val CONVERSATION_ID = stringPreferencesKey("active_conversation_id")
        val SEARCH_CONVERSATION_ID = stringPreferencesKey("search_conversation_id")
        val PENDING_EMAIL = stringPreferencesKey("pending_otp_email")
        val PENDING_VERIFICATION = stringPreferencesKey("pending_verification_id")
    }

    @Volatile private var cachedFlorisToken: String? = null
    @Volatile private var cachedFlorisExpiry: Long = 0
    private val cacheMutex = Mutex()

    data class Snapshot(
        val cloudBaseAccessToken: String?,
        val cloudBaseRefreshToken: String?,
        val cloudBaseExpiresAt: Long,
        val florisToken: String?,
        val florisExpiresAt: Long,
        val identity: Identity?,
    )

    override suspend fun load(): Snapshot {
        val prefs = context.authDataStore.data.first()
        val identity = prefs[Keys.IDENTITY]?.let {
            runCatching { json.decodeFromString(Identity.serializer(), it) }.getOrNull()
        }
        cacheMutex.withLock {
            cachedFlorisToken = prefs[Keys.FLORIS_TOKEN]
            cachedFlorisExpiry = prefs[Keys.FLORIS_EXPIRES_AT] ?: 0
        }
        return Snapshot(
            cloudBaseAccessToken = prefs[Keys.CB_ACCESS],
            cloudBaseRefreshToken = prefs[Keys.CB_REFRESH],
            cloudBaseExpiresAt = prefs[Keys.CB_EXPIRES_AT] ?: 0,
            florisToken = prefs[Keys.FLORIS_TOKEN],
            florisExpiresAt = prefs[Keys.FLORIS_EXPIRES_AT] ?: 0,
            identity = identity,
        )
    }

    override suspend fun saveCloudBaseSession(accessToken: String, refreshToken: String, expiresAt: Long) {
        context.authDataStore.edit {
            it[Keys.CB_ACCESS] = accessToken
            if (refreshToken.isNotEmpty()) it[Keys.CB_REFRESH] = refreshToken
            it[Keys.CB_EXPIRES_AT] = expiresAt
        }
    }

    override suspend fun saveFlorisSession(token: String, expiresInSeconds: Long, identity: Identity?) {
        val expiresAt = System.currentTimeMillis() + expiresInSeconds * 1000
        cacheMutex.withLock {
            cachedFlorisToken = token
            cachedFlorisExpiry = expiresAt
        }
        context.authDataStore.edit {
            it[Keys.FLORIS_TOKEN] = token
            it[Keys.FLORIS_EXPIRES_AT] = expiresAt
            identity?.let { id -> it[Keys.IDENTITY] = json.encodeToString(Identity.serializer(), id) }
        }
    }

    fun cachedFlorisToken(now: Long = System.currentTimeMillis()): String? =
        cachedFlorisToken?.takeIf { now < cachedFlorisExpiry - REFRESH_MARGIN_MS }

    suspend fun activeConversationId(): String? =
        context.authDataStore.data.first()[Keys.CONVERSATION_ID]

    suspend fun saveActiveConversationId(id: String) {
        context.authDataStore.edit { it[Keys.CONVERSATION_ID] = id }
    }

    suspend fun searchConversationId(): String? =
        context.authDataStore.data.first()[Keys.SEARCH_CONVERSATION_ID]

    suspend fun saveSearchConversationId(id: String) {
        context.authDataStore.edit { it[Keys.SEARCH_CONVERSATION_ID] = id }
    }

    override suspend fun savePendingVerification(email: String, verificationId: String) {
        context.authDataStore.edit {
            it[Keys.PENDING_EMAIL] = email
            it[Keys.PENDING_VERIFICATION] = verificationId
        }
    }

    override suspend fun loadPendingVerification(): Pair<String, String>? {
        val prefs = context.authDataStore.data.first()
        val email = prefs[Keys.PENDING_EMAIL]
        val verificationId = prefs[Keys.PENDING_VERIFICATION]
        return if (!email.isNullOrEmpty() && !verificationId.isNullOrEmpty()) {
            email to verificationId
        } else null
    }

    override suspend fun clearPendingVerification() {
        context.authDataStore.edit {
            it.remove(Keys.PENDING_EMAIL)
            it.remove(Keys.PENDING_VERIFICATION)
        }
    }

    override suspend fun clear() {
        cacheMutex.withLock {
            cachedFlorisToken = null
            cachedFlorisExpiry = 0
        }
        context.authDataStore.edit { it.clear() }
    }

    companion object {
        /** Consider tokens stale 5 minutes before real expiry. */
        const val REFRESH_MARGIN_MS = 5 * 60 * 1000L
    }
}
