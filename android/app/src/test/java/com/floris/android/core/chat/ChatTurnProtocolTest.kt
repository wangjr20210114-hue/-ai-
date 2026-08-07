package com.floris.android.core.chat

import com.floris.android.core.location.ClientLocationFix
import com.floris.android.core.location.ClientLocationRequest
import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ClarificationField
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatTurnProtocolTest {
    @Test
    fun `location retry matches the dev browser protocol`() {
        val now = System.currentTimeMillis()
        val body = PendingChatTurn(
            id = "turn-location-1",
            text = "带我去车站",
            currentLocation = ClientLocationFix(
                latitude = 31.2304,
                longitude = 121.4737,
                accuracyMeters = 23.5,
                capturedAt = now,
            ),
            locationRequest = ClientLocationRequest(ClientLocationRequest.AVAILABLE, now),
            locationRetry = true,
        ).toChatRequestBody()

        val location = body["current_location"]!!.jsonObject
        assertEquals("wgs84", location["coordinate_type"]!!.jsonPrimitive.content)
        assertEquals("23.5", location["accuracy_meters"]!!.jsonPrimitive.content)
        assertEquals(now.toString(), location["captured_at"]!!.jsonPrimitive.content)
        assertEquals("available", body["location_request"]!!.jsonObject["state"]!!.jsonPrimitive.content)
        assertTrue(body["_location_retry"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `stale location is never sent to Maker`() {
        val body = PendingChatTurn(
            id = "turn-location-stale",
            text = "附近有什么",
            currentLocation = ClientLocationFix(
                latitude = 31.2,
                longitude = 121.4,
                accuracyMeters = 10.0,
                capturedAt = System.currentTimeMillis() - ClientLocationFix.MAX_AGE_MS - 1,
            ),
        ).toChatRequestBody()

        assertFalse("current_location" in body)
    }

    @Test
    fun `clarification submission carries structured answers and source id`() {
        val clarification = Clarification(
            id = "place-choice",
            fields = listOf(
                ClarificationField(
                    id = "place",
                    label = "去哪家店",
                    type = "single",
                    options = listOf("国贸店", "其他地点"),
                    option_values = mapOf("国贸店" to "poi-001"),
                    allow_custom_input = true,
                ),
            ),
        )
        val turn = PendingChatTurn(id = "answer-1", text = "已选择：去哪家店: 国贸店")
        val body = clarificationRequestBody(
            turn,
            clarification,
            sourceMessageId = "assistant-card-1",
            values = mapOf("place" to "poi-001"),
        )

        assertEquals("clarification", body["interaction_mode"]!!.jsonPrimitive.content)
        assertEquals("clarification_answered", body["activity"]!!.jsonPrimitive.content)
        val response = body["clarification_response"]!!.jsonObject
        assertEquals("assistant-card-1", response["source_message_id"]!!.jsonPrimitive.content)
        val answer = (response["answers"] as JsonArray).single() as JsonObject
        assertEquals("place", answer["id"]!!.jsonPrimitive.content)
        assertEquals("poi-001", answer["value"]!!.jsonPrimitive.content)
        assertEquals("去哪家店: 国贸店", clarificationAnswerSummary(clarification, mapOf("place" to "poi-001")))
    }
}
