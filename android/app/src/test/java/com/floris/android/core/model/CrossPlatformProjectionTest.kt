package com.floris.android.core.model

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CrossPlatformProjectionTest {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    @Test
    fun `intelligence projection includes memory rule and external skill connection`() {
        val state = json.decodeFromString(
            IntelligenceState.serializer(),
            """
            {
              "revision": 9,
              "memory_preferences":{"enabled":true},
              "memory_proposals":[{"id":"p1","memory_key":"travel","value":"省钱","version":2}],
              "memories":[{"id":"m1","memory_key":"food","value":["清淡"],"version":3,
                "history":[{"version":2,"value":"不限"}]}],
              "rule_proposals":[{"id":"r1","kind":"disable_notification_type",
                "target":"weather","reason":"用户经常忽略","version":1}],
              "future_projection":{"safe":true}
            }
            """.trimIndent(),
        )

        assertEquals(9, state.revision)
        assertEquals("p1", state.memory_proposals.single().id)
        assertEquals(2, state.memories.single().history.single().version)
        assertEquals("r1", state.rule_proposals.single().id)
    }

    @Test
    fun `proactive projection includes workflow steps`() {
        val state = json.decodeFromString(
            ProactiveState.serializer(),
            """
            {"revision":4,"preferences":{"enabled":true,"autonomy_mode":"propose",
              "quiet_hours":{"enabled":true,"start":"22:00","end":"07:00"}},
             "workflows":[{"id":"w1","title":"杭州出发准备","status":"active","version":2,
              "steps":[{"id":"s1","title":"订票","status":"notified","action_prompt":"帮我查票"}]}]}
            """.trimIndent(),
        )

        assertTrue(state.preferences.quiet_hours.enabled)
        assertEquals("s1", state.workflows.single().steps.single().id)
    }

    @Test
    fun `route projection preserves multimodal sections between recommended stops`() {
        val route = json.decodeFromString(
            RoutePlan.serializer(),
            """
            {"mode":"transit","legs":[{"from":{"name":"灵隐寺"},"to":{"name":"西湖"},
              "sections":[{"mode":"walking","distance_meters":320},
                {"mode":"bus","line":"7路","geton":"灵隐","getoff":"岳庙"},
                {"mode":"bicycling","distance_meters":900}]}]}
            """.trimIndent(),
        )

        assertEquals(listOf("walking", "bus", "bicycling"), route.legs.single().sections.map { it.mode })
    }

    @Test
    fun `skill marketplace consumes the Maker component API instead of a client copy`() {
        val state = json.decodeFromString(
            SkillMarketplaceState.serializer(),
            """
            {"skills":[],"component_api":{"version":"2026-08-04","actions":[{
              "id":"calendar.change.propose","category":"calendar",
              "name":{"zh-CN":"提交日程变更","en":"Propose calendar changes"},
              "description":"Create a calendar proposal",
              "description_i18n":{"zh-CN":"提交日程变更提案"},
              "permission":"components.calendar",
              "input":{"changes":"calendar-change[]","warnings":"string[]"},
              "required":["changes"]
            }]},"future_marketplace_field":true}
            """.trimIndent(),
        )

        val action = state.component_api!!.actions.single()
        assertEquals("2026-08-04", state.component_api.version)
        assertEquals("calendar.change.propose", action.id)
        assertEquals(listOf("changes"), action.required)
        assertEquals("calendar-change[]", action.input["changes"])
    }
}
