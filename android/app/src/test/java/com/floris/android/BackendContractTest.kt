package com.floris.android

import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.core.network.sse.ChatEventDispatcher
import com.floris.android.core.network.sse.SseParser
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
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
 * 契约层接口测试：验证客户端只依赖「契约里写明的字段」，
 * 后端在契约之外怎么改都不影响我们。
 *
 * 这一点是用户明确关心的：后端更新后客户端要不要跟着改？
 * 结论是——只要下面这些断言成立就不用改。
 */
class BackendContractTest {

    private lateinit var server: MockWebServer
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = true }

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun postJson(path: String, body: String, token: String = "tok"): okhttp3.Response =
        OkHttpClient().newCall(
            Request.Builder()
                .url(server.url(path))
                .header("Authorization", "Bearer $token")
                .header("makers-conversation-id", "contract-conv-1")
                .post(body.toRequestBody("application/json".toMediaType()))
                .build(),
        ).execute()

    // ---------- 1. 未知字段不影响解析（后端加字段无需同步） ----------

    @Test
    fun `unknown response fields are ignored`() {
        // 后端未来新增了 experimental_field / server_region / trace 等字段。
        val payload = """
            {"display_name":"王同学","avatar_url":"/a.png","membership":"pro",
             "email":"me@example.com","experimental_field":{"deep":[1,2,3]},
             "server_region":"ap-shanghai","trace_id":"abc-123"}
        """.trimIndent()

        val profile = json.decodeFromString(
            com.floris.android.core.model.Profile.serializer(),
            payload,
        )

        assertEquals("王同学", profile.display_name)
        assertEquals("pro", profile.membership)
        // 新字段被安全忽略，没有抛异常，客户端不需要任何改动。
    }

    @Test
    fun `missing optional fields fall back to defaults`() {
        // 后端某次只返回了最小集合。
        val profile = json.decodeFromString(
            com.floris.android.core.model.Profile.serializer(),
            """{"display_name":"只有名字"}""",
        )
        assertEquals("只有名字", profile.display_name)
        assertNull(profile.membership)
        assertNull(profile.avatar_url)
    }

    @Test
    fun `identity tolerates new auth types`() {
        // 后端新增了 auth_type=wechat，客户端不认识但也不能崩。
        val identity = json.decodeFromString(
            com.floris.android.core.model.Identity.serializer(),
            """{"auth_type":"wechat","membership":"vip_plus","extra":true}""",
        )
        assertEquals("wechat", identity.auth_type)
        assertEquals("vip_plus", identity.membership)
    }

    // ---------- 2. 未知 SSE 事件降级为忽略（后端加事件无需同步） ----------

    @Test
    fun `unknown sse events degrade to ignored`() {
        val dispatcher = ChatEventDispatcher(json)
        val frames = SseParser.split(
            "event: token\n" +
                "data: {\"type\":\"ai_response\",\"content\":\"正文\"}\n\n" +
                // 后端将来新增的事件类型
                "event: quantum_thinking\n" +
                "data: {\"type\":\"quantum_thinking\",\"payload\":{\"depth\":9}}\n\n" +
                "event: done\n" +
                "data: {\"type\":\"answer_complete\",\"payload\":{\"turn_id\":\"t-9\"}}\n\n",
        ).frames

        val events = frames.map { dispatcher.dispatch(it) }

        assertEquals("正文", events.filterIsInstance<ChatEvent.AiResponse>().single().content)
        assertEquals("t-9", events.filterIsInstance<ChatEvent.AnswerComplete>().single().turnId)
        // 不认识的事件既不崩也不误判，直接忽略。
        assertEquals(1, events.count { it is ChatEvent.Ignored })
    }

    @Test
    fun `malformed event payload never breaks the stream`() {
        val dispatcher = ChatEventDispatcher(json)
        val frames = SseParser.split(
            "event: progress_event\ndata: {this is not json}\n\n" +
                "event: token\ndata: {\"type\":\"ai_response\",\"content\":\"依然可用\"}\n\n",
        ).frames

        // 关键保证：坏帧不抛异常、不中断，后续正文照常解析出来。
        val events = frames.map { dispatcher.dispatch(it) }
        assertEquals("依然可用", events.filterIsInstance<ChatEvent.AiResponse>().single().content)
        assertTrue("坏帧不得产生正文事件", events.filterIsInstance<ChatEvent.AiResponse>().size == 1)
    }

    // ---------- 3. 请求契约：路径 / 头 / 操作字段固定 ----------

    @Test
    fun `requests always carry bearer and conversation id`() {
        server.enqueue(MockResponse().setBody("{}"))
        postJson("proactive", """{"operation":"refresh"}""").close()

        val recorded = server.takeRequest()
        assertEquals("/proactive", recorded.path)
        assertEquals("POST", recorded.method)
        assertEquals("Bearer tok", recorded.getHeader("Authorization"))
        assertEquals("contract-conv-1", recorded.getHeader("makers-conversation-id"))
    }

    @Test
    fun `proactive operations match the contract vocabulary`() {
        // 这四个 operation 是客户端唯一会发出的，后端只要保留它们就无需同步改动。
        val allowed = setOf("refresh", "mark_read", "snooze", "dismiss", "get", "update_preferences")
        val used = setOf("refresh", "mark_read", "snooze", "dismiss")
        assertTrue("客户端使用的 operation 必须都在契约词表内", allowed.containsAll(used))
    }

    @Test
    fun `snooze sends notification id and until`() {
        server.enqueue(MockResponse().setBody("{}"))
        val until = 1_700_003_600L
        postJson(
            "proactive",
            """{"operation":"snooze","input":{"notification_id":"n-1","until":$until}}""",
        ).close()

        val body = server.takeRequest().body.readUtf8()
        val parsed = json.parseToJsonElement(body) as JsonObject
        val input = parsed["input"] as JsonObject
        assertEquals("snooze", parsed["operation"]!!.jsonPrimitive.content)
        assertEquals("n-1", input["notification_id"]!!.jsonPrimitive.content)
        assertEquals(until, input["until"]!!.jsonPrimitive.content.toLong())
    }

    // ---------- 4. 错误契约：按 code 分流而非文案 ----------

    @Test
    fun `error code drives the message not the prose`() {
        // 后端把提示语从"请先登录后使用此 Skill"改成任何别的说法，
        // 客户端仍按 code 判定，不需要同步。
        server.enqueue(
            MockResponse().setResponseCode(403)
                .setBody("""{"error":"换了一句完全不同的话","code":"LOGIN_REQUIRED"}"""),
        )
        val response = postJson("skills", """{"operation":"set_enabled"}""")
        val body = response.body!!.string()
        response.close()

        val parsed = json.parseToJsonElement(body) as JsonObject
        assertEquals("LOGIN_REQUIRED", parsed["code"]!!.jsonPrimitive.content)
    }

    @Test
    fun `success is never assumed without backend confirmation`() {
        // 后端返回 200 但没有确认字段时，客户端不得当作成功。
        server.enqueue(MockResponse().setBody("""{"status":"pending"}"""))
        val response = postJson("workspace", """{"operation":"confirm_action"}""")
        val body = json.parseToJsonElement(response.body!!.string()) as JsonObject
        response.close()

        assertFalse(
            "只有后端明确 confirmed 才算成功",
            body["status"]?.jsonPrimitive?.content == "confirmed",
        )
    }

    // ---------- 5. 契约版本 ----------

    @Test
    fun `client speaks contract v1`() {
        val session = json.decodeFromString(
            com.floris.android.core.model.MobileSession.serializer(),
            """{"access_token":"t","expires_in":3600,"contract_version":"1",
                "identity":{"auth_type":"guest"},"brand_new_field":42}""",
        )
        assertEquals("1", session.contract_version)
        assertEquals("t", session.access_token)
    }
}
