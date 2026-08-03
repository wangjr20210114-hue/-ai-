package com.floris.android

import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.auth.CloudBaseAuthApi
import com.floris.android.core.auth.TokenStorage
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.model.Identity
import com.floris.android.core.model.MobileSession
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthManagerTest {

    private lateinit var server: MockWebServer
    private val json = Json { ignoreUnknownKeys = true }

    private class FakeTokenStorage(var snapshot: TokenStore.Snapshot = empty()) : TokenStorage {
        var cleared = false
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
            )
        }
        override suspend fun clear() {
            cleared = true
            snapshot = empty()
        }

        companion object {
            fun empty() = TokenStore.Snapshot(null, null, 0, null, 0, null)
        }
    }

    @Before fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After fun tearDown() = server.shutdown()

    private fun manager(storage: FakeTokenStorage): AuthManager {
        val api = CloudBaseAuthApi.create(server.url("/").toString(), json)
        return AuthManager(api, "publishable-key", storage, json) { accessToken ->
            // Simulated POST /auth/mobile/session against the mock server.
            val client = OkHttpClient()
            val body = buildJsonObject { put("access_token", accessToken) }
                .toString().toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url(server.url("auth/mobile/session"))
                .post(body)
                .build()
            client.newCall(request).execute().use { response ->
                check(response.isSuccessful) { "exchange failed: ${response.code}" }
                json.decodeFromString(MobileSession.serializer(), response.body!!.string())
            }
        }
    }

    private fun cloudBaseSessionJson(access: String, refresh: String) = """
        {"access_token":"$access","refresh_token":"$refresh","token_type":"bearer","expires_in":3600}
    """.trimIndent()

    private fun mobileSessionJson(token: String) = """
        {"access_token":"$token","token_type":"Bearer","expires_in":3600,"contract_version":"1",
         "identity":{"id":"u1","subject_id":"s1","tenant_id":"t1","auth_type":"cloudbase",
         "membership":"plus","display_name":"测试用户"}}
    """.trimIndent()

    @Test
    fun `email otp login exchanges cloudbase token for floris bearer`() = runTest {
        val storage = FakeTokenStorage()
        val auth = manager(storage)

        server.enqueue(MockResponse().setResponseCode(200)) // otp
        server.enqueue(MockResponse().setBody(cloudBaseSessionJson("cb-access", "cb-refresh")))
        server.enqueue(MockResponse().setBody(mobileSessionJson("floris-token-1")))

        auth.sendEmailOtp("user@example.com")
        auth.verifyEmailOtp("user@example.com", "123456")

        assertEquals("floris-token-1", auth.currentFlorisToken())
        assertTrue(auth.state.value is AuthState.SignedIn)
        assertEquals("测试用户", (auth.state.value as AuthState.SignedIn).identity.display_name)
        assertEquals("cb-refresh", storage.snapshot.cloudBaseRefreshToken)

        // Verify the exchange request carried the CloudBase access token.
        assertTrue(server.takeRequest().path!!.startsWith("/auth/v1/otp"))
        assertTrue(server.takeRequest().path!!.startsWith("/auth/v1/verify"))
        val exchangeRequest = server.takeRequest()
        assertTrue(exchangeRequest.path!!.startsWith("/auth/mobile/session"))
        assertTrue(exchangeRequest.body.readUtf8().contains("cb-access"))
    }

    @Test
    fun `restore with refresh token refreshes cloudbase then re-exchanges`() = runTest {
        val storage = FakeTokenStorage(
            FakeTokenStorage.empty().copy(
                cloudBaseRefreshToken = "saved-refresh",
                identity = Identity(id = "u1", subject_id = "s1", tenant_id = "t1", auth_type = "cloudbase", membership = "free"),
            ),
        )
        val auth = manager(storage)

        server.enqueue(MockResponse().setBody(cloudBaseSessionJson("cb-access-2", "cb-refresh-2")))
        server.enqueue(MockResponse().setBody(mobileSessionJson("floris-token-2")))

        assertTrue(auth.restore())
        assertEquals("floris-token-2", auth.currentFlorisToken())

        val refreshRequest = server.takeRequest()
        assertTrue(refreshRequest.path!!.contains("/auth/v1/token"))
        assertTrue(refreshRequest.path!!.contains("grant_type=refresh_token"))
        assertTrue(refreshRequest.body.readUtf8().contains("saved-refresh"))
    }

    @Test
    fun `restore without refresh token signs out`() = runTest {
        val auth = manager(FakeTokenStorage())
        assertTrue(!auth.restore())
        assertEquals(AuthState.SignedOut, auth.state.value)
    }

    @Test
    fun `expired floris token triggers single refresh and re-exchange`() = runTest {
        val storage = FakeTokenStorage(
            FakeTokenStorage.empty().copy(
                cloudBaseRefreshToken = "saved-refresh",
                // Floris token already expired.
                florisToken = "stale-token",
                florisExpiresAt = System.currentTimeMillis() - 10_000,
            ),
        )
        val auth = manager(storage)

        server.enqueue(MockResponse().setBody(cloudBaseSessionJson("cb-access-3", "cb-refresh-3")))
        server.enqueue(MockResponse().setBody(mobileSessionJson("floris-token-3")))

        assertTrue(auth.restore())
        val token = auth.requireFlorisToken()
        assertEquals("floris-token-3", token)
        // Exactly two calls: one CloudBase refresh + one Floris exchange.
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `invalid refresh token forces sign out`() = runTest {
        val storage = FakeTokenStorage(
            FakeTokenStorage.empty().copy(cloudBaseRefreshToken = "bad-refresh"),
        )
        val auth = manager(storage)
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"invalid"}"""))

        val result = runCatching { auth.restore() }
        assertTrue(result.isFailure || !result.getOrDefault(false))
        assertEquals(AuthState.SignedOut, auth.state.value)
        assertTrue(storage.cleared)
    }

    @Test
    fun `sign out clears stored credentials`() = runTest {
        val storage = FakeTokenStorage(
            FakeTokenStorage.empty().copy(
                cloudBaseAccessToken = "cb-access",
                cloudBaseRefreshToken = "cb-refresh",
                florisToken = "floris-token",
                florisExpiresAt = System.currentTimeMillis() + 3_600_000,
            ),
        )
        val auth = manager(storage)
        server.enqueue(MockResponse().setResponseCode(204))
        auth.signOut()
        assertEquals(AuthState.SignedOut, auth.state.value)
        assertEquals(null, auth.currentFlorisToken())
        assertTrue(storage.cleared)
    }
}
