package com.floris.android.core.network

import com.floris.android.BuildConfig
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.GuestSession
import com.floris.android.core.model.Identity
import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.core.network.sse.ChatEventDispatcher
import com.floris.android.core.network.sse.SseParser
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, message: String) : IOException(message)

/**
 * Single entry point for everything that talks to the Floris Maker backend.
 *
 * Auth discipline (mobile-client-v1):
 *  - every business request carries `Authorization: Bearer <floris token>`;
 *  - a 401 refreshes the CloudBase session and re-exchanges the Floris token
 *    exactly once (OkHttp Authenticator);
 *  - `makers-conversation-id` is passed explicitly per call.
 */
class FlorisClient(
    val authManager: AuthManager,
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    },
) {
    private val jsonMediaType = "application/json".toMediaType()

    private val authInterceptor = Interceptor { chain ->
        val original = chain.request()
        val builder = original.newBuilder().header("Accept", "application/json")
        if (original.header("Authorization") == null) {
            authManager.currentFlorisToken()?.let { builder.header("Authorization", "Bearer $it") }
        }
        chain.proceed(builder.build())
    }

    private val tokenAuthenticator = Authenticator { _: Route?, response: Response ->
        if (response.request.header("X-Floris-Retried") != null) return@Authenticator null
        val fresh = runBlocking {
            runCatching { authManager.refreshAndExchange() }.getOrNull()
        } ?: return@Authenticator null
        response.request.newBuilder()
            .header("Authorization", "Bearer $fresh")
            .header("X-Floris-Retried", "1")
            .build()
    }

    private val baseClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(authInterceptor)
        .authenticator(tokenAuthenticator)
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC },
                )
            }
        }
        .build()

    val api: FlorisApi = Retrofit.Builder()
        .baseUrl(BuildConfig.FLORIS_BASE_URL.ensureTrailingSlash())
        .client(baseClient)
        .addConverterFactory(json.asConverterFactory(jsonMediaType))
        .build()
        .create(FlorisApi::class.java)

    val dispatcher = ChatEventDispatcher(json)

    /**
     * 游客登录：GET /auth/session 在没有凭证时返回 identity(auth_type=guest)
     * 并通过 Set-Cookie: floris_session=<jwt> 下发会话。这里把 cookie 里的 JWT
     * 取出来当 Bearer 用（后端 readSessionToken 同时接受 Bearer 与 cookie）。
     */
    suspend fun obtainGuestSession(): GuestSession {
        val response = api.guestSession()
        if (!response.isSuccessful) {
            throw ApiException(response.code(), "游客会话获取失败 (${response.code()})")
        }
        val cookies = response.headers().values("Set-Cookie")
        val raw = cookies.firstNotNullOfOrNull { header ->
            header.split(';').firstOrNull()?.trim()?.takeIf { it.startsWith("$SESSION_COOKIE=") }
                ?.substringAfter('=')
        } ?: throw ApiException(response.code(), "游客会话未返回凭证")
        val token = runCatching { java.net.URLDecoder.decode(raw, "UTF-8") }.getOrDefault(raw)
        val maxAgeSeconds = cookies.firstNotNullOfOrNull { header ->
            Regex("Max-Age=(\\d+)", RegexOption.IGNORE_CASE).find(header)?.groupValues?.get(1)?.toLongOrNull()
        } ?: GUEST_FALLBACK_TTL_SECONDS
        val identity = response.body()?.get("identity")?.let { element ->
            runCatching { json.decodeFromJsonElement(Identity.serializer(), element) }.getOrNull()
        } ?: Identity(auth_type = "guest", membership = "guest", display_name = "游客")
        return GuestSession(
            token = token,
            expiresAt = System.currentTimeMillis() + maxAgeSeconds * 1000,
            identity = identity,
        )
    }

    /** SSE streaming for POST /chat. */
    fun streamChat(conversationId: String, body: JsonObject): Flow<ChatEvent> =
        streamSse("chat", conversationId, body).map { dispatcher.dispatch(it) }

    /**
     * SSE streaming for POST /reader (论文助读：summarize / translate / analyze / qa).
     * Emits incremental `paper_delta` text; falls back to a plain JSON body.
     */
    fun streamReader(conversationId: String, body: JsonObject): Flow<ReaderChunk> =
        streamSse("reader", conversationId, body).map { frame ->
            if (frame == "[DONE]") return@map ReaderChunk.Done
            val obj = runCatching { json.parseToJsonElement(frame) as? JsonObject }.getOrNull()
                ?: return@map ReaderChunk.Delta(frame)
            when (obj["type"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }) {
                "paper_delta" -> ReaderChunk.Delta(
                    (obj["content"] as? kotlinx.serialization.json.JsonPrimitive)?.content.orEmpty(),
                )
                "error_message" -> ReaderChunk.Error(
                    (obj["content"] as? kotlinx.serialization.json.JsonPrimitive)?.content
                        ?: "阅读失败",
                )
                else -> {
                    // Non-SSE JSON fallback: {"content": "..."}
                    val content = (obj["content"] as? kotlinx.serialization.json.JsonPrimitive)?.content
                    if (content.isNullOrEmpty()) ReaderChunk.Ignored else ReaderChunk.Delta(content)
                }
            }
        }

    private fun streamSse(path: String, conversationId: String, body: JsonObject): Flow<String> =
        callbackFlow {
            authManager.ensureFreshToken()
            val request = buildSseRequest(path, conversationId, body)
            val client = baseClient.newBuilder()
                .readTimeout(0, TimeUnit.MILLISECONDS) // SSE: no read timeout
                .retryOnConnectionFailure(false)
                .build()
            val response = try {
                client.newCall(request).execute()
            } catch (error: Throwable) {
                close(error)
                return@callbackFlow
            }
            if (!response.isSuccessful) {
                val detail = runCatching { response.body?.string().orEmpty() }.getOrDefault("")
                val status = response.code
                response.close()
                close(ApiException(status, detail.ifEmpty { "$path failed ($status)" }))
                return@callbackFlow
            }
            val source = response.body?.source() ?: run {
                response.close()
                close(ApiException(response.code, "Empty $path stream"))
                return@callbackFlow
            }
            var buffer = ""
            try {
                while (!source.exhausted()) {
                    val chunk = source.readUtf8(4096) ?: break
                    buffer += chunk
                    val split = SseParser.split(buffer)
                    buffer = split.rest
                    for (frame in split.frames) trySend(frame)
                }
                SseParser.flush(buffer)?.let { trySend(it) }
                close()
            } catch (error: Throwable) {
                close(error)
            } finally {
                response.close()
            }
            awaitClose { response.close() }
        }.flowOn(Dispatchers.IO)

    private fun buildSseRequest(path: String, conversationId: String, body: JsonObject): Request {
        val requestBody = json.encodeToString(JsonObject.serializer(), body).toRequestBody(jsonMediaType)
        return Request.Builder()
            .url(BuildConfig.FLORIS_BASE_URL.ensureTrailingSlash() + path)
            .header("Accept", "text/event-stream")
            .header("makers-conversation-id", conversationId)
            .post(requestBody)
            .build()
    }

    private fun String.ensureTrailingSlash(): String = if (endsWith("/")) this else "$this/"

    private companion object {
        const val SESSION_COOKIE = "floris_session"
        /** 后端游客会话为 7 天；响应缺少 Max-Age 时按此兜底。 */
        const val GUEST_FALLBACK_TTL_SECONDS = 7L * 24 * 60 * 60
    }
}

/** 论文助读增量结果。 */
sealed interface ReaderChunk {
    data class Delta(val text: String) : ReaderChunk
    data class Error(val message: String) : ReaderChunk
    data object Done : ReaderChunk
    data object Ignored : ReaderChunk
}
