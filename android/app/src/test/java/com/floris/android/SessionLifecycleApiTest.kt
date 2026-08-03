package com.floris.android

import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.auth.CloudBaseAuthApi
import com.floris.android.core.auth.GuestSession
import com.floris.android.core.auth.TokenStorage
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.model.Identity
import com.floris.android.core.model.MobileSession
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * 会话生命周期的接口级验证：
 * 游客 → 正式登录 → 退出 → 一键恢复，每一步的身份与凭证都必须正确。
 *
 * 覆盖用户反馈的三个问题：
 *  #5 登录后技能页仍把用户当游客（身份没有随AuthState 更新）；
 *  #7 退出登录后仍停在验证码页（登录页状态没有重置）；
 *  #9 cookie 未过期时能否一键登录历史账号。
 */
class SessionLifecycleApiTest {

    private lateinit var server: MockWebServer
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    // ---------- 可观测的假存储 ----------

    private class FakeStorage(
        var snapshot: TokenStore.Snapshot = empty(),
    ) : TokenStorage {
        var cleared = false
        private var pending: Pair<String, String>? = null

        override suspend fun load() = snapshot

        override suspend fun saveCloudBaseSession(accessToken: String, refreshToken: String, expiresAt: Long) {
            snapshot = snapshot.copy(
                cloudBaseAccessToken = accessToken,
                cloudBaseRefreshToken = refreshToken.ifEmpty { snapshot.cloudBaseRefreshToken },
                cloudBaseExpiresAt = expiresAt,
            )
        }

        override suspend fun saveFlorisSession(token: String, expiresInSeconds: Long, identity: Identity?) {
            snapshot = snapshot.copy(
                florisToken = token,
                florisExpiresAt = System.currentTimeMillis() + expiresInSeconds * 1000,
                identity = identity ?: snapshot.identity,
                isGuest = false,
            )
        }

        override suspend fun saveGuestSession(token: String, expiresAt: Long, identity: Identity?) {
            snapshot = snapshot.copy(
                cloudBaseAccessToken = null,
                cloudBaseRefreshToken = null,
                cloudBaseExpiresAt = 0,
                florisToken = token,
                florisExpiresAt = expiresAt,
                identity = identity ?: snapshot.identity,
                isGuest = true,
            )
        }

        override suspend fun savePendingVerification(email: String, verificationId: String) {
            pending = email to verificationId
        }

        override suspend fun loadPendingVerification() = pending
        override suspend fun clearPendingVerification() { pending = null }

        override suspend fun clear() {
            cleared = true
            pending = null
            snapshot = empty()
        }

        companion object {
            fun empty() = TokenStore.Snapshot(null, null, 0, null, 0, null, false)
        }
    }

    private fun manager(
        storage: TokenStorage,
        guestToken: String = "guest-jwt",
    ): AuthManager {
        val api = CloudBaseAuthApi.create(
            baseUrl = server.url("/").toString(),
            envId = "test-env",
            publishableKey = "key",
            json = json,
        )
        return AuthManager(
            cloudBaseApi = api,
            envId = "test-env",
            tokenStore = storage,
            json = json,
            exchange = { accessToken ->
                val body = """{"access_token":"$accessToken"}"""
                    .toRequestBody("application/json".toMediaType())
                OkHttpClient().newCall(
                    Request.Builder().url(server.url("auth/mobile/session")).post(body).build(),
                ).execute().use { response ->
                    check(response.isSuccessful) { "exchange failed ${response.code}" }
                    json.decodeFromString(MobileSession.serializer(), response.body!!.string())
                }
            },
            guestExchange = {
                GuestSession(
                    token = guestToken,
                    expiresAt = System.currentTimeMillis() + 604_800_000,
                    identity = Identity(auth_type = "guest", membership = "guest"),
                )
            },
        )
    }

    // ---------- #5 身份切换必须体现在 AuthState ----------

    @Test
    fun `guest then email sign in flips identity to cloudbase`() = runTest {
        val storage = FakeStorage()
        val auth = manager(storage)

        auth.signInAsGuest()
        assertEquals("guest", (auth.state.value as AuthState.SignedIn).identity.auth_type)
        assertTrue(auth.isGuest)

        // 正式登录：OTP → verify → signin → 换 Floris Bearer
        server.enqueue(MockResponse().setBody("""{"verification_id":"vid-1"}"""))
        server.enqueue(MockResponse().setBody("""{"verification_token":"vtok-1"}"""))
        server.enqueue(
            MockResponse().setBody(
                """{"access_token":"cb-access","refresh_token":"cb-refresh","expires_in":7200}""",
            ),
        )
        server.enqueue(
            MockResponse().setBody(
                """{"access_token":"floris-jwt","expires_in":3600,
                    "identity":{"auth_type":"cloudbase","membership":"free"}}""",
            ),
        )

        auth.sendEmailOtp("me@example.com")
        auth.verifyEmailOtp("me@example.com", "123456")

        // 关键：身份必须翻成 cloudbase，isGuest 必须归位。
        val identity = (auth.state.value as AuthState.SignedIn).identity
        assertEquals("cloudbase", identity.auth_type)
        assertFalse("登录后不能再被当作游客", auth.isGuest)
        assertFalse(storage.snapshot.isGuest)
        assertEquals("floris-jwt", auth.currentFlorisToken())
    }

    @Test
    fun `auth state emits signed out after sign out`() = runTest {
        val storage = FakeStorage()
        val auth = manager(storage)
        auth.signInAsGuest()
        assertTrue(auth.state.value is AuthState.SignedIn)

        auth.signOut()

        // #7 的前提：登录页据此把自己重置回邮箱输入步骤。
        assertTrue(auth.state.value is AuthState.SignedOut)
        assertNull(auth.currentFlorisToken())
        assertTrue(storage.cleared)
    }

    // ---------- #7 退出后不得残留待验证状态 ----------

    @Test
    fun `sign out clears pending verification`() = runTest {
        val storage = FakeStorage()
        val auth = manager(storage)

        server.enqueue(MockResponse().setBody("""{"verification_id":"vid-2"}"""))
        auth.sendEmailOtp("me@example.com")
        assertEquals("me@example.com", storage.loadPendingVerification()?.first)

        auth.signOut()

        // 待验证记录必须一起清掉，否则重进会直接落在验证码那一屏。
        assertNull("退出后不得残留待验证的邮箱", storage.loadPendingVerification())
    }

    // ---------- #9 未过期即可一键恢复 ----------

    @Test
    fun `valid cached session restores without any network call`() = runTest {
        val storage = FakeStorage(
            FakeStorage.empty().copy(
                cloudBaseRefreshToken = "cb-refresh",
                florisToken = "still-valid",
                florisExpiresAt = System.currentTimeMillis() + 3_600_000,
                identity = Identity(auth_type = "cloudbase", membership = "pro"),
            ),
        )
        val auth = manager(storage)

        assertTrue("未过期就该直接进入", auth.restore())
        assertEquals("still-valid", auth.currentFlorisToken())
        assertEquals("pro", (auth.state.value as AuthState.SignedIn).identity.membership)
        assertEquals("有效期内不该有任何网络往返", 0, server.requestCount)
    }

    @Test
    fun `expired bearer is renewed through the refresh token`() = runTest {
        val storage = FakeStorage(
            FakeStorage.empty().copy(
                cloudBaseRefreshToken = "cb-refresh",
                florisToken = "expired",
                florisExpiresAt = System.currentTimeMillis() - 1_000,
                identity = Identity(auth_type = "cloudbase"),
            ),
        )
        val auth = manager(storage)

        server.enqueue(
            MockResponse().setBody(
                """{"access_token":"cb-access-2","refresh_token":"cb-refresh-2","expires_in":7200}""",
            ),
        )
        server.enqueue(
            MockResponse().setBody(
                """{"access_token":"floris-jwt-2","expires_in":3600,
                    "identity":{"auth_type":"cloudbase"}}""",
            ),
        )

        assertTrue(auth.restore())
        assertEquals("floris-jwt-2", auth.currentFlorisToken())
        // 刷新用的是持久化的 refresh token，用户无需重新输验证码。
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `guest session survives a restart while unexpired`() = runTest {
        val storage = FakeStorage(
            FakeStorage.empty().copy(
                florisToken = "guest-saved",
                florisExpiresAt = System.currentTimeMillis() + 604_800_000,
                identity = Identity(auth_type = "guest", membership = "guest"),
                isGuest = true,
            ),
        )
        val auth = manager(storage)

        assertTrue(auth.restore())
        assertTrue(auth.isGuest)
        assertEquals("guest-saved", auth.currentFlorisToken())
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `no credentials means signed out`() = runTest {
        val auth = manager(FakeStorage())
        assertFalse(auth.restore())
        assertTrue(auth.state.value is AuthState.SignedOut)
        assertEquals(0, server.requestCount)
    }
}
