package com.floris.android.core.network

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ResponseLanguageTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun `injects selected language into any JSON command`() {
        val localized = injectResponseLanguage(json, """{"operation":"get"}""", "en")
        val body = json.parseToJsonElement(requireNotNull(localized)) as JsonObject
        assertEquals("get", body["operation"]?.jsonPrimitive?.content)
        assertEquals("en", body["response_language"]?.jsonPrimitive?.content)
    }

    @Test
    fun `preserves an explicitly supplied model language`() {
        assertNull(
            injectResponseLanguage(
                json,
                """{"message":"hello","response_language":"cat-cute"}""",
                "en",
            ),
        )
    }

    @Test
    fun `unknown product language safely normalizes to simplified Chinese`() {
        val localized = injectResponseLanguage(json, "{}", "xx")
        val body = json.parseToJsonElement(requireNotNull(localized)) as JsonObject
        assertEquals("zh-CN", body["response_language"]?.jsonPrimitive?.content)
    }
}
