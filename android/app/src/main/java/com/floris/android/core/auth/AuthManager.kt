package com.floris.android.core.auth

import com.floris.android.core.model.Identity
import com.floris.android.core.model.MobileSession
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import retrofit2.HttpException

sealed interface AuthState {
    data object Loading : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val identity: Identity) : AuthState
}

class AuthException(message: String, cause: Throwable? = null) : Exception(message, cause)

/**
 * Floris mobile auth adapter (mobile-client-v1):
 *
 *  1. CloudBase email OTP sign-in / refresh (official HTTP API).
 *  2. Exchange the CloudBase access token at POST /auth/mobile/session for a
 *     1-hour Floris Bearer.
 *  3. Floris never issues its own refresh token — expiry is handled by
 *     refreshing CloudBase first, then re-exchanging.
 */
class AuthManager(
    private val cloudBaseApi: CloudBaseAuthApi,
    private val publishableKey: String,
    private val tokenStore: TokenStorage,
    private val json: Json,
    private val exchange: suspend (cloudBaseAccessToken: String) -> MobileSession,
) {
    private val _state = MutableStateFlow<AuthState>(AuthState.Loading)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    @Volatile private var florisToken: String? = null
    @Volatile private var florisExpiresAt: Long = 0
    @Volatile private var cloudBaseAccessToken: String? = null
    @Volatile private var cloudBaseRefreshToken: String? = null
    @Volatile private var cloudBaseExpiresAt: Long = 0

    private val exchangeMutex = Mutex()

    // ---------- Sign-in ----------

    suspend fun sendEmailOtp(email: String) {
        require(email.contains("@")) { "请输入有效的邮箱地址" }
        try {
            cloudBaseApi.sendOtp(publishableKey, OtpRequest(email.trim()))
        } catch (error: Throwable) {
            throw AuthException("验证码发送失败，请稍后重试", error)
        }
    }

    suspend fun verifyEmailOtp(email: String, code: String) {
        val session = try {
            cloudBaseApi.verifyOtp(publishableKey, VerifyRequest(email.trim(), code.trim()))
        } catch (error: Throwable) {
            throw AuthException("验证码无效或已过期", error)
        }
        if (session.access_token.isEmpty()) throw AuthException("CloudBase 未返回访问令牌")
        applyCloudBaseSession(session)
        exchangeAndPersist(session.access_token)
    }

    // ---------- Session restore & refresh ----------

    /** Attempt to restore the persisted session at app start. */
    suspend fun restore(): Boolean {
        val snapshot = tokenStore.load()
        cloudBaseAccessToken = snapshot.cloudBaseAccessToken
        cloudBaseRefreshToken = snapshot.cloudBaseRefreshToken
        cloudBaseExpiresAt = snapshot.cloudBaseExpiresAt
        florisToken = snapshot.florisToken
        florisExpiresAt = snapshot.florisExpiresAt

        val identity = snapshot.identity
        if (snapshot.cloudBaseRefreshToken.isNullOrEmpty()) {
            _state.value = AuthState.SignedOut
            return false
        }
        _state.value = AuthState.SignedIn(identity ?: Identity(auth_type = "cloudbase"))
        // Proactively make sure we hold a fresh Floris token.
        return runCatching { ensureFreshToken() }.isSuccess
    }

    /** Non-suspending read of a currently-valid cached Floris token. */
    fun currentFlorisToken(): String? {
        val token = florisToken ?: return null
        val now = System.currentTimeMillis()
        return token.takeIf { now < florisExpiresAt - TokenStore.REFRESH_MARGIN_MS }
    }

    /** Return a valid Floris token, refreshing CloudBase + re-exchanging if needed. */
    suspend fun requireFlorisToken(): String =
        currentFlorisToken() ?: refreshAndExchange()

    /** Called by the network layer when a request needs a guaranteed-fresh token. */
    suspend fun ensureFreshToken() {
        requireFlorisToken()
    }

    /**
     * Refresh the CloudBase session, then re-exchange for a Floris Bearer.
     * Serialized so concurrent 401s trigger exactly one refresh.
     */
    suspend fun refreshAndExchange(): String = exchangeMutex.withLock {
        currentFlorisToken()?.let { return@withLock it }
        val refreshToken = cloudBaseRefreshToken
            ?: throw AuthException("登录状态已失效，请重新登录")
        val session = try {
            cloudBaseApi.refreshToken(publishableKey, body = RefreshRequest(refreshToken))
        } catch (error: Throwable) {
            if (error is HttpException && error.code() in listOf(400, 401)) {
                forceSignOut()
                throw AuthException("登录状态已失效，请重新登录", error)
            }
            // Network hiccup: fall back to a still-valid CloudBase access token.
            val cached = cloudBaseAccessToken
            if (cached != null && System.currentTimeMillis() < cloudBaseExpiresAt - 60_000) {
                return@withLock exchangeAndPersist(cached)
            }
            throw AuthException("网络异常，无法刷新登录状态", error)
        }
        if (session.access_token.isEmpty()) throw AuthException("CloudBase 刷新失败")
        applyCloudBaseSession(session)
        exchangeAndPersist(session.access_token)
    }

    private suspend fun exchangeAndPersist(cloudBaseAccessToken: String): String {
        val session = exchange(cloudBaseAccessToken)
        if (session.access_token.isEmpty()) throw AuthException("Floris 会话交换失败")
        florisToken = session.access_token
        florisExpiresAt = System.currentTimeMillis() + session.expires_in * 1000
        tokenStore.saveFlorisSession(session.access_token, session.expires_in, session.identity)
        _state.value = AuthState.SignedIn(session.identity)
        return session.access_token
    }

    private suspend fun applyCloudBaseSession(session: CloudBaseSession) {
        cloudBaseAccessToken = session.access_token
        if (session.refresh_token.isNotEmpty()) cloudBaseRefreshToken = session.refresh_token
        cloudBaseExpiresAt = if (session.expires_at > 0) {
            session.expires_at * 1000
        } else {
            System.currentTimeMillis() + session.expires_in * 1000
        }
        tokenStore.saveCloudBaseSession(
            session.access_token,
            session.refresh_token,
            cloudBaseExpiresAt,
        )
    }

    // ---------- Sign-out ----------

    suspend fun signOut() {
        val accessToken = cloudBaseAccessToken
        if (!accessToken.isNullOrEmpty()) {
            runCatching { cloudBaseApi.logout(publishableKey, "Bearer $accessToken") }
        }
        forceSignOut()
    }

    private suspend fun forceSignOut() {
        florisToken = null
        florisExpiresAt = 0
        cloudBaseAccessToken = null
        cloudBaseRefreshToken = null
        cloudBaseExpiresAt = 0
        tokenStore.clear()
        _state.value = AuthState.SignedOut
    }
}

/** Builds the /auth/mobile/session exchange call used by [AuthManager]. */
fun mobileSessionExchange(
    call: suspend (body: kotlinx.serialization.json.JsonObject) -> MobileSession,
): suspend (String) -> MobileSession = { accessToken ->
    call(buildJsonObject { put("access_token", accessToken) })
}
