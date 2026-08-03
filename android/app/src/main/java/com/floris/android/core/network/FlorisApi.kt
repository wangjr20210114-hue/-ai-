package com.floris.android.core.network

import com.floris.android.core.model.ConversationBootstrap
import com.floris.android.core.model.MobileSession
import com.floris.android.core.model.Profile
import com.floris.android.core.model.SkillMarketplaceState
import kotlinx.serialization.json.JsonObject
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Headers
import retrofit2.http.POST
import retrofit2.http.Query

interface FlorisApi {

    @Headers("Content-Type: application/json")
    @POST("auth/mobile/session")
    suspend fun exchangeMobileSession(@Body body: JsonObject): MobileSession

    @Headers("Content-Type: application/json")
    @POST("messages")
    suspend fun bootstrap(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject = JsonObject(emptyMap()),
    ): ConversationBootstrap

    @GET("conversations")
    suspend fun listConversations(): JsonObject

    @Headers("Content-Type: application/json")
    @POST("conversations")
    suspend fun touchConversation(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @DELETE("conversations")
    suspend fun deleteConversation(
        @Header("makers-conversation-id") conversationId: String,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("stop")
    suspend fun stop(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("conversation")
    suspend fun appendMessage(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("workspace")
    suspend fun workspaceOperation(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("intelligence")
    suspend fun intelligenceOperation(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("skill_marketplace")
    suspend fun skillMarketplace(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): SkillMarketplaceState

    @Headers("Content-Type: application/json")
    @POST("places")
    suspend fun searchPlaces(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("routes")
    suspend fun planRoute(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @GET("papers")
    suspend fun searchPapers(@Query("topic") topic: String): JsonObject

    @Headers("Content-Type: application/json")
    @POST("reader")
    suspend fun readPaper(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @GET("library")
    suspend fun loadLibrary(): JsonObject

    @Headers("Content-Type: application/json")
    @POST("library")
    suspend fun libraryOperation(@Body body: JsonObject): JsonObject

    @GET("profile")
    suspend fun getProfile(): Profile

    @Headers("Content-Type: application/json")
    @POST("profile")
    suspend fun profileOperation(@Body body: JsonObject): JsonObject

    @Headers("Content-Type: application/json")
    @POST("proactive")
    suspend fun proactiveOperation(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @GET("provider_usage")
    suspend fun providerUsage(
        @Header("makers-conversation-id") conversationId: String,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("reset")
    suspend fun resetState(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("reset-files")
    suspend fun resetFiles(@Body body: JsonObject): JsonObject
}
