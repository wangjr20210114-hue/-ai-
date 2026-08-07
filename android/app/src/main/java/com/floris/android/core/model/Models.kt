package com.floris.android.core.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
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
    val pending: Boolean = false,
    val manuallyRenamed: Boolean = false,
    val activityStatus: String = "idle",
)

@Serializable
data class ConversationBootstrap(
    val messages: List<JsonObject> = emptyList(),
    val workspace_revision: Long = 0,
    val schedules: List<JsonObject> = emptyList(),
    val map_places: List<JsonObject> = emptyList(),
    val map_title: String = "",
    val map_route_mode: String = "",
    val map_route_strategy: String = "",
    val map_route: JsonObject? = null,
    val map_show_route: Boolean = false,
    val run: ChatRun? = null,
    val presentation: RunPresentation? = null,
)

/** Public Maker run state. It never contains private model reasoning. */
@Serializable
data class ChatRun(
    val run_id: String = "",
    val client_message_id: String = "",
    val status: String = "",
    val error: String? = null,
    val started_at: Long? = null,
    val updated_at: Long? = null,
    val completed_at: Long? = null,
    val diagnostics: JsonObject? = null,
) {
    val active: Boolean get() = status == "running" || status == "cancel_requested"
}

/**
 * Bounded UI snapshot published by the Maker backend while a turn is running.
 * Android restores this projection after process death instead of starting a
 * second, downgraded model request.
 */
@Serializable
data class RunPresentation(
    val schema_version: Int = 1,
    val run_id: String = "",
    val client_message_id: String = "",
    val revision: Long = 0,
    val updated_at: Long = 0,
    val turn_started_at: Long? = null,
    val search_selected: Boolean = false,
    val search_started_at: Long? = null,
    val search_completed_at: Long? = null,
    val active_activity: String? = null,
    val content: String = "",
    val progress: List<JsonObject> = emptyList(),
    val search_results: JsonObject? = null,
    val search_media: JsonObject? = null,
    val workspace_actions: List<WorkspaceAction> = emptyList(),
    val clarification: Clarification? = null,
    val papers: PaperResults? = null,
    val follow_ups: List<String> = emptyList(),
    val experience_hints: List<ExperienceHintItem> = emptyList(),
    val error: String? = null,
)

@Serializable
data class ChatRunState(
    val run: ChatRun? = null,
    val presentation: RunPresentation? = null,
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
    val source_id: String? = null,
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
    /** floris-components-v1: 各阶段耗时（毫秒），如 timings_ms.search。 */
    val timings_ms: Map<String, Double> = emptyMap(),
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
    val allow_custom_input: Boolean = false,
    val custom_placeholder: String? = null,
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
    val from: Place? = null,
    val to: Place? = null,
    val scope: String? = null,
    val mode: String? = null,
    val distance_text: String? = null,
    val duration_text: String? = null,
    val instruction: String? = null,
    val polyline: List<List<Double>> = emptyList(),
    val path: List<RoutePoint> = emptyList(),
    val sections: List<RouteSection> = emptyList(),
    val distance_meters: Double = 0.0,
    val duration_seconds: Double = 0.0,
)

@Serializable
data class RoutePoint(
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
)

@Serializable
data class RouteSection(
    val mode: String = "walking",
    val path: List<RoutePoint> = emptyList(),
    val distance_meters: Double = 0.0,
    val duration_seconds: Double = 0.0,
    val line: String? = null,
    val vehicle: String? = null,
    val geton: String? = null,
    val getoff: String? = null,
    val station_count: Int? = null,
    val instruction: String? = null,
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
    val schema_version: Int = 1,
    val provider: String = "",
    val places: List<Place> = emptyList(),
    val path: List<RoutePoint> = emptyList(),
    val distance_meters: Double = 0.0,
    val duration_seconds: Double = 0.0,
    val fare: JsonObject = JsonObject(emptyMap()),
    val transit: JsonObject? = null,
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
    val installed: Boolean? = null,
    val eligible: Boolean? = null,
    val required_plan: String? = null,
    val eligibility_reason: String? = null,
    val conflicts: List<String> = emptyList(),
    val recommends: List<String> = emptyList(),
    val capabilities: List<String> = emptyList(),
    val component_actions: List<String> = emptyList(),
    val external: Boolean = false,
    val configured: Boolean = false,
    val connect_url: String = "",
    val credential: SkillCredential? = null,
    val publisher: JsonObject? = null,
)

@Serializable
data class SkillCredential(
    val kind: String = "token",
    val ttl_seconds: Long = 0,
    val help_url: String = "",
    val instructions: Map<String, String> = emptyMap(),
)

@Serializable
data class SkillConnectionState(
    val configured: Boolean = false,
    val connected_at: Long = 0,
    val expires_at: Long = 0,
)

@Serializable
data class UserSkill(
    val id: String = "",
    val name: String = "",
    val description: String = "",
    val instructions: String = "",
    val source_type: String = "",
    val source_url: String = "",
    val enabled: Boolean = true,
    val installed_at: Long = 0,
    val updated_at: Long = 0,
    val review_status: String = "not_submitted",
)

@Serializable
data class SkillUploadRecord(
    val id: String = "",
    val name: String = "",
    val status: String = "stored",
    val visibility: String = "private",
    val review_status: String = "not_submitted",
    val review_available: Boolean = false,
    val source_type: String = "zip",
    val source_skill_id: String? = null,
    val description: String? = null,
    val size: Long = 0,
    val installed_at: Long? = null,
    val review_requested_at: Long? = null,
)

@Serializable
data class SkillComponentAction(
    val id: String = "",
    val category: String = "",
    val name: Map<String, String> = emptyMap(),
    val description: String = "",
    val description_i18n: Map<String, String> = emptyMap(),
    val input: Map<String, String> = emptyMap(),
    val required: List<String> = emptyList(),
)

@Serializable
data class SkillComponentApi(
    val version: String = "",
    val actions: List<SkillComponentAction> = emptyList(),
)

@Serializable
data class SkillMarketplaceState(
    val skills: List<Skill> = emptyList(),
    val preferences: Map<String, Boolean> = emptyMap(),
    val connections: Map<String, SkillConnectionState> = emptyMap(),
    val user_skills: List<UserSkill> = emptyList(),
    val entitlements: JsonObject? = null,
    val identity: Identity? = null,
    val dependency_graph: JsonObject? = null,
    val component_api: SkillComponentApi? = null,
    val enabled: List<String> = emptyList(),
)

// ---------- Calendar ----------

@Serializable
data class Schedule(
    val id: String = "",
    val title: String = "",
    val start_time: Long = 0,
    val end_time: Long = 0,
    val duration_minutes: Int = 0,
    val duration_days: Int = 0,
    val category: String? = null,
    val location: String? = null,
    val place: Place? = null,
    val location_kind: String? = null,
    val notes: String? = null,
    val description: String? = null,
    val markdown_content: String? = null,
    val done: Boolean = false,
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
data class MapPreferences(
    val service_mode: String = "balanced",
    val place_result_limit: Int = 6,
    val route_stop_limit: Int = 8,
    val search_timeout_seconds: Int = 30,
    val preferred_route_mode: String = "driving",
    val route_strategy: String = "time_then_cost",
    val near_time_tolerance_minutes: Int = 10,
    val learn_route_preferences: Boolean = true,
)

@Serializable
data class MemoryHistoryEntry(
    val version: Int = 0,
    val value: JsonElement = JsonNull,
    val sensitivity: String = "normal",
    val updated_at: Long = 0,
)

@Serializable
data class MemoryProposal(
    val id: String = "",
    val memory_key: String = "",
    val value: JsonElement = JsonNull,
    val reason: String = "",
    val sensitivity: String = "normal",
    val status: String = "pending",
    val version: Int = 0,
    val created_at: Long = 0,
    val updated_at: Long = 0,
)

@Serializable
data class UserMemory(
    val id: String = "",
    val memory_key: String = "",
    val value: JsonElement = JsonNull,
    val confidence: Double = 0.0,
    val sensitivity: String = "normal",
    val version: Int = 0,
    val history: List<MemoryHistoryEntry> = emptyList(),
    val created_at: Long = 0,
    val updated_at: Long = 0,
)

@Serializable
data class ProactiveRuleProposal(
    val id: String = "",
    val kind: String = "",
    val target: String = "",
    val reason: String = "",
    val status: String = "pending",
    val version: Int = 0,
    val created_at: Long = 0,
    val updated_at: Long = 0,
)

@Serializable
data class IntelligenceState(
    val schema_version: Int = 1,
    val revision: Int = 0,
    val memory_proposals: List<MemoryProposal> = emptyList(),
    val memories: List<UserMemory> = emptyList(),
    val memory_count: Int = memories.size,
    val memory_preferences: MemoryPreferences = MemoryPreferences(),
    val search_preferences: SearchPreferences = SearchPreferences(),
    val map_preferences: MapPreferences = MapPreferences(),
    val rule_proposals: List<ProactiveRuleProposal> = emptyList(),
)

@Serializable
data class MemoryPreferences(val enabled: Boolean = true)

@Serializable
data class SearchPreferences(
    val result_limit: Int = 8,
    val image_limit: Int = 4,
    val parallel_image_search: Boolean = true,
)

@Serializable
data class QuietHours(
    val enabled: Boolean = false,
    val start: String = "22:00",
    val end: String = "07:00",
)

@Serializable
data class ProactivePreferences(
    val enabled: Boolean = true,
    val autonomy_mode: String = "propose",
    val timezone: String = "Asia/Shanghai",
    val quiet_hours: QuietHours = QuietHours(),
    val daily_limit: Int = 6,
    val lookahead_hours: Int = 24,
    val window_limit: Int = 10,
    val provider_schedule_limit: Int = 6,
    val route_gap_hours: Int = 3,
    val travel_buffer_minutes: Int = 20,
    val fallback_mottos: List<String> = emptyList(),
    val types: Map<String, Boolean> = emptyMap(),
)

@Serializable
data class ProactiveWorkflowStep(
    val id: String = "",
    val offset_minutes: Int = 0,
    val title: String = "",
    val body: String = "",
    val action_prompt: String = "",
    val depends_on: List<String> = emptyList(),
    val status: String = "pending",
    val attempt: Int = 0,
    val last_error: String? = null,
    val due_at: Long? = null,
)

@Serializable
data class ProactiveWorkflow(
    val id: String = "",
    val title: String = "",
    val reason: String = "",
    val status: String = "awaiting_confirmation",
    val version: Int = 0,
    val steps: List<ProactiveWorkflowStep> = emptyList(),
    val created_at: Long = 0,
    val updated_at: Long = 0,
)

@Serializable
data class ProactiveState(
    val schema_version: Int = 1,
    val revision: Int = 0,
    val preferences: ProactivePreferences = ProactivePreferences(),
    val notifications: List<ProactiveNotification> = emptyList(),
    val workflows: List<ProactiveWorkflow> = emptyList(),
)

/**
 * 主动提醒（POST /proactive）。后端负责生成与状态流转，
 * 客户端只展示并把用户决定原样转发（mark_read / snooze / dismiss）。
 */
@Serializable
data class ProactiveNotification(
    val id: String = "",
    val title: String = "",
    val body: String? = null,
    val type: String? = null,
    val priority: String? = null,
    val status: String = "unread",
    @SerialName("snoozed_until") val snoozedUntil: Long? = null,
    /** 后端建议的处理话术，点"去处理"时填入输入框。 */
    @SerialName("action_prompt") val actionPrompt: String? = null,
)
