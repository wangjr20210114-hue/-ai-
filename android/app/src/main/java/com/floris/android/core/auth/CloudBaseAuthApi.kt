package com.floris.android.core.auth

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.Headers
import retrofit2.http.POST
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

/**
 * CloudBase Auth (GoTrue-compatible) HTTP API client.
 *
 * Used only for email OTP sign-in, session restore and token refresh.
 * The publishable key is safe to ship in the client (see repo README).
 */
interface CloudBaseAuthApi {

    @Headers("Content-Type: application/json")
    @POST("auth/v1/otp")
    suspend fun sendOtp(
        @Header("apikey") apiKey: String,
        @Body body: OtpRequest,
    )

    @Headers("Content-Type: application/json")
    @POST("auth/v1/verify")
    suspend fun verifyOtp(
        @Header("apikey") apiKey: String,
        @Body body: VerifyRequest,
    ): CloudBaseSession

    @Headers("Content-Type: application/json")
    @POST("auth/v1/token")
    suspend fun refreshToken(
        @Header("apikey") apiKey: String,
        @Query("grant_type") grantType: String = "refresh_token",
        @Body body: RefreshRequest,
    ): CloudBaseSession

    @POST("auth/v1/logout")
    suspend fun logout(
        @Header("apikey") apiKey: String,
        @Header("Authorization") bearer: String,
    )

    companion object {
        fun create(baseUrl: String, json: Json, client: OkHttpClient? = null): CloudBaseAuthApi {
            val okHttp = client ?: OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
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
data class OtpRequest(
    val email: String,
    val options: Options = Options(),
) {
    @Serializable
    data class Options(val shouldCreateUser: Boolean = true)
}

@Serializable
data class VerifyRequest(
    val email: String,
    val token: String,
    val type: String = "email",
)

@Serializable
data class RefreshRequest(val refresh_token: String)

@Serializable
data class CloudBaseSession(
    val access_token: String = "",
    val refresh_token: String = "",
    val token_type: String = "bearer",
    val expires_in: Long = 3600,
    val expires_at: Long = 0,
)
