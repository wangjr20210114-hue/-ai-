package com.floris.android.core.network

import com.floris.android.BuildConfig
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.core.network.sse.ChatEventDispatcher
import com.floris.android.core.network.sse.SseParser
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
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

    /** SSE streaming for POST /chat. */
    fun streamChat(conversationId: String, body: JsonObject): Flow<ChatEvent> = callbackFlow {
        authManager.ensureFreshToken()
        val request = buildChatRequest(conversationId, body)
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
            close(ApiException(status, detail.ifEmpty { "Chat failed ($status)" }))
            return@callbackFlow
        }
        val source = response.body?.source() ?: run {
            response.close()
            close(ApiException(response.code, "Empty chat stream"))
            return@callbackFlow
        }
        var buffer = ""
        try {
            while (!source.exhausted()) {
                val chunk = source.readUtf8(4096) ?: break
                buffer += chunk
                val split = SseParser.split(buffer)
                buffer = split.rest
                for (frame in split.frames) trySend(dispatcher.dispatch(frame))
            }
            SseParser.flush(buffer)?.let { trySend(dispatcher.dispatch(it)) }
            close()
        } catch (error: Throwable) {
            close(error)
        } finally {
            response.close()
        }
        awaitClose { response.close() }
    }.flowOn(Dispatchers.IO)

    private fun buildChatRequest(conversationId: String, body: JsonObject): Request {
        val requestBody = json.encodeToString(JsonObject.serializer(), body).toRequestBody(jsonMediaType)
        return Request.Builder()
            .url(BuildConfig.FLORIS_BASE_URL.ensureTrailingSlash() + "chat")
            .header("Accept", "text/event-stream")
            .header("makers-conversation-id", conversationId)
            .post(requestBody)
            .build()
    }

    private fun String.ensureTrailingSlash(): String = if (endsWith("/")) this else "$this/"
}
