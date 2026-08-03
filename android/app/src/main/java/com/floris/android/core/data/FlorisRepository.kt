package com.floris.android.core.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.model.ConversationBootstrap
import com.floris.android.core.model.ConversationSummary
import com.floris.android.core.model.Paper
import com.floris.android.core.model.Place
import com.floris.android.core.model.Profile
import com.floris.android.core.model.RoutePlan
import com.floris.android.core.model.Schedule
import com.floris.android.core.model.Skill
import com.floris.android.core.model.SkillMarketplaceState
import com.floris.android.core.network.FlorisClient
import kotlinx.coroutines.flow.first
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
import java.util.UUID

data class MapWorkspaceState(
    val places: List<Place> = emptyList(),
    val title: String? = null,
    val routeMode: String? = null,
    val routeStrategy: String? = null,
    val showRoute: Boolean = false,
    val revision: Long = 0,
)

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

    suspend fun stop(conversationId: String) {
        api.stop(conversationId, buildJsonObject { put("conversation_id", conversationId) })
    }

    suspend fun touchConversation(conversationId: String, title: String, messageCount: Int) {
        api.touchConversation(
            conversationId,
            buildJsonObject {
                put("operation", "touch_pointer")
                put("conversation_id", conversationId)
                put("title", title)
                put("message_count", messageCount)
            },
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
            ConversationSummary(
                id = id,
                title = metadata?.str("title") ?: obj.str("title") ?: "新对话",
                createdAt = obj.num("createdAt") ?: obj.num("created_at") ?: 0,
                updatedAt = obj.num("lastMessageAt") ?: obj.num("updatedAt")
                    ?: obj.num("updated_at") ?: obj.num("createdAt") ?: 0,
                messageCount = (obj.num("messageCount") ?: obj.num("message_count") ?: 0).toInt(),
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

    suspend fun intelligencePreferences(conversationId: String): JsonObject =
        api.intelligenceOperation(conversationId, buildJsonObject { put("operation", "get") })

    suspend fun setSkillEnabled(conversationId: String, skillId: String, enabled: Boolean) {
        api.intelligenceOperation(
            conversationId,
            buildJsonObject {
                put("operation", "update_skill_preferences")
                putJsonObject("preferences") { put(skillId, enabled) }
            },
        )
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

    suspend fun readPaper(conversationId: String, input: JsonObject): JsonObject =
        api.readPaper(conversationId, input)

    suspend fun loadLibrary(): JsonObject = api.loadLibrary()

    // ---------- Profile / Proactive / Usage ----------

    suspend fun getProfile(): Profile = api.getProfile()

    suspend fun updateDisplayName(name: String) {
        api.profileOperation(buildJsonObject {
            put("operation", "update")
            put("display_name", name)
        })
    }

    suspend fun proactive(conversationId: String, operation: String, input: JsonObject = JsonObject(emptyMap())): JsonObject =
        api.proactiveOperation(
            conversationId,
            JsonObject(buildMap {
                put("operation", JsonPrimitive(operation))
                input.forEach { (key, value) -> put(key, value) }
            }),
        )

    suspend fun providerUsage(conversationId: String): JsonObject = api.providerUsage(conversationId)

    /**
     * Three-step account data reset, mirroring the Web client:
     * inspect files → reset Makers state → clear stored files.
     */
    suspend fun resetAll(conversationId: String) {
        val confirmation = "RESET"
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
}

// ---------- JsonObject helpers ----------

fun JsonObject.str(key: String): String? = this[key]?.jsonPrimitive?.contentOrNull
fun JsonObject.num(key: String): Long? = this[key]?.jsonPrimitive?.longOrNull
fun JsonObject.bool(key: String): Boolean? = this[key]?.jsonPrimitive?.booleanOrNull
fun JsonObject.int(key: String): Int? = this[key]?.jsonPrimitive?.intOrNull
fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray
fun JsonElement?.asString(): String? = (this as? JsonPrimitive)?.contentOrNull
