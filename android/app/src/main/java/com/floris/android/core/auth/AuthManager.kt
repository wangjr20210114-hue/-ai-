package com.floris.android.core.auth

import com.floris.android.core.model.Identity
import com.floris.android.core.model.MobileSession
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
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
 *  1. CloudBase email OTP sign-in / refresh (official HTTP API, same wire
 *     protocol as @cloudbase/js-sdk 3.7.0).
 *  2. Exchange the CloudBase access token at POST /auth/mobile/session for a
 *     1-hour Floris Bearer.
 *  3. Floris never issues its own refresh token — expiry is handled by
 *     refreshing CloudBase first, then re-exchanging.
 */
class AuthManager(
    private val cloudBaseApi: CloudBaseAuthApi,
    private val envId: String,
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
        val normalized = email.trim()
        require(normalized.contains("@")) { "请输入有效的邮箱地址" }
        val response = try {
            cloudBaseApi.sendVerification(VerificationRequest(normalized))
        } catch (error: Throwable) {
            throw AuthException("验证码发送失败，请检查网络后重试", error)
        }
        if (response.error_code != null || response.verification_id.isEmpty()) {
            throw AuthException(response.error_description ?: "验证码发送失败，请稍后重试")
        }
        tokenStore.savePendingVerification(normalized, response.verification_id)
    }

    suspend fun verifyEmailOtp(email: String, code: String) {
        val pending = tokenStore.loadPendingVerification()
        val verificationId = pending?.second
            ?: throw AuthException("请先获取邮箱验证码")
        val verified = try {
            cloudBaseApi.verifyCode(
                envId,
                VerifyCodeRequest(verificationId, code.trim()),
            )
        } catch (error: Throwable) {
            throw AuthException("验证码校验失败，请稍后重试", error)
        }
        if (verified.error_code != null || verified.verification_token.isEmpty()) {
            throw AuthException("验证码无效或已过期")
        }

        val session = signInOrUp(email.trim(), verified.verification_token)
        if (session.error_code != null || session.access_token.isEmpty()) {
            throw AuthException(session.error_description ?: "CloudBase 登录失败")
        }
        tokenStore.clearPendingVerification()
        applyCloudBaseSession(session)
        exchangeAndPersist(session.access_token)
    }

    /** Existing accounts sign in; unknown accounts are created (shouldCreateUser). */
    private suspend fun signInOrUp(email: String, verificationToken: String): CloudBaseSession {
        val signIn = runCatching {
            cloudBaseApi.signIn(envId, SignInRequest(email, verificationToken))
        }.getOrNull()
        if (signIn != null && signIn.error_code == null && signIn.access_token.isNotEmpty()) {
            return signIn
        }
        return try {
            cloudBaseApi.signUp(envId, SignUpRequest(email, verificationToken))
        } catch (error: Throwable) {
            signIn ?: throw AuthException("CloudBase 登录失败", error)
        }
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
            cloudBaseApi.refreshToken(
                envId,
                RefreshRequest(client_id = envId, refresh_token = refreshToken),
            )
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
        if (session.error_code != null || session.access_token.isEmpty()) {
            forceSignOut()
            throw AuthException("登录状态已失效，请重新登录")
        }
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
        cloudBaseExpiresAt = session.resolvedExpiresAt()
        tokenStore.saveCloudBaseSession(
            session.access_token,
            session.refresh_token,
            cloudBaseExpiresAt,
        )
    }

    // ---------- Sign-out ----------

    suspend fun signOut() {
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
    call(
        kotlinx.serialization.json.buildJsonObject {
            put("access_token", kotlinx.serialization.json.JsonPrimitive(accessToken))
        },
    )
}
