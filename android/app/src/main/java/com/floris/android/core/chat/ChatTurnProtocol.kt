package com.floris.android.core.chat

import com.floris.android.core.model.Clarification
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

/** Single client boundary for the dev POST /chat contract. */
fun PendingChatTurn.toChatRequestBody() = buildJsonObject {
    put("message", text)
    put("client_message_id", id)
    activity?.let { put("activity", it) }
    routePlanId?.let { put("route_plan_id", it) }
    if (referenceImages.isNotEmpty()) {
        put("reference_images", JsonArray(referenceImages.take(3).map(::JsonPrimitive)))
    }
    currentLocation?.takeIf { it.isFresh() }?.let { location ->
        put("current_location", buildJsonObject {
            put("latitude", location.latitude)
            put("longitude", location.longitude)
            put("accuracy_meters", location.accuracyMeters)
            put("captured_at", location.capturedAt)
            put("coordinate_type", location.coordinateType)
        })
    }
    put("location_request", buildJsonObject {
        put("state", locationRequest.normalizedState)
        put("attempted_at", locationRequest.attemptedAt)
    })
    if (locationRetry) put("_location_retry", true)
}

data class StructuredClarificationAnswer(
    val id: String,
    val label: String,
    val value: List<String>,
)

fun clarificationAnswers(
    clarification: Clarification,
    values: Map<String, Any>,
): List<StructuredClarificationAnswer> = clarification.fields.mapNotNull { field ->
    val raw = values[field.id] ?: return@mapNotNull null
    val clean = when (raw) {
        is List<*> -> raw.mapNotNull { it?.toString()?.trim()?.takeIf(String::isNotEmpty) }
        else -> listOf(raw.toString().trim()).filter(String::isNotEmpty)
    }
    clean.takeIf(List<String>::isNotEmpty)?.let {
        StructuredClarificationAnswer(field.id, field.label, it)
    }
}

fun clarificationAnswerSummary(
    clarification: Clarification,
    values: Map<String, Any>,
): String = clarificationAnswers(clarification, values).joinToString("；") { answer ->
    val field = clarification.fields.firstOrNull { it.id == answer.id }
    val display = answer.value.map { value ->
        field?.options?.firstOrNull { option ->
            (field.option_values[option] ?: option) == value
        } ?: value
    }
    "${answer.label}: ${display.joinToString("、")}"
}

fun clarificationRequestBody(
    turn: PendingChatTurn,
    clarification: Clarification,
    sourceMessageId: String,
    values: Map<String, Any>,
) = buildJsonObject {
    val answers = clarificationAnswers(clarification, values)
    put("message", turn.text)
    put("text", turn.text)
    put("client_message_id", turn.id)
    put("message_id", turn.id)
    put("activity", "clarification_answered")
    put("interaction_mode", "clarification")
    put("clarification_response", buildJsonObject {
        put("id", clarification.id)
        put("source_message_id", sourceMessageId)
        putJsonArray("answers") {
            answers.forEach { answer ->
                add(buildJsonObject {
                    put("id", answer.id)
                    put("label", answer.label)
                    if (answer.value.size == 1) {
                        put("value", answer.value.single())
                    } else {
                        put("value", JsonArray(answer.value.map(::JsonPrimitive)))
                    }
                })
            }
        }
    })
}
