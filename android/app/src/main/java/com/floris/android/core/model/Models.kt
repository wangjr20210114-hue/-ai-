package com.floris.android.core.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// ---------- Identity ----------

@Serializable
data class Identity(
    val id: String = "",
    val subject_id: String = "",
    val tenant_id: String = "",
    val auth_type: String = "guest",
    val membership: String = "guest",
    val display_name: String? = null,
    val avatar_url: String? = null,
    val roles: List<String> = emptyList(),
)

@Serializable
data class MobileSession(
    val access_token: String = "",
    val token_type: String = "Bearer",
    val expires_in: Long = 3600,
    val contract_version: String = "1",
    val identity: Identity = Identity(),
)

// ---------- Chat ----------

@Serializable
data class ChatTurnRequest(
    val message: String,
    val client_message_id: String? = null,
    val reference_images: List<String>? = null,
    val clarification_response: JsonObject? = null,
    val current_location: JsonObject? = null,
    val document_context: JsonObject? = null,
)

@Serializable
data class ConversationSummary(
    val id: String = "",
    val title: String = "",
    val createdAt: Long = 0,
    val updatedAt: Long = 0,
    val messageCount: Int = 0,
    val activityStatus: String = "idle",
)

@Serializable
data class ConversationBootstrap(
    val messages: List<JsonObject> = emptyList(),
    val workspace_revision: Long = 0,
    val schedules: List<JsonObject> = emptyList(),
    val map_places: List<JsonObject> = emptyList(),
)

// ---------- Components (floris-components-v1) ----------

@Serializable
data class ProgressComponent(
    val schema_version: Int = 1,
    val stage: String = "planning",
    val status: String = "active",
    val activity: String = "general",
    val source: String = "controller",
    val updated_at: Long? = null,
)

@Serializable
data class SearchSource(
    val id: String = "",
    val title: String = "",
    val url: String = "",
    val source: String? = null,
    val snippet: String? = null,
    val date: String? = null,
)

@Serializable
data class MediaItem(
    val id: String = "",
    val kind: String = "image",
    val url: String = "",
    val alt: String = "",
    val caption: String = "",
    val generated: Boolean = false,
    val source_title: String? = null,
    val source_url: String? = null,
    val attribution: String? = null,
    val preview: Boolean? = null,
    val vision_reviewed: Boolean? = null,
)

@Serializable
data class SearchMeta(
    val query: String = "",
    val results: List<SearchSource> = emptyList(),
    val images: List<String> = emptyList(),
    val media: List<MediaItem> = emptyList(),
    val sources_used: List<String> = emptyList(),
    val total: Int = 0,
    val target_date: String? = null,
    val strict_date: Boolean? = null,
    val media_pending: Boolean? = null,
)

@Serializable
data class Paper(
    val title: String = "",
    val arxiv_id: String? = null,
    val authors: String? = null,
    val year: Int? = null,
    val abstract_zh: String? = null,
    val key_contribution: String? = null,
    val citations: Int? = null,
    val arxiv_url: String? = null,
    val pdf_url: String? = null,
    val source: String? = null,
    val source_url: String? = null,
)

@Serializable
data class PaperResults(
    val papers: List<Paper> = emptyList(),
    val topic: String? = null,
)

@Serializable
data class Place(
    val place_id: String = "",
    val provider: String? = null,
    val name: String = "",
    val address: String = "",
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    val city: String? = null,
    val category: String? = null,
)

@Serializable
data class WorkspaceActionPayload(
    val title: String? = null,
    val action_text: String? = null,
    val places: List<Place> = emptyList(),
    val route_mode: String? = null,
    val route_strategy: String? = null,
    val show_route: Boolean? = null,
    val route_plan_id: String? = null,
    val calendar_offer: Boolean? = null,
    val summary: String? = null,
    val changes: List<JsonObject> = emptyList(),
    val subject: String? = null,
    val start_time: String? = null,
    val end_time: String? = null,
    val warnings: List<String> = emptyList(),
    val missing_fields: List<String> = emptyList(),
    val validation_errors: List<String> = emptyList(),
    val prompt: String? = null,
    val parent_action_id: String? = null,
    val group_id: String? = null,
)

@Serializable
data class WorkspaceAction(
    val schema_version: Int = 1,
    val id: String = "",
    val kind: String = "",
    val status: String = "ready",
    val version: Int = 0,
    val payload: WorkspaceActionPayload = WorkspaceActionPayload(),
    val result: JsonObject? = null,
    val error: String? = null,
    val snapshot_hash: String? = null,
    val idempotency_key: String? = null,
) {
    val isKnownKind: Boolean
        get() = kind in setOf("map_recommendation", "calendar_changes", "meeting_create", "image_generate")
}

@Serializable
data class ClarificationField(
    val id: String = "",
    val label: String = "",
    val type: String = "text",
    val options: List<String> = emptyList(),
    val option_values: Map<String, String> = emptyMap(),
    val required: Boolean = false,
    val placeholder: String? = null,
)

@Serializable
data class Clarification(
    val id: String = "",
    val title: String = "",
    val prompt: String = "",
    val fields: List<ClarificationField> = emptyList(),
)

@Serializable
data class ExperienceHintItem(
    val kind: String = "",
    val skill_ids: List<String> = emptyList(),
    val login_required: Boolean? = null,
)

// ---------- Maps / Routes ----------

@Serializable
data class RouteLeg(
    val mode: String? = null,
    val distance_text: String? = null,
    val duration_text: String? = null,
    val instruction: String? = null,
    val polyline: List<List<Double>> = emptyList(),
)

@Serializable
data class RoutePlan(
    val id: String? = null,
    val mode: String? = null,
    val strategy: String? = null,
    val distance_text: String? = null,
    val duration_text: String? = null,
    val cost_text: String? = null,
    val ordered_stops: List<Place> = emptyList(),
    val legs: List<RouteLeg> = emptyList(),
    val polyline: List<List<Double>> = emptyList(),
)

// ---------- Skills ----------

@Serializable
data class Skill(
    val id: String = "",
    val name: Map<String, String> = emptyMap(),
    val description: Map<String, String> = emptyMap(),
    val category: String? = null,
    val version: String? = null,
    val requires: List<String> = emptyList(),
    val enabled: Boolean? = null,
    val locked: Boolean? = null,
    val builtin: Boolean? = null,
    val publisher: JsonObject? = null,
)

@Serializable
data class SkillMarketplaceState(
    val skills: List<Skill> = emptyList(),
    val dependency_graph: JsonObject? = null,
    val component_api: JsonObject? = null,
    val enabled: List<String> = emptyList(),
)

// ---------- Calendar ----------

@Serializable
data class Schedule(
    val id: String = "",
    val title: String = "",
    val start_time: Long = 0,
    val end_time: Long = 0,
    val location: String? = null,
    val place: Place? = null,
    val location_kind: String? = null,
    val notes: String? = null,
    val source_route_plan_id: String? = null,
    val deleted: Boolean? = null,
)

// ---------- Profile / Intelligence ----------

@Serializable
data class Profile(
    val display_name: String? = null,
    val avatar_url: String? = null,
    val membership: String? = null,
    val email: String? = null,
)

@Serializable
data class ProactiveBrief(
    val id: String = "",
    val title: String = "",
    val summary: String? = null,
    val kind: String? = null,
    val priority: String? = null,
    val created_at: Long? = null,
    val payload: JsonObject? = null,
)
