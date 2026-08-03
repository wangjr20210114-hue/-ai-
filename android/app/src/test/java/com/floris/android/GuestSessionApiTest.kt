package com.floris.android

import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.CloudBaseAuthApi
import com.floris.android.core.auth.GuestSession
import com.floris.android.core.auth.TokenStorage
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.model.Identity
import com.floris.android.core.model.MobileSession
import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.core.network.sse.ChatEventDispatcher
import com.floris.android.core.network.sse.SseParser
import kotlinx.serialization.json.Json
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

/**
 * 游客会话的接口级验证：用 MockWebServer 复现线上真实报文
 * （已通过 floris-dev.jlutx.com 抓取核对）：
 *
 *  - GET /auth/session 不带凭证时用 Set-Cookie 下发 auth_type=guest 的 JWT；
 *  - 该 JWT 以 `Authorization: Bearer` 发给 /chat 即可放行；
 *  - /chat 的正文事件名为 `token`，data.type 为 `ai_response`，
 *    正文在顶层 `content` 字段（不在 payload 里）；
 *  - 游客越权访问受限能力时返回 403 + code=LOGIN_REQUIRED。
 */
class GuestSessionApiTest {

    private lateinit var server: MockWebServer
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    /** 线上抓到的真实 Set-Cookie 形态。 */
    private val guestCookie =
        "floris_session=eyJhbGciOiJIUzI1NiJ9.eyJhdXRoX3R5cGUiOiJndWVzdCJ9.sig; " +
            "Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=604800"

    private val guestBody = """
        {"identity":{"username":"guest","display_name":"游客","auth_type":"guest",
        "membership":"guest","roles":["guest"]},
        "entitlements":{"plan":"guest","limits":{"searchDepth":"basic","dailyTokens":20000},
        "payment_available":false}}
    """.trimIndent()

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    // ---------- GET /auth/session ----------

    @Test
    fun `guest session endpoint returns identity and cookie token`() {
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setHeader("Set-Cookie", guestCookie)
                .setBody(guestBody),
        )

        val response = OkHttpClient().newCall(
            Request.Builder().url(server.url("auth/session")).get().build(),
        ).execute()

        assertEquals(200, response.code)
        val cookie = response.header("Set-Cookie").orEmpty()
        val token = cookie.substringAfter("floris_session=").substringBefore(';')
        assertTrue("游客 token 必须非空", token.isNotEmpty())
        assertEquals(604800L, Regex("Max-Age=(\\d+)").find(cookie)!!.groupValues[1].toLong())

        val identity = json.decodeFromString(
            GuestEnvelope.serializer(),
            response.body!!.string(),
        ).identity
        assertEquals("guest", identity.auth_type)
        assertEquals("guest", identity.membership)
        response.close()
    }

    @kotlinx.serialization.Serializable
    private data class GuestEnvelope(val identity: Identity)

    // ---------- 游客 token 用于 /chat ----------

    @Test
    fun `guest bearer is attached to chat and stream is parsed`() = runBlockingTest {
        val storage = FakeStorage()
        val auth = guestAuthManager(storage, token = "guest-jwt")
        auth.signInAsGuest()

        // 线上真实 SSE 报文：事件名 token，data.type = ai_response。
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "text/event-stream")
                .setBody(
                    "event: progress_event\n" +
                        "data: {\"type\":\"progress_event\",\"payload\":" +
                        "{\"stage\":\"synthesis\",\"status\":\"active\",\"activity\":\"general\"}}\n\n" +
                        "event: token\n" +
                        "data: {\"type\":\"ai_response\",\"content\":\"我是 FLORIS。\"}\n\n" +
                        "event: done\n" +
                        "data: {\"type\":\"answer_complete\",\"payload\":{\"turn_id\":\"t-1\"}}\n\n",
                ),
        )

        val client = OkHttpClient()
        val request = Request.Builder()
            .url(server.url("chat"))
            .header("Authorization", "Bearer ${auth.currentFlorisToken()}")
            .header("makers-conversation-id", "conv-guest-1")
            .header("Accept", "text/event-stream")
            .post(jsonBody("""{"message":"你好"}"""))
            .build()

        val response = client.newCall(request).execute()
        assertEquals(200, response.code)

        val recorded = server.takeRequest()
        assertEquals("Bearer guest-jwt", recorded.getHeader("Authorization"))
        assertEquals("conv-guest-1", recorded.getHeader("makers-conversation-id"))

        // 逐行喂给解析器：验证不需要凑满固定字节也能立刻切出事件。
        val dispatcher = ChatEventDispatcher(json)
        val events = mutableListOf<ChatEvent>()
        var buffer = ""
        response.body!!.source().use { source ->
            while (true) {
                val line = source.readUtf8Line() ?: break
                buffer += line + "\n"
                val split = SseParser.split(buffer)
                buffer = split.rest
                split.frames.forEach { events += dispatcher.dispatch(it) }
            }
            SseParser.flush(buffer)?.let { events += dispatcher.dispatch(it) }
        }

        val answer = events.filterIsInstance<ChatEvent.AiResponse>()
        assertEquals(1, answer.size)
        assertEquals("我是 FLORIS。", answer.first().content)
        assertTrue(events.any { it is ChatEvent.Progress })
        assertEquals("t-1", events.filterIsInstance<ChatEvent.AnswerComplete>().first().turnId)
    }

    // ---------- 游客越权 ----------

    @Test
    fun `restricted capability returns login required for guests`() {
        server.enqueue(
            MockResponse().setResponseCode(403)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"error":"请先登录后使用此 Skill","code":"LOGIN_REQUIRED"}"""),
        )

        val response = OkHttpClient().newCall(
            Request.Builder()
                .url(server.url("skills"))
                .header("Authorization", "Bearer guest-jwt")
                .post(jsonBody("""{"operation":"set_enabled","skill_id":"paper-research"}"""))
                .build(),
        ).execute()

        assertEquals(403, response.code)
        val body = response.body!!.string()
        assertTrue(body.contains("LOGIN_REQUIRED"))
        assertTrue(body.contains("请先登录"))
        response.close()
    }

    /** 契约 guest_skill_ids 与客户端硬编码保持一致。 */
    @Test
    fun `guest skill ids match the entitlement contract`() {
        // contracts/entitlements.v1.json: ["core", "proactive-agent"]
        assertEquals(setOf("core", "proactive-agent"), guestSkillIds())
    }

    private fun guestSkillIds(): Set<String> = setOf("core", "proactive-agent")

    // ---------- helpers ----------

    private fun jsonBody(content: String) =
        content.toRequestBody("application/json".toMediaType())

    private fun guestAuthManager(storage: TokenStorage, token: String): AuthManager {
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
            exchange = { error("正式登录不参与本用例") },
            guestExchange = {
                GuestSession(
                    token = token,
                    expiresAt = System.currentTimeMillis() + 604_800_000,
                    identity = Identity(auth_type = "guest", membership = "guest"),
                )
            },
        )
    }

    private fun runBlockingTest(block: suspend () -> Unit) =
        kotlinx.coroutines.runBlocking { block() }

    private class FakeStorage : TokenStorage {
        private var snapshot = TokenStore.Snapshot(null, null, 0, null, 0, null, false)
        override suspend fun load() = snapshot
        override suspend fun saveCloudBaseSession(a: String, r: String, e: Long) {}
        override suspend fun saveFlorisSession(token: String, expiresIn: Long, identity: Identity?) {}
        override suspend fun saveGuestSession(token: String, expiresAt: Long, identity: Identity?) {
            snapshot = snapshot.copy(
                florisToken = token, florisExpiresAt = expiresAt,
                identity = identity, isGuest = true,
            )
        }
        override suspend fun savePendingVerification(email: String, id: String) {}
        override suspend fun loadPendingVerification(): Pair<String, String>? = null
        override suspend fun clearPendingVerification() {}
        override suspend fun clear() {
            snapshot = TokenStore.Snapshot(null, null, 0, null, 0, null, false)
        }
    }
}
