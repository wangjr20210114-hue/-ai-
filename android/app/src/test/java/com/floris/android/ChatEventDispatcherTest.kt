package com.floris.android

import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.core.network.sse.ChatEventDispatcher
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatEventDispatcherTest {

    private val dispatcher = ChatEventDispatcher(Json { ignoreUnknownKeys = true })

    @Test
    fun `stage timing is retained as typed Maker telemetry`() {
        val event = dispatcher.dispatch(
            """{"type":"stage_timing","timings_ms":{"planning":12,"search":1450.5}}""",
        )

        assertTrue(event is ChatEvent.StageTiming)
        event as ChatEvent.StageTiming
        assertEquals(12.0, event.timingsMs["planning"])
        assertEquals(1450.5, event.timingsMs["search"])
    }

    @Test
    fun `ai_response maps to AiResponse`() {
        val event = dispatcher.dispatch("""{"type":"ai_response","content":"你好"}""")
        assertEquals(ChatEvent.AiResponse("你好"), event)
    }

    @Test
    fun `progress_event parses payload component`() {
        val frame = """
            {"type":"progress_event","payload":{"schema_version":1,"stage":"retrieval",
            "status":"active","activity":"web_search","source":"controller"}}
        """.trimIndent()
        val event = dispatcher.dispatch(frame)
        assertTrue(event is ChatEvent.Progress)
        assertEquals("retrieval", (event as ChatEvent.Progress).payload.stage)
        assertEquals("web_search", event.payload.activity)
    }

    @Test
    fun `map_action parses workspace action from payload action`() {
        val frame = """
            {"type":"map_action","payload":{"action":{"schema_version":1,"id":"a1",
            "kind":"map_recommendation","status":"awaiting_confirmation","version":2,
            "payload":{"title":"北海公园","places":[{"place_id":"p1","name":"北海公园",
            "address":"北京市西城区","latitude":39.9,"longitude":116.4}]}}}}
        """.trimIndent()
        val event = dispatcher.dispatch(frame)
        assertTrue(event is ChatEvent.WorkspaceActionEvent)
        val action = (event as ChatEvent.WorkspaceActionEvent).action
        assertEquals("a1", action.id)
        assertEquals("awaiting_confirmation", action.status)
        assertEquals(1, action.payload.places.size)
        assertEquals(39.9, action.payload.places[0].latitude, 0.0001)
    }

    @Test
    fun `clarification_action parses form fields`() {
        val frame = """
            {"type":"clarification_action","payload":{"clarification":{"id":"c1",
            "title":"补充信息","prompt":"想去哪儿？","fields":[{"id":"f1","label":"城市",
            "type":"single","options":["北京","上海"],"required":true}]}}}
        """.trimIndent()
        val event = dispatcher.dispatch(frame)
        assertTrue(event is ChatEvent.ClarificationEvent)
        val clarification = (event as ChatEvent.ClarificationEvent).clarification
        assertEquals("c1", clarification.id)
        assertEquals("single", clarification.fields[0].type)
        assertEquals(listOf("北京", "上海"), clarification.fields[0].options)
    }

    @Test
    fun `follow_ups parses items`() {
        val event = dispatcher.dispatch("""{"type":"follow_ups","payload":{"items":["a","b"]}}""")
        assertEquals(ChatEvent.FollowUps(listOf("a", "b")), event)
    }

    @Test
    fun `usage parses token counts`() {
        val event = dispatcher.dispatch(
            """{"type":"usage","input_tokens":10,"output_tokens":20,"total_tokens":30}""",
        )
        assertEquals(ChatEvent.Usage(10, 20, 30), event)
    }

    @Test
    fun `error_message maps to Error`() {
        val event = dispatcher.dispatch("""{"type":"error_message","code":"quota","content":"超出额度"}""")
        assertEquals(ChatEvent.Error("quota", "超出额度"), event)
    }

    // ---- Forward compatibility (contract: unknown events must be ignored) ----

    @Test
    fun `unknown event type is ignored`() {
        val event = dispatcher.dispatch("""{"type":"brand_new_event_v2","payload":{"x":1}}""")
        assertEquals(ChatEvent.Ignored, event)
    }

    @Test
    fun `event without type is ignored`() {
        assertEquals(ChatEvent.Ignored, dispatcher.dispatch("""{"payload":{}}"""))
    }

    @Test
    fun `known event with extra fields still parses`() {
        val event = dispatcher.dispatch(
            """{"type":"ai_response","content":"ok","future_field":{"nested":[1,2]}}""",
        )
        assertEquals(ChatEvent.AiResponse("ok"), event)
    }

    @Test
    fun `known event with malformed payload degrades to ignored instead of crashing`() {
        val event = dispatcher.dispatch("""{"type":"progress_event","payload":"not-an-object"}""")
        assertEquals(ChatEvent.Ignored, event)
    }

    @Test
    fun `non json frame becomes Malformed`() {
        val event = dispatcher.dispatch("this is not json")
        assertTrue(event is ChatEvent.Malformed)
    }

    @Test
    fun `unknown workspace action kind is preserved for text fallback`() {
        val frame = """
            {"type":"side_effect_action","payload":{"action":{"schema_version":1,"id":"x",
            "kind":"future_kind","status":"ready","version":0,"payload":{"title":"t"}}}}
        """.trimIndent()
        val event = dispatcher.dispatch(frame)
        assertTrue(event is ChatEvent.WorkspaceActionEvent)
        assertTrue(!(event as ChatEvent.WorkspaceActionEvent).action.isKnownKind)
    }
}
