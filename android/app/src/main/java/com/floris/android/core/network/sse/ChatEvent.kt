package com.floris.android.core.network.sse

import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ExperienceHintItem
import com.floris.android.core.model.PaperResults
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

/** Typed view of chat-events-v1.schema.json. Unknown events become [Ignored]. */
sealed interface ChatEvent {
    data class AiResponse(val content: String) : ChatEvent
    data object AiResponseReset : ChatEvent
    data class ToolActivity(val isCall: Boolean, val name: String, val content: String?) : ChatEvent
    data class Progress(val payload: ProgressComponent) : ChatEvent
    data class StageTiming(val timingsMs: Map<String, Double>) : ChatEvent
    data class SearchResults(val payload: SearchMeta) : ChatEvent
    data class SearchMedia(val payload: SearchMeta) : ChatEvent
    data class PaperResultsEvent(val payload: PaperResults) : ChatEvent
    data class WorkspaceActionEvent(val eventType: String, val action: WorkspaceAction) : ChatEvent
    data class ImageAction(val action: WorkspaceAction) : ChatEvent
    data class ClarificationEvent(val clarification: Clarification) : ChatEvent
    data class LocationRequest(val reason: String) : ChatEvent
    data class ExperienceHint(val items: List<ExperienceHintItem>) : ChatEvent
    data class AnswerComplete(val turnId: String?) : ChatEvent
    data class FollowUps(val items: List<String>) : ChatEvent
    data class ProactiveUpdate(val payload: JsonObject) : ChatEvent
    data class Usage(val inputTokens: Long, val outputTokens: Long, val totalTokens: Long) : ChatEvent
    data class Ping(val ts: Long) : ChatEvent
    data class Error(val code: String, val content: String) : ChatEvent

    /** Forward-compatible: v1 clients ignore unknown event types. */
    data object Ignored : ChatEvent

    /** A frame that is not valid JSON at all. */
    data class Malformed(val raw: String) : ChatEvent
}

/** Parses raw SSE frames into [ChatEvent]s; never throws on unknown shapes. */
class ChatEventDispatcher(private val json: Json) {

    fun dispatch(frame: String): ChatEvent {
        val element = runCatching { json.parseToJsonElement(frame) }.getOrNull()
            ?: return ChatEvent.Malformed(frame)
        val obj = element as? JsonObject ?: return ChatEvent.Malformed(frame)
        val type = obj["type"]?.jsonPrimitive?.content ?: return ChatEvent.Ignored
        return runCatching { dispatchTyped(type, obj) }.getOrDefault(ChatEvent.Ignored)
    }

    private fun dispatchTyped(type: String, obj: JsonObject): ChatEvent = when (type) {
        "ai_response" -> ChatEvent.AiResponse(obj.str("content"))
        "ai_response_reset" -> ChatEvent.AiResponseReset
        "tool_call" -> ChatEvent.ToolActivity(true, obj.str("name"), obj.strOrNull("content"))
        "tool_result" -> ChatEvent.ToolActivity(false, obj.str("name"), obj.strOrNull("content"))
        "progress_event" -> ChatEvent.Progress(
            json.decodeFromJsonElement(ProgressComponent.serializer(), obj.requiredPayload()),
        )
        "stage_timing" -> ChatEvent.StageTiming(
            (obj["timings_ms"] as? JsonObject).orEmpty().mapNotNull { (stage, value) ->
                value.jsonPrimitive.doubleOrNull?.let { stage to it }
            }.toMap(),
        )
        "search_results" -> ChatEvent.SearchResults(
            json.decodeFromJsonElement(SearchMeta.serializer(), obj.requiredPayload()),
        )
        "search_media" -> ChatEvent.SearchMedia(
            json.decodeFromJsonElement(SearchMeta.serializer(), obj.requiredPayload()),
        )
        "paper_results" -> ChatEvent.PaperResultsEvent(
            json.decodeFromJsonElement(PaperResults.serializer(), obj.requiredPayload()),
        )
        "map_action", "calendar_action", "side_effect_action" -> {
            val payload = obj.payload()
            val actionElement = payload["action"] ?: payload
            ChatEvent.WorkspaceActionEvent(
                type,
                json.decodeFromJsonElement(WorkspaceAction.serializer(), actionElement),
            )
        }
        "image_action" -> ChatEvent.ImageAction(
            json.decodeFromJsonElement(
                WorkspaceAction.serializer(),
                obj["action"] ?: obj.payload()["action"] ?: throw IllegalArgumentException("missing action"),
            ),
        )
        "clarification_action" -> {
            val payload = obj.payload()
            val clarification = payload["clarification"] ?: payload
            ChatEvent.ClarificationEvent(
                json.decodeFromJsonElement(Clarification.serializer(), clarification),
            )
        }
        "browser_location_request" -> ChatEvent.LocationRequest(
            (obj["payload"] as? JsonObject)?.str("reason") ?: "",
        )
        "experience_hint" -> {
            val payload = obj.payload()
            val items = payload["items"]?.jsonArray?.mapNotNull { item ->
                runCatching {
                    json.decodeFromJsonElement(ExperienceHintItem.serializer(), item)
                }.getOrNull()
            }.orEmpty()
            ChatEvent.ExperienceHint(items)
        }
        "answer_complete" -> ChatEvent.AnswerComplete(
            (obj["payload"] as? JsonObject)?.strOrNull("turn_id"),
        )
        "follow_ups" -> ChatEvent.FollowUps(
            obj.payload()["items"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty(),
        )
        "proactive_update" -> ChatEvent.ProactiveUpdate(obj.payload())
        "usage" -> ChatEvent.Usage(
            obj["input_tokens"]?.jsonPrimitive?.longOrNull ?: 0,
            obj["output_tokens"]?.jsonPrimitive?.longOrNull ?: 0,
            obj["total_tokens"]?.jsonPrimitive?.longOrNull ?: 0,
        )
        "ping" -> ChatEvent.Ping(obj["ts"]?.jsonPrimitive?.longOrNull ?: 0)
        "error_message" -> ChatEvent.Error(obj.str("code"), obj.str("content"))
        else -> ChatEvent.Ignored
    }

    private fun JsonObject.payload(): JsonObject = (this["payload"] as? JsonObject) ?: JsonObject(emptyMap())

    /** Component events must carry an object payload; otherwise degrade to Ignored. */
    private fun JsonObject.requiredPayload(): JsonObject =
        this["payload"] as? JsonObject ?: throw IllegalArgumentException("missing payload")
    private fun JsonObject.str(key: String): String = this[key]?.jsonPrimitive?.content ?: ""
    private fun JsonObject.strOrNull(key: String): String? =
        this[key]?.jsonPrimitive?.content?.takeIf { it.isNotEmpty() }
}
