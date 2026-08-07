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
import kotlinx.coroutines.withContext
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
import okio.Buffer
import retrofit2.Retrofit
import java.io.IOException
import java.util.concurrent.TimeUnit

internal object FlorisStreamRoutes {
    const val CHAT = "chat"
    const val IMAGE = "image"
    const val READER = "reader"
    val all = setOf(CHAT, IMAGE, READER)
}

class ApiException(
    val status: Int,
    val code: String? = null,
    val serverMessage: String? = null,
    val requestPath: String? = null,
) : IOException("Floris request failed: ${requestPath ?: "unknown"} ($status${code?.let { ", $it" }.orEmpty()})")

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
    private val responseLanguage: () -> String = { "zh-CN" },
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
        // 强制换新 token：游客再领一枚游客会话，正式用户走 CloudBase 刷新。
        // 绝不能复用刚被服务端拒绝的旧 token，否则会陷入重试循环。
        val fresh = runBlocking {
            runCatching { authManager.forceRenewToken() }.getOrNull()
        } ?: return@Authenticator null
        response.request.newBuilder()
            .header("Authorization", "Bearer $fresh")
            .header("X-Floris-Retried", "1")
            .build()
    }

    /** Add the selected product language to every Maker JSON command. */
    private val responseLanguageInterceptor = Interceptor { chain ->
        val original = chain.request()
        val body = original.body
        val contentType = body?.contentType()
        if (body == null || contentType?.subtype?.contains("json", ignoreCase = true) != true) {
            return@Interceptor chain.proceed(original)
        }
        val replacement = runCatching {
            val buffer = Buffer()
            body.writeTo(buffer)
            injectResponseLanguage(json, buffer.readUtf8(), responseLanguage())
                ?.toRequestBody(contentType)
        }.getOrNull()
        chain.proceed(
            if (replacement == null) original else original.newBuilder()
                .method(original.method, replacement)
                .build(),
        )
    }

    private val baseClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        // 云函数冷启动首字节可能超过 30s，普通请求给足 90s。
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(authInterceptor)
        .addInterceptor(responseLanguageInterceptor)
        .authenticator(tokenAuthenticator)
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC },
                )
            }
        }
        .build()

    /** Presigned Maker Blob URLs must never receive the Floris bearer. */
    private val blobClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
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
            throw ApiException(status = response.code(), requestPath = "auth/session")
        }
        val cookies = response.headers().values("Set-Cookie")
        val raw = cookies.firstNotNullOfOrNull { header ->
            header.split(';').firstOrNull()?.trim()?.takeIf { it.startsWith("$SESSION_COOKIE=") }
                ?.substringAfter('=')
        } ?: throw ApiException(status = response.code(), code = "MISSING_SESSION_TOKEN", requestPath = "auth/session")
        val token = runCatching { java.net.URLDecoder.decode(raw, "UTF-8") }.getOrDefault(raw)
        val maxAgeSeconds = cookies.firstNotNullOfOrNull { header ->
            Regex("Max-Age=(\\d+)", RegexOption.IGNORE_CASE).find(header)?.groupValues?.get(1)?.toLongOrNull()
        } ?: GUEST_FALLBACK_TTL_SECONDS
        val identity = response.body()?.get("identity")?.let { element ->
            runCatching { json.decodeFromJsonElement(Identity.serializer(), element) }.getOrNull()
        } ?: Identity(auth_type = "guest", membership = "guest")
        return GuestSession(
            token = token,
            expiresAt = System.currentTimeMillis() + maxAgeSeconds * 1000,
            identity = identity,
        )
    }

    /** SSE streaming for POST /chat. */
    fun streamChat(conversationId: String, body: JsonObject): Flow<ChatEvent> =
        streamSse(FlorisStreamRoutes.CHAT, conversationId, body).map { dispatcher.dispatch(it) }

    fun streamImageEdit(conversationId: String, body: JsonObject): Flow<ChatEvent> =
        streamSse(FlorisStreamRoutes.IMAGE, conversationId, body).map { dispatcher.dispatch(it) }

    suspend fun putPresigned(
        url: String,
        contentType: String,
        bytes: ByteArray,
    ) = withContext(Dispatchers.IO) {
        require(url.startsWith("https://")) { "Only HTTPS upload URLs are accepted" }
        val request = Request.Builder()
            .url(url)
            .put(bytes.toRequestBody(contentType.toMediaType()))
            .build()
        blobClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw ApiException(status = response.code, requestPath = "files/blob")
            }
        }
    }

    /**
     * 下载公开 HTTPS 资源字节（生图结果保存到相册等）。
     *
     * 使用 blobClient 的独立连接池，绝不携带 Floris Bearer；仅接受 HTTPS，
     * 避免把任意内网/明文地址交给下载器。
     */
    suspend fun fetchBytes(url: String): ByteArray = withContext(Dispatchers.IO) {
        require(url.startsWith("https://")) { "Only HTTPS download URLs are accepted" }
        val request = Request.Builder()
            .url(url)
            .get()
            .build()
        blobClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw ApiException(status = response.code, requestPath = "files/blob")
            }
            response.body?.bytes()
                ?: throw ApiException(status = response.code, requestPath = "files/blob")
        }
    }

    /**
     * SSE streaming for POST /reader (论文助读：summarize / translate / analyze / qa).
     * Emits incremental `paper_delta` text; falls back to a plain JSON body.
     */
    fun streamReader(conversationId: String, body: JsonObject): Flow<ReaderChunk> =
        streamSse(FlorisStreamRoutes.READER, conversationId, body).map { frame ->
            if (frame == "[DONE]") return@map ReaderChunk.Done
            val obj = runCatching { json.parseToJsonElement(frame) as? JsonObject }.getOrNull()
                ?: return@map ReaderChunk.Delta(frame)
            when (obj["type"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }) {
                "paper_delta" -> ReaderChunk.Delta(
                    (obj["content"] as? kotlinx.serialization.json.JsonPrimitive)?.content.orEmpty(),
                )
                "error_message" -> ReaderChunk.Error(
                    (obj["content"] as? kotlinx.serialization.json.JsonPrimitive)?.content.orEmpty(),
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
                close(parseApiException(status, detail, path))
                return@callbackFlow
            }
            val source = response.body?.source() ?: run {
                response.close()
                close(ApiException(status = response.code, code = "EMPTY_STREAM", requestPath = path))
                return@callbackFlow
            }
            var buffer = ""
            try {
                // 逐行读取：readUtf8(n) 会阻塞到读满 n 字节，会把先到的小事件
                // 一直压在缓冲里，观感上就是"卡住不动然后一次性刷出来"。
                while (true) {
                    val line = source.readUtf8Line() ?: break
                    buffer += line + "\n"
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

    /** Preserve machine-readable server context; UI adapters localize it. */
    private fun parseApiException(status: Int, detail: String, path: String): ApiException {
        val payload = runCatching { json.parseToJsonElement(detail) as? JsonObject }.getOrNull()
        val code = payload?.get("code")
            ?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
        val serverMessage = (payload?.get("error") ?: payload?.get("message"))
            ?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
        return ApiException(
            status = status,
            code = code,
            serverMessage = serverMessage,
            requestPath = path,
        )
    }

    private companion object {
        const val SESSION_COOKIE = "floris_session"
        /** 后端游客会话为 7 天；响应缺少 Max-Age 时按此兜底。 */
        const val GUEST_FALLBACK_TTL_SECONDS = 7L * 24 * 60 * 60
    }
}

internal fun injectResponseLanguage(json: Json, rawBody: String, requested: String): String? {
    val payload = runCatching { json.parseToJsonElement(rawBody) as? JsonObject }.getOrNull()
        ?: return null
    if ("response_language" in payload) return null
    val language = requested.takeIf {
        it in setOf("zh-CN", "zh-TW", "en", "cat-cute", "cat-cold")
    } ?: "zh-CN"
    val localized = JsonObject(
        payload + ("response_language" to kotlinx.serialization.json.JsonPrimitive(language)),
    )
    return json.encodeToString(JsonObject.serializer(), localized)
}

/** 论文助读增量结果。 */
sealed interface ReaderChunk {
    data class Delta(val text: String) : ReaderChunk
    data class Error(val message: String) : ReaderChunk
    data object Done : ReaderChunk
    data object Ignored : ReaderChunk
}
