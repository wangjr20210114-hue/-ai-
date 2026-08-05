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
    suspend fun saveGuestSession(token: String, expiresAt: Long, identity: Identity?)
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
    private val credentials = SecureCredentialStore(context)

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
        val IS_GUEST = stringPreferencesKey("session_is_guest")
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
        val isGuest: Boolean = false,
    )

    override suspend fun load(): Snapshot {
        val prefs = context.authDataStore.data.first()
        migrateLegacyCredentials(prefs)
        val identity = prefs[Keys.IDENTITY]?.let {
            runCatching { json.decodeFromString(Identity.serializer(), it) }.getOrNull()
        }
        val cloudBaseAccess = credentials.read(SecureCredentialStore.CLOUD_BASE_ACCESS)
        val cloudBaseRefresh = credentials.read(SecureCredentialStore.CLOUD_BASE_REFRESH)
        val florisToken = credentials.read(SecureCredentialStore.FLORIS_BEARER)
        cacheMutex.withLock {
            cachedFlorisToken = florisToken
            cachedFlorisExpiry = prefs[Keys.FLORIS_EXPIRES_AT] ?: 0
        }
        return Snapshot(
            cloudBaseAccessToken = cloudBaseAccess,
            cloudBaseRefreshToken = cloudBaseRefresh,
            cloudBaseExpiresAt = prefs[Keys.CB_EXPIRES_AT] ?: 0,
            florisToken = florisToken,
            florisExpiresAt = prefs[Keys.FLORIS_EXPIRES_AT] ?: 0,
            identity = identity,
            isGuest = prefs[Keys.IS_GUEST] == "1",
        )
    }

    override suspend fun saveCloudBaseSession(accessToken: String, refreshToken: String, expiresAt: Long) {
        credentials.write(SecureCredentialStore.CLOUD_BASE_ACCESS, accessToken)
        if (refreshToken.isNotEmpty()) {
            credentials.write(SecureCredentialStore.CLOUD_BASE_REFRESH, refreshToken)
        }
        context.authDataStore.edit {
            it[Keys.CB_EXPIRES_AT] = expiresAt
            removeLegacyCredentials(it)
        }
    }

    override suspend fun saveFlorisSession(token: String, expiresInSeconds: Long, identity: Identity?) {
        val expiresAt = System.currentTimeMillis() + expiresInSeconds * 1000
        cacheMutex.withLock {
            cachedFlorisToken = token
            cachedFlorisExpiry = expiresAt
        }
        credentials.write(SecureCredentialStore.FLORIS_BEARER, token)
        context.authDataStore.edit {
            it[Keys.FLORIS_EXPIRES_AT] = expiresAt
            it[Keys.IS_GUEST] = "0"
            identity?.let { id -> it[Keys.IDENTITY] = json.encodeToString(Identity.serializer(), id) }
            removeLegacyCredentials(it)
        }
    }

    /**
     * 游客会话：token 直接来自 GET /auth/session 的 floris_session cookie，
     * 后端签发 7 天有效期，没有 refresh token，所以到期后重新领一枚即可。
     */
    override suspend fun saveGuestSession(token: String, expiresAt: Long, identity: Identity?) {
        cacheMutex.withLock {
            cachedFlorisToken = token
            cachedFlorisExpiry = expiresAt
        }
        credentials.write(SecureCredentialStore.FLORIS_BEARER, token)
        credentials.remove(SecureCredentialStore.CLOUD_BASE_ACCESS)
        credentials.remove(SecureCredentialStore.CLOUD_BASE_REFRESH)
        context.authDataStore.edit {
            it[Keys.FLORIS_EXPIRES_AT] = expiresAt
            it[Keys.IS_GUEST] = "1"
            it.remove(Keys.CB_EXPIRES_AT)
            identity?.let { id -> it[Keys.IDENTITY] = json.encodeToString(Identity.serializer(), id) }
            removeLegacyCredentials(it)
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
        credentials.clear()
        context.authDataStore.edit { it.clear() }
    }

    /** One-time, lossless migration from pre-Keystore Android builds. */
    private suspend fun migrateLegacyCredentials(
        prefs: androidx.datastore.preferences.core.Preferences,
    ) {
        val legacy = listOf(
            Triple(Keys.CB_ACCESS, SecureCredentialStore.CLOUD_BASE_ACCESS, prefs[Keys.CB_ACCESS]),
            Triple(Keys.CB_REFRESH, SecureCredentialStore.CLOUD_BASE_REFRESH, prefs[Keys.CB_REFRESH]),
            Triple(Keys.FLORIS_TOKEN, SecureCredentialStore.FLORIS_BEARER, prefs[Keys.FLORIS_TOKEN]),
        )
        legacy.forEach { (_, secureKey, value) ->
            if (!value.isNullOrEmpty() && credentials.read(secureKey).isNullOrEmpty()) {
                credentials.write(secureKey, value)
            }
        }
        if (legacy.any { (_, _, value) -> value != null }) {
            context.authDataStore.edit(::removeLegacyCredentials)
        }
    }

    private fun removeLegacyCredentials(
        prefs: androidx.datastore.preferences.core.MutablePreferences,
    ) {
        prefs.remove(Keys.CB_ACCESS)
        prefs.remove(Keys.CB_REFRESH)
        prefs.remove(Keys.FLORIS_TOKEN)
    }

    companion object {
        /** Consider tokens stale 5 minutes before real expiry. */
        const val REFRESH_MARGIN_MS = 5 * 60 * 1000L
    }
}
