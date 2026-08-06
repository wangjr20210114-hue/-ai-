package com.floris.android.core.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.model.ConversationBootstrap
import com.floris.android.core.model.ConversationSummary
import com.floris.android.core.model.ChatRunState
import com.floris.android.core.model.IntelligenceState
import com.floris.android.core.model.MapPreferences
import com.floris.android.core.model.Paper
import com.floris.android.core.model.Place
import com.floris.android.core.model.Profile
import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.RoutePlan
import com.floris.android.core.model.Schedule
import com.floris.android.core.model.Skill
import com.floris.android.core.model.SkillUploadRecord
import com.floris.android.core.model.SkillMarketplaceState
import com.floris.android.core.model.SkillAccessProjection
import com.floris.android.core.model.toSkillAccessProjection
import com.floris.android.core.network.FlorisClient
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

data class MapWorkspaceState(
    val places: List<Place> = emptyList(),
    val title: String? = null,
    val routeMode: String? = null,
    val routeStrategy: String? = null,
    val showRoute: Boolean = false,
    val route: RoutePlan? = null,
    val revision: Long = 0,
)

private const val SKILL_ACCESS_TTL_MS = 5 * 60 * 1000L

/**
 * Thin data layer over the Floris Maker backend. Contains zero business
 * logic — every operation is forwarded to the backend verbatim.
 */
class FlorisRepository(
    private val client: FlorisClient,
    private val tokenStore: TokenStore,
    private val json: Json,
    private val context: Context,
) {
    private val api get() = client.api

    /** Backend-confirmed workspace projections shared across screens. */
    val schedulesFlow = kotlinx.coroutines.flow.MutableStateFlow<List<Schedule>>(emptyList())
    val mapWorkspaceFlow = kotlinx.coroutines.flow.MutableStateFlow(MapWorkspaceState())
    private val _skillAccessFlow = kotlinx.coroutines.flow.MutableStateFlow(SkillAccessProjection())
    val skillAccessFlow = _skillAccessFlow.asStateFlow()
    private val skillAccessMutex = Mutex()
    private var skillAccessFetchedAt = 0L

    /**
     * 待填入聊天输入框的草稿。主动提醒点"去处理"时写入，
     * 聊天页读取后清空——只做页面间传值，不触发任何后端调用。
     */
    val pendingDraftFlow = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    val localAvatarFlow = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)

    /** Drop identity-scoped in-memory projections without deleting server data or cached files. */
    fun clearLocalIdentityProjection() {
        schedulesFlow.value = emptyList()
        mapWorkspaceFlow.value = MapWorkspaceState()
        _skillAccessFlow.value = SkillAccessProjection()
        skillAccessFetchedAt = 0L
        pendingDraftFlow.value = null
        localAvatarFlow.value = null
    }

    fun publishMapWorkspace(map: JsonObject, fallbackTitle: String?) {
        val places = (map["places"] as? JsonArray).orEmpty().mapNotNull {
            runCatching { json.decodeFromJsonElement(Place.serializer(), it) }.getOrNull()
        }
        mapWorkspaceFlow.value = MapWorkspaceState(
            places = places,
            title = map.str("title") ?: fallbackTitle,
            routeMode = map.str("route_mode"),
            routeStrategy = map.str("route_strategy"),
            showRoute = map.bool("show_route") ?: false,
            route = map["route"]?.let { raw ->
                runCatching { json.decodeFromJsonElement(RoutePlan.serializer(), raw) }.getOrNull()
            },
            revision = mapWorkspaceFlow.value.revision + 1,
        )
    }

    // ---------- Conversation IDs ----------

    /** Stable, opaque makers-conversation-id for the active chat. */
    suspend fun activeConversationId(): String {
        tokenStore.activeConversationId()?.let { return it }
        val created = newConversationId()
        tokenStore.saveActiveConversationId(created)
        return created
    }

    suspend fun setActiveConversationId(id: String) = tokenStore.saveActiveConversationId(id)

    fun newConversationId(): String =
        "fla_" + UUID.randomUUID().toString().replace("-", "").take(24)

    suspend fun searchConversationId(): String {
        tokenStore.searchConversationId()?.let { return it }
        val created = newConversationId()
        tokenStore.saveSearchConversationId(created)
        return created
    }

    // ---------- Chat ----------

    fun streamChat(conversationId: String, body: JsonObject) = client.streamChat(conversationId, body)

    suspend fun bootstrap(conversationId: String): ConversationBootstrap =
        api.bootstrap(conversationId, buildJsonObject { put("conversation_id", conversationId) })

    suspend fun chatRun(conversationId: String): ChatRunState =
        api.chatRun(conversationId, buildJsonObject { put("conversation_id", conversationId) })

    suspend fun stop(conversationId: String, clientMessageId: String): JsonObject =
        api.stop(
            conversationId,
            buildJsonObject {
                put("conversation_id", conversationId)
                clientMessageId.takeIf { it.isNotBlank() }?.let { put("client_message_id", it) }
            },
        )

    suspend fun touchConversation(conversationId: String, title: String? = null, messageCount: Int) {
        api.touchConversation(
            conversationId,
            buildJsonObject {
                put("operation", "touch_pointer")
                put("conversation_id", conversationId)
                title?.takeIf { it.isNotBlank() }?.let { put("title", it) }
                put("message_count", messageCount)
            },
        )
    }

    suspend fun renameConversation(conversationId: String, title: String): ConversationSummary? {
        val response = api.touchConversation(
            conversationId,
            buildJsonObject {
                put("operation", "rename")
                put("conversation_id", conversationId)
                put("title", title.trim())
            },
        )
        val item = response.obj("conversation") ?: return null
        val metadata = item.obj("metadata")
        return ConversationSummary(
            id = item.str("conversationId") ?: item.str("id") ?: conversationId,
            title = metadata?.str("title") ?: item.str("title") ?: title.trim(),
            createdAt = item.num("createdAt") ?: item.num("created_at") ?: 0,
            updatedAt = item.num("lastMessageAt") ?: item.num("updatedAt")
                ?: item.num("updated_at") ?: System.currentTimeMillis(),
            messageCount = (item.num("messageCount") ?: item.num("message_count") ?: 0).toInt(),
            pending = false,
            manuallyRenamed = true,
        )
    }

    suspend fun listConversations(): List<ConversationSummary> {
        val response = api.listConversations()
        val items = response["conversations"] as? JsonArray ?: return emptyList()
        return items.mapNotNull { item ->
            val obj = item as? JsonObject ?: return@mapNotNull null
            val id = obj.str("conversationId") ?: obj.str("id") ?: return@mapNotNull null
            val metadata = obj["metadata"] as? JsonObject
            val run = metadata?.get("yuanbao_chat_run_v1") as? JsonObject
            val status = run?.str("status")
            val messageCount = (obj.num("messageCount") ?: obj.num("message_count") ?: 0).toInt()
            val manuallyRenamed = metadata?.str("title_source") == "manual"
            ConversationSummary(
                id = id,
                title = metadata?.str("title") ?: obj.str("title").orEmpty(),
                createdAt = obj.num("createdAt") ?: obj.num("created_at") ?: 0,
                updatedAt = obj.num("lastMessageAt") ?: obj.num("updatedAt")
                    ?: obj.num("updated_at") ?: obj.num("createdAt") ?: 0,
                messageCount = messageCount,
                pending = messageCount == 0 && !manuallyRenamed,
                manuallyRenamed = manuallyRenamed,
                activityStatus = when (status) {
                    "running", "cancel_requested" -> "running"
                    "failed" -> "failed"
                    else -> "idle"
                },
            )
        }.sortedByDescending { it.updatedAt }
    }

    suspend fun deleteConversation(conversationId: String) {
        api.deleteConversation(conversationId)
    }

    // ---------- Workspace ----------

    suspend fun workspaceOperation(
        conversationId: String,
        operation: String,
        input: JsonObject = JsonObject(emptyMap()),
    ): JsonObject = api.workspaceOperation(
        conversationId,
        JsonObject(buildMap {
            put("operation", JsonPrimitive(operation))
            input.forEach { (key, value) -> put(key, value) }
        }),
    )

    suspend fun loadSchedules(conversationId: String): List<Schedule> {
        val response = workspaceOperation(conversationId, "get")
        return parseSchedules(response["schedules"] as? JsonArray)
    }

    fun parseSchedules(array: JsonArray?): List<Schedule> =
        array.orEmpty().mapNotNull { element ->
            runCatching { json.decodeFromJsonElement(Schedule.serializer(), element) }.getOrNull()
        }.filter { it.deleted != true }

    // ---------- Skills / Intelligence ----------

    suspend fun skillCatalog(conversationId: String): SkillMarketplaceState =
        api.skillMarketplace(conversationId, buildJsonObject { put("operation", "catalog") })
            .also { publishSkillAccess(it) }

    /**
     * Fetch Maker's entitlement/catalog projection once for all feature pages.
     * Concurrent tab initializations share one request; no client-side plan or
     * guest policy is inferred here.
     */
    suspend fun ensureSkillAccess(
        conversationId: String,
        force: Boolean = false,
    ): SkillAccessProjection = skillAccessMutex.withLock {
        val cached = _skillAccessFlow.value
        val fresh = cached.ready &&
            System.currentTimeMillis() - skillAccessFetchedAt < SKILL_ACCESS_TTL_MS
        if (!force && fresh) return@withLock cached
        try {
            skillCatalog(conversationId)
            _skillAccessFlow.value
        } catch (error: Throwable) {
            _skillAccessFlow.value = SkillAccessProjection.failed(cached)
            throw error
        }
    }

    private fun publishSkillAccess(catalog: SkillMarketplaceState) {
        _skillAccessFlow.value = catalog.toSkillAccessProjection()
        skillAccessFetchedAt = System.currentTimeMillis()
    }

    suspend fun intelligencePreferences(conversationId: String): JsonObject =
        api.intelligenceOperation(conversationId, buildJsonObject { put("operation", "get") })

    suspend fun intelligenceState(conversationId: String): IntelligenceState =
        decodeIntelligence(intelligencePreferences(conversationId))

    suspend fun mutateIntelligence(
        conversationId: String,
        operation: String,
        input: JsonObject = JsonObject(emptyMap()),
    ): IntelligenceState = decodeIntelligence(
        api.intelligenceOperation(
            conversationId,
            JsonObject(buildMap {
                put("operation", JsonPrimitive(operation))
                input.forEach { (key, value) -> put(key, value) }
            }),
        ),
    )

    private fun decodeIntelligence(response: JsonObject): IntelligenceState =
        json.decodeFromJsonElement(IntelligenceState.serializer(), response)

    suspend fun updateSearchPreferences(
        conversationId: String,
        resultLimit: Int,
        imageLimit: Int,
        parallelImageSearch: Boolean = true,
    ): JsonObject = api.intelligenceOperation(
        conversationId,
        buildJsonObject {
            put("operation", "update_search_preferences")
            putJsonObject("preferences") {
                put("result_limit", resultLimit)
                put("image_limit", imageLimit)
                put("parallel_image_search", parallelImageSearch)
            }
        },
    )

    suspend fun updateMapPreferences(
        conversationId: String,
        preferences: MapPreferences,
    ): JsonObject = api.intelligenceOperation(
        conversationId,
        buildJsonObject {
            put("operation", "update_map_preferences")
            putJsonObject("preferences") {
                put("service_mode", preferences.service_mode)
                put("place_result_limit", preferences.place_result_limit)
                put("route_stop_limit", preferences.route_stop_limit)
                put("search_timeout_seconds", preferences.search_timeout_seconds)
                put("preferred_route_mode", preferences.preferred_route_mode)
                put("route_strategy", preferences.route_strategy)
                put("near_time_tolerance_minutes", preferences.near_time_tolerance_minutes)
                put("learn_route_preferences", preferences.learn_route_preferences)
            }
        },
    )

    suspend fun setSkillEnabled(conversationId: String, skillId: String, enabled: Boolean) {
        api.intelligenceOperation(
            conversationId,
            buildJsonObject {
                put("operation", "update_skill_preferences")
                putJsonObject("preferences") { put(skillId, enabled) }
            },
        )
        _skillAccessFlow.value = _skillAccessFlow.value.withEnabled(skillId, enabled)
    }

    // ---------- Maps ----------

    suspend fun searchPlaces(conversationId: String, query: String, city: String = "全国"): List<Place> {
        val response = api.searchPlaces(
            conversationId,
            buildJsonObject {
                put("query", query)
                put("city", city)
                put("limit", 10)
            },
        )
        val places = response["places"] as? JsonArray ?: return emptyList()
        return places.mapNotNull {
            runCatching { json.decodeFromJsonElement(Place.serializer(), it) }.getOrNull()
        }
    }

    suspend fun planRoute(
        conversationId: String,
        places: List<Place>,
        mode: String? = null,
        strategy: String? = null,
    ): RoutePlan? {
        val response = api.planRoute(
            conversationId,
            buildJsonObject {
                put("places", json.encodeToJsonElement(
                    kotlinx.serialization.builtins.ListSerializer(Place.serializer()), places,
                ))
                mode?.let { put("mode", it) }
                strategy?.let { put("strategy", it) }
                put("optimize", false)
            },
        )
        val route = response["route"] ?: return null
        return runCatching { json.decodeFromJsonElement(RoutePlan.serializer(), route) }.getOrNull()
    }

    // ---------- Papers ----------

    suspend fun searchPapers(topic: String): List<Paper> {
        val response = api.searchPapers(topic)
        val papers = (response["papers"] as? JsonArray)
            ?: (response["results"] as? JsonArray)
            ?: return emptyList()
        return papers.mapNotNull {
            runCatching { json.decodeFromJsonElement(Paper.serializer(), it) }.getOrNull()
        }
    }

    suspend fun directCalendarChanges(
        conversationId: String,
        changes: JsonArray,
    ): List<Schedule> {
        val response = workspaceOperation(
            conversationId,
            "direct_calendar_changes",
            buildJsonObject { put("changes", changes) },
        )
        return parseSchedules(response.arr("schedules")).also {
            schedulesFlow.value = it
        }
    }

    suspend fun savePaper(paper: Paper): JsonObject = api.savePaper(
        buildJsonObject {
            put("title", paper.title)
            paper.arxiv_id?.let { put("arxiv_id", it) }
            paper.pdf_url?.let { put("pdf_url", it) }
            paper.source_url?.let { put("source_url", it) }
        },
    )

    suspend fun readPaper(conversationId: String, input: JsonObject): JsonObject =
        api.readPaper(conversationId, input)

    /**
     * 论文助读流式调用（后端 /reader）。
     * action: summarize / translate / analyze / qa
     */
    fun streamReader(
        conversationId: String,
        action: String,
        text: String,
        responseLanguage: String,
        fileId: String? = null,
        question: String? = null,
    ) = client.streamReader(
        conversationId,
        buildJsonObject {
            put("action", action)
            text.takeIf { it.isNotBlank() }?.let { put("text", it) }
            put("response_language", responseLanguage)
            fileId?.let { put("file_id", it) }
            question?.let { put("question", it) }
        },
    )

    suspend fun loadLibrary(): JsonObject = api.loadLibrary()

    suspend fun deleteReadingItem(id: String) = api.deleteLibrary(id = id)

    suspend fun deleteReadingFolder(folderId: String) = api.deleteLibrary(folderId = folderId)

    suspend fun updateReadingSettings(autoOrganize: Boolean): JsonObject =
        api.libraryOperation(buildJsonObject {
            put("operation", "settings")
            put("auto_organize", autoOrganize)
        })

    suspend fun createReadingFolder(name: String): JsonObject =
        api.libraryOperation(buildJsonObject {
            put("operation", "create_folder")
            put("name", name.trim())
        })

    suspend fun renameReadingFolder(folderId: String, name: String): JsonObject =
        api.libraryOperation(buildJsonObject {
            put("operation", "rename_folder")
            put("folder_id", folderId)
            put("name", name.trim())
        })

    suspend fun moveReadingItem(itemId: String, folderId: String?): JsonObject =
        api.libraryOperation(buildJsonObject {
            put("operation", "move_item")
            put("item_id", itemId)
            folderId?.let { put("folder_id", it) }
        })

    suspend fun touchReadingItem(itemId: String): JsonObject =
        api.libraryOperation(buildJsonObject {
            put("operation", "touch")
            put("id", itemId)
        })

    suspend fun saveAssistantResult(
        storageKey: String,
        action: String,
        title: String,
        sourceText: String,
        content: String,
    ): JsonObject = api.libraryOperation(buildJsonObject {
        put("operation", "save_assistant_result")
        put("storage_key", storageKey)
        put("action", action)
        put("title", title)
        put("source_text", sourceText)
        put("content", content)
    })

    suspend fun extractDocumentText(fileId: String): JsonObject = api.extractDocumentText(
        buildJsonObject { put("file_id", fileId) },
    )

    /**
     * Upload through the Maker-issued presigned URL, then let the backend own
     * PDF extraction and library registration. Android does not ship a second
     * PDF parser or duplicate Web's pdf.js behavior.
     */
    suspend fun uploadReadingDocument(
        conversationId: String,
        uri: Uri,
        filename: String,
        contentType: String = "application/pdf",
    ): JsonObject = withContext(Dispatchers.IO) {
        val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: error("无法读取文件")
        require(bytes.isNotEmpty()) { "文件为空" }
        require(bytes.size <= MAX_FILE_BYTES) { "文件不能超过 20 MB" }
        val intent = api.createFileUpload(
            buildJsonObject {
                put("conversation_id", conversationId)
                put("name", filename)
                put("content_type", contentType)
                put("size", bytes.size)
            },
        )
        val uploadUrl = intent.str("url") ?: error("未获得上传地址")
        val storageKey = intent.str("key") ?: intent.str("storage_key")
            ?: error("未获得文件标识")
        client.putPresigned(uploadUrl, contentType, bytes)
        val extracted = extractDocumentText(storageKey)
        val registered = api.libraryOperation(
            buildJsonObject {
                put("operation", "register")
                put("storage_key", storageKey)
                put("filename", filename)
                put("title", filename.substringBeforeLast('.').ifBlank { filename })
                put("mime_type", contentType)
                put("is_paper", true)
                put("page_count", extracted.int("page_count") ?: 0)
                put("preview", extracted.str("preview") ?: "")
            },
        )
        registered.obj("item") ?: registered
    }

    /** 阅读库条目（后端已自动整理为文件夹）。 */
    data class LibraryItem(
        val id: String,
        val storageKey: String,
        val fileId: String,
        val title: String,
        val folderId: String?,
        val isPaper: Boolean,
        val preview: String?,
    )

    data class LibraryFolder(val id: String, val name: String, val automatic: Boolean)

    data class Library(
        val items: List<LibraryItem> = emptyList(),
        val folders: List<LibraryFolder> = emptyList(),
        val autoOrganize: Boolean = true,
    ) {
        /** 尚未从后端取到任何内容。*/
        val isEmpty: Boolean get() = items.isEmpty() && folders.isEmpty()
    }

    suspend fun readingLibrary(): Library {
        val response = api.loadLibrary()
        val items = response.arr("items").orEmpty().mapNotNull { element ->
            val obj = element as? JsonObject ?: return@mapNotNull null
            LibraryItem(
                id = obj.str("id") ?: obj.str("storage_key") ?: return@mapNotNull null,
                storageKey = obj.str("storage_key") ?: obj.str("file_id")
                    ?: obj.str("id") ?: return@mapNotNull null,
                fileId = obj.str("file_id") ?: obj.str("storage_key")
                    ?: obj.str("id") ?: return@mapNotNull null,
                title = obj.str("title") ?: obj.str("filename").orEmpty(),
                folderId = obj.str("folder_id"),
                isPaper = obj.bool("is_paper") ?: false,
                preview = obj.str("preview"),
            )
        }
        val folders = response.arr("folders").orEmpty().mapNotNull { element ->
            val obj = element as? JsonObject ?: return@mapNotNull null
            LibraryFolder(
                id = obj.str("id") ?: return@mapNotNull null,
                name = obj.str("name").orEmpty(),
                automatic = obj.bool("automatic") ?: false,
            )
        }
        return Library(
            items = items,
            folders = folders,
            autoOrganize = response.obj("settings")?.bool("auto_organize") != false,
        )
    }

    suspend fun configureSkillConnection(
        conversationId: String,
        skillId: String,
        token: String,
    ): IntelligenceState = mutateIntelligence(
        conversationId = conversationId,
        operation = "configure_skill_connection",
        input = buildJsonObject {
            put("skill_id", skillId)
            put("token", token)
        },
    )

    suspend fun disconnectSkillConnection(
        conversationId: String,
        skillId: String,
    ): IntelligenceState = mutateIntelligence(
        conversationId = conversationId,
        operation = "disconnect_skill_connection",
        input = buildJsonObject { put("skill_id", skillId) },
    )

    /** Materialize a private Maker file using makers-parts-v1, never HTTP Range. */
    suspend fun materializeReadingDocument(item: LibraryItem): File = withContext(Dispatchers.IO) {
        val targetDir = File(context.cacheDir, "reading-files").apply { mkdirs() }
        val safeName = item.title.replace(Regex("[^0-9A-Za-z._\\-\\u4e00-\\u9fff]"), "_")
            .take(64).ifBlank { "document" }
        val target = File(targetDir, "${item.storageKey.hashCode().toUInt()}-$safeName.pdf")
        if (target.exists() && target.length() > 0) return@withContext target

        // A cancelled/failed multipart read must never leave a file that looks
        // complete to the next open attempt.
        val partial = File(targetDir, "${target.name}.part")
        partial.delete()

        val head = api.inspectFile(item.storageKey)
        require(head.isSuccessful) { "文件暂时无法读取" }
        val partCount = head.headers()["X-Floris-Part-Count"]?.toIntOrNull()
            ?: head.headers()["X-Yuanbao-Part-Count"]?.toIntOrNull()
            ?: 0
        try {
            FileOutputStream(partial).use { output ->
                if (partCount > 1) {
                    repeat(partCount) { part ->
                        val response = api.downloadFile(item.storageKey, part)
                        require(response.isSuccessful) { "文件分片读取失败" }
                        response.body()?.byteStream()?.use { it.copyTo(output) }
                            ?: error("文件分片为空")
                    }
                } else {
                    val response = api.downloadFile(item.storageKey)
                    require(response.isSuccessful) { "文件读取失败" }
                    response.body()?.byteStream()?.use { it.copyTo(output) }
                        ?: error("文件为空")
                }
            }
            require(partial.length() > 0) { "文件为空" }
            if (target.exists()) target.delete()
            check(partial.renameTo(target)) { "文件暂时无法保存" }
        } catch (error: Throwable) {
            partial.delete()
            throw error
        }
        target
    }

    // ---------- User Skill intake ----------

    suspend fun listSkillUploads(): List<SkillUploadRecord> =
        api.listSkillUploads().arr("uploads").orEmpty().mapNotNull { raw ->
            runCatching {
                json.decodeFromJsonElement(SkillUploadRecord.serializer(), raw)
            }.getOrNull()
        }

    suspend fun resolveSkillUrl(sourceUrl: String): JsonObject =
        api.mutateSkillUpload(buildJsonObject {
            put("operation", "resolve_url")
            put("source_url", sourceUrl)
        })

    suspend fun uploadSkillPackage(uri: Uri, filename: String): JsonObject =
        withContext(Dispatchers.IO) {
            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                ?: error("无法读取文件")
            require(bytes.isNotEmpty()) { "文件为空" }
            require(bytes.size <= MAX_SKILL_BYTES) { "Skill 包不能超过 2 MB" }
            val intent = api.mutateSkillUpload(buildJsonObject {
                put("operation", "create")
                put("name", filename)
                put("content_type", "application/zip")
                put("size", bytes.size)
            })
            val uploadId = intent.str("upload_id") ?: error("未获得上传标识")
            val storageKey = intent.str("storage_key") ?: error("未获得存储标识")
            val uploadUrl = intent.str("url") ?: error("未获得上传地址")
            client.putPresigned(uploadUrl, "application/zip", bytes)
            api.mutateSkillUpload(buildJsonObject {
                put("operation", "complete")
                put("upload_id", uploadId)
                put("storage_key", storageKey)
                put("name", filename)
            }).obj("upload") ?: error("Skill 保存失败")
        }

    suspend fun requestSkillReview(uploadId: String): JsonObject =
        api.mutateSkillUpload(buildJsonObject {
            put("operation", "publish")
            put("upload_id", uploadId)
        })

    suspend fun publishDeclarativeSkill(
        sourceSkillId: String,
        name: String,
        description: String,
        instructions: String,
        installedAt: Long = System.currentTimeMillis(),
    ): JsonObject = api.mutateSkillUpload(buildJsonObject {
        put("operation", "publish_declarative")
        put("source_skill_id", sourceSkillId)
        put("name", name)
        put("description", description)
        put("instructions", instructions)
        put("installed_at", installedAt)
    })

    suspend fun installUserSkill(skill: JsonObject): JsonObject =
        api.intelligenceOperation(
            activeConversationId(),
            buildJsonObject {
                put("operation", "install_user_skill")
                put("skill", skill)
            },
        )

    suspend fun installUserSkillText(
        name: String,
        description: String,
        instructions: String,
        sourceType: String = "paste",
        sourceUrl: String = "",
    ): JsonObject {
        val clean = instructions.trim()
        require(clean.isNotEmpty()) { "Skill 内容不能为空" }
        require(clean.length <= MAX_SKILL_INSTRUCTIONS) { "Skill 内容不能超过 12000 字" }
        return installUserSkill(buildJsonObject {
            put("name", name.trim().ifBlank { "我的 Skill" }.take(80))
            put("description", description.trim().take(280))
            put("instructions", clean)
            put("source_type", sourceType)
            put("source_url", sourceUrl.trim().take(1000))
        })
    }

    suspend fun importUserSkillFile(uri: Uri, filename: String): JsonObject =
        withContext(Dispatchers.IO) {
            if (filename.endsWith(".zip", ignoreCase = true)) {
                return@withContext uploadSkillPackage(uri, filename)
            }
            val text = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                ?: error("无法读取文件")
            val metadata = Regex("^---\\s*\\n([\\s\\S]*?)\\n---", RegexOption.MULTILINE)
                .find(text)?.groupValues?.getOrNull(1).orEmpty()
            fun field(key: String): String = Regex(
                "(?mi)^${Regex.escape(key)}:\\s*(.+)$",
            ).find(metadata)?.groupValues?.getOrNull(1)?.trim()?.trim('\'', '"').orEmpty()
            installUserSkillText(
                name = field("name").ifBlank {
                    filename.substringBeforeLast('.').replace('-', ' ').replace('_', ' ')
                },
                description = field("description"),
                instructions = text,
                sourceType = if (filename.endsWith(".json", true)) "package" else "file",
            )
        }

    suspend fun setUserSkillEnabled(skillId: String, enabled: Boolean): JsonObject =
        api.intelligenceOperation(
            activeConversationId(),
            buildJsonObject {
                put("operation", "set_user_skill_enabled")
                put("skill_id", skillId)
                put("enabled", enabled)
            },
        )

    suspend fun removeUserSkill(skillId: String): JsonObject =
        api.intelligenceOperation(
            activeConversationId(),
            buildJsonObject {
                put("operation", "remove_user_skill")
                put("skill_id", skillId)
            },
        )

    fun streamImageEdit(conversationId: String, prompt: String, parentActionId: String) =
        client.streamImageEdit(
            conversationId,
            buildJsonObject {
                put("prompt", prompt)
                put("parent_action_id", parentActionId)
            },
        )

    // ---------- Profile / Proactive / Usage ----------

    suspend fun getProfile(): Profile = api.getProfile()

    suspend fun updateDisplayName(name: String) {
        updateProfile(name, null)
    }

    suspend fun loadCachedAvatar() = withContext(Dispatchers.IO) {
        localAvatarFlow.value = avatarCacheFile().takeIf { it.exists() && it.length() > 0 }?.absolutePath
    }

    suspend fun updateProfile(displayName: String, avatarUri: Uri?): Profile {
        var avatarKey: String? = null
        var avatarBytes: ByteArray? = null
        var avatarType = "image/jpeg"
        if (avatarUri != null) {
            avatarType = context.contentResolver.getType(avatarUri)
                ?.takeIf { it in setOf("image/png", "image/jpeg", "image/webp") }
                ?: "image/jpeg"
            avatarBytes = withContext(Dispatchers.IO) {
                context.contentResolver.openInputStream(avatarUri)?.use { it.readBytes() }
            } ?: error("无法读取头像")
            require(avatarBytes.isNotEmpty()) { "头像文件为空" }
            require(avatarBytes.size <= MAX_AVATAR_BYTES) { "头像不能超过 5 MB" }
            val intent = api.profileOperation(buildJsonObject {
                put("operation", "create_avatar_upload")
                put("content_type", avatarType)
                put("size", avatarBytes.size)
            })
            avatarKey = intent.str("key") ?: error("未获得头像上传标识")
            client.putPresigned(
                intent.str("url") ?: error("未获得头像上传地址"),
                avatarType,
                avatarBytes,
            )
        }
        api.profileOperation(buildJsonObject {
            put("operation", "update")
            put("display_name", displayName.trim())
            avatarKey?.let { put("avatar_key", it) }
        })
        if (avatarBytes != null) {
            withContext(Dispatchers.IO) {
                val file = avatarCacheFile()
                file.parentFile?.mkdirs()
                file.writeBytes(avatarBytes)
                localAvatarFlow.value = file.absolutePath
            }
        }
        return api.getProfile()
    }

    private fun avatarCacheFile(): File {
        val subject = (client.authManager.state.value as? com.floris.android.core.auth.AuthState.SignedIn)
            ?.identity?.subject_id.orEmpty().ifBlank { "guest" }
        return File(context.filesDir, "profile/avatars/${subject.hashCode().toUInt()}.cache")
    }

    suspend fun proactive(conversationId: String, operation: String, input: JsonObject = JsonObject(emptyMap())): JsonObject =
        api.proactiveOperation(
            conversationId,
            JsonObject(buildMap {
                put("operation", JsonPrimitive(operation))
                input.forEach { (key, value) -> put(key, value) }
            }),
        )

    suspend fun proactiveState(conversationId: String): ProactiveState =
        decodeProactive(proactive(conversationId, "get"))

    suspend fun mutateProactive(
        conversationId: String,
        operation: String,
        input: JsonObject = JsonObject(emptyMap()),
    ): ProactiveState = decodeProactive(proactive(conversationId, operation, input))

    private fun decodeProactive(response: JsonObject): ProactiveState =
        json.decodeFromJsonElement(ProactiveState.serializer(), response)

    fun parseProactiveNotifications(response: JsonObject): List<ProactiveNotification> {
        val raw = response.arr("notifications") ?: response.arr("items") ?: response.arr("briefs")
        return raw.orEmpty().mapNotNull { element ->
            runCatching {
                json.decodeFromJsonElement(ProactiveNotification.serializer(), element)
            }.getOrNull()
        }
    }

    suspend fun providerUsage(conversationId: String): JsonObject = api.providerUsage(conversationId)

    /**
     * Three-step account data reset, mirroring the Web client:
     * inspect files → reset Makers state → clear stored files.
     */
    suspend fun resetAll(conversationId: String) {
        val confirmation = "DELETE"
        val inspect = api.resetFiles(buildJsonObject {
            put("confirmation", confirmation)
            put("operation", "inspect")
        })
        val conversationIds = inspect.arr("conversation_ids") ?: JsonArray(emptyList())
        api.resetState(conversationId, buildJsonObject {
            put("confirmation", confirmation)
            put("conversation_ids", conversationIds)
        })
        api.resetFiles(buildJsonObject {
            put("confirmation", confirmation)
            put("operation", "clear")
        })
    }

    // ---------- Attachments ----------

    /** Compress a picked image to a <=1280px JPEG data URL (contract: max 3). */
    suspend fun imageToDataUrl(uri: Uri): String? = withContext(Dispatchers.IO) {
        runCatching {
            val source = context.contentResolver.openInputStream(uri)
                ?.use { BitmapFactory.decodeStream(it) }
                ?: error("cannot decode image")
            val maxSide = 1280
            val scale = minOf(1f, maxSide.toFloat() / maxOf(source.width, source.height))
            val bitmap = if (scale < 1f) {
                Bitmap.createScaledBitmap(
                    source,
                    (source.width * scale).toInt().coerceAtLeast(1),
                    (source.height * scale).toInt().coerceAtLeast(1),
                    true,
                )
            } else source
            val output = ByteArrayOutputStream()
            var quality = 88
            bitmap.compress(Bitmap.CompressFormat.JPEG, quality, output)
            while (output.size() > 1_800_000 && quality > 40) {
                output.reset()
                quality -= 12
                bitmap.compress(Bitmap.CompressFormat.JPEG, quality, output)
            }
            "data:image/jpeg;base64," + Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP)
        }.getOrNull()
    }

    private companion object {
        const val MAX_FILE_BYTES = 20 * 1024 * 1024
        const val MAX_SKILL_BYTES = 2 * 1024 * 1024
        const val MAX_SKILL_INSTRUCTIONS = 12_000
        const val MAX_AVATAR_BYTES = 5 * 1024 * 1024
    }
}

// ---------- JsonObject helpers ----------

fun JsonObject.str(key: String): String? = this[key]?.jsonPrimitive?.contentOrNull
fun JsonObject.num(key: String): Long? = this[key]?.jsonPrimitive?.longOrNull
fun JsonObject.bool(key: String): Boolean? = this[key]?.jsonPrimitive?.booleanOrNull
fun JsonObject.int(key: String): Int? = this[key]?.jsonPrimitive?.intOrNull
fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray
fun JsonElement?.asString(): String? = (this as? JsonPrimitive)?.contentOrNull
