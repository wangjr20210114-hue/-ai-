package com.floris.android.core.network

import com.floris.android.core.model.ConversationBootstrap
import com.floris.android.core.model.ChatRunState
import com.floris.android.core.model.MobileSession
import com.floris.android.core.model.Profile
import com.floris.android.core.model.SkillMarketplaceState
import kotlinx.serialization.json.JsonObject
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.HEAD
import retrofit2.http.Headers
import retrofit2.http.POST
import retrofit2.http.Query
import retrofit2.http.Streaming
import okhttp3.ResponseBody
import retrofit2.Response

interface FlorisApi {

    @Headers("Content-Type: application/json")
    @POST("auth/mobile/session")
    suspend fun exchangeMobileSession(@Body body: JsonObject): MobileSession

    @Headers("Content-Type: application/json")
    @POST("auth/logout")
    suspend fun logout(@Body body: JsonObject = JsonObject(emptyMap())): JsonObject

    /**
     * GET /auth/session —— 无凭证访问时后端会签发一枚 7 天有效的游客会话
     * （auth_type=guest），通过 Set-Cookie: floris_session 下发。
     * 移动端把该 cookie 值当作 Bearer 使用（后端 readSessionToken 同时接受两者）。
     */
    @GET("auth/session")
    suspend fun guestSession(): retrofit2.Response<JsonObject>

    @Headers("Content-Type: application/json")
    @POST("messages")
    suspend fun bootstrap(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject = JsonObject(emptyMap()),
    ): ConversationBootstrap

    @Headers("Content-Type: application/json")
    @POST("run")
    suspend fun chatRun(
        @Header("makers-conversation-id") conversationId: String,
        @Body body: JsonObject,
    ): ChatRunState

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
    @POST("files")
    suspend fun createFileUpload(@Body body: JsonObject): JsonObject

    @Streaming
    @GET("files")
    suspend fun downloadFile(
        @Query("key") key: String,
        @Query("part") part: Int? = null,
    ): Response<ResponseBody>

    @HEAD("files")
    suspend fun inspectFile(@Query("key") key: String): Response<Void>

    @DELETE("files")
    suspend fun deleteFile(@Query("key") key: String): JsonObject

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

    @GET("skill-uploads")
    suspend fun listSkillUploads(): JsonObject

    @Headers("Content-Type: application/json")
    @POST("skill-uploads")
    suspend fun mutateSkillUpload(@Body body: JsonObject): JsonObject

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
    @POST("papers")
    suspend fun savePaper(@Body body: JsonObject): JsonObject

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

    @DELETE("library")
    suspend fun deleteLibrary(
        @Query("id") id: String? = null,
        @Query("folder_id") folderId: String? = null,
    ): JsonObject

    @Headers("Content-Type: application/json")
    @POST("document-text")
    suspend fun extractDocumentText(@Body body: JsonObject): JsonObject

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
