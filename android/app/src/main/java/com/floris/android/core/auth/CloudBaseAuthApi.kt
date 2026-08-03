package com.floris.android.core.auth

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.http.Body
import retrofit2.http.Headers
import retrofit2.http.POST
import retrofit2.http.Query
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * CloudBase Auth HTTP API client — verified against the official
 * @cloudbase/js-sdk 3.7.0 wire protocol:
 *
 *  host:  https://{env}.api.tcloudbasegateway.com
 *  auth:  Authorization: Bearer <publishable key>
 *
 *  1. POST /auth/v1/verification            {email, usage:"email"}        → {verification_id}
 *  2. POST /auth/v1/verification/verify     {verification_id, code}       → {verification_token}
 *  3. POST /auth/v1/signin | /auth/v1/signup {username|email, verification_token} → tokens
 *  4. POST /auth/v1/token                   {grant_type:"refresh_token"}  → new tokens
 */
interface CloudBaseAuthApi {

    @Headers("Content-Type: application/json")
    @POST("auth/v1/verification")
    suspend fun sendVerification(@Body body: VerificationRequest): VerificationResponse

    @Headers("Content-Type: application/json")
    @POST("auth/v1/verification/verify")
    suspend fun verifyCode(
        @Query("client_id") clientId: String,
        @Body body: VerifyCodeRequest,
    ): VerifyCodeResponse

    @Headers("Content-Type: application/json")
    @POST("auth/v1/signin")
    suspend fun signIn(
        @Query("client_id") clientId: String,
        @Body body: SignInRequest,
    ): CloudBaseSession

    @Headers("Content-Type: application/json")
    @POST("auth/v1/signup")
    suspend fun signUp(
        @Query("client_id") clientId: String,
        @Body body: SignUpRequest,
    ): CloudBaseSession

    @Headers("Content-Type: application/json")
    @POST("auth/v1/token")
    suspend fun refreshToken(
        @Query("client_id") clientId: String,
        @Body body: RefreshRequest,
    ): CloudBaseSession

    companion object {
        fun create(
            baseUrl: String,
            envId: String,
            publishableKey: String,
            json: Json,
            client: OkHttpClient? = null,
            deviceId: String = UUID.randomUUID().toString().replace("-", ""),
        ): CloudBaseAuthApi {
            val authHeader = Interceptor { chain ->
                val request = chain.request().newBuilder()
                    .header("Authorization", "Bearer $publishableKey")
                    .header("x-device-id", deviceId)
                    .header("X-SDK-Version", "@cloudbase/js-sdk/3.7.0")
                    .header("X-TCB-Region", "ap-shanghai")
                    .header("X-Client-Timestamp", System.currentTimeMillis().toString())
                    .build()
                chain.proceed(request)
            }
            val okHttp = (client?.newBuilder() ?: OkHttpClient.Builder())
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .addInterceptor(authHeader)
                .build()
            return Retrofit.Builder()
                .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
                .client(okHttp)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(CloudBaseAuthApi::class.java)
        }
    }
}

@Serializable
data class VerificationRequest(
    val email: String,
    val usage: String = "email",
)

@Serializable
data class VerificationResponse(
    val verification_id: String = "",
    val error_code: Int? = null,
    val error_description: String? = null,
)

@Serializable
data class VerifyCodeRequest(
    val verification_id: String,
    val verification_code: String,
)

@Serializable
data class VerifyCodeResponse(
    val verification_token: String = "",
    val error_code: Int? = null,
    val error_description: String? = null,
)

@Serializable
data class SignInRequest(
    val username: String,
    val verification_token: String,
)

@Serializable
data class SignUpRequest(
    val email: String,
    val verification_token: String,
)

@Serializable
data class RefreshRequest(
    val client_id: String,
    val client_secret: String = "",
    val grant_type: String = "refresh_token",
    val refresh_token: String,
)

@Serializable
data class CloudBaseSession(
    val access_token: String = "",
    val refresh_token: String = "",
    val token_type: String = "bearer",
    /** Seconds until expiry (v2 style). */
    val expires_in: Long = 0,
    /** Absolute epoch (s or ms) or string timestamp (v1 style). */
    val expires_at: Long = 0,
    val access_token_expire: String? = null,
    val refresh_token_expire: String? = null,
    val error_code: Int? = null,
    val error_description: String? = null,
) {
    /** Resolve an absolute expiry in epoch milliseconds, lenient across shapes. */
    fun resolvedExpiresAt(now: Long = System.currentTimeMillis()): Long {
        fun parseEpoch(raw: String?): Long {
            val value = raw?.toLongOrNull() ?: return 0
            return when {
                value > 1_000_000_000_000L -> value          // epoch ms
                value > 10_000_000_000L -> value * 1000      // epoch s
                else -> 0
            }
        }
        parseEpoch(access_token_expire).takeIf { it > 0 }?.let { return it }
        if (expires_at > 0) {
            return if (expires_at > 1_000_000_000_000L) expires_at else expires_at * 1000
        }
        if (expires_in > 0) return now + expires_in * 1000
        return now + 3600_000
    }
}
