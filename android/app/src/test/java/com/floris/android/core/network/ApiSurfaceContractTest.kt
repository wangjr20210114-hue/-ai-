package com.floris.android.core.network

import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HEAD
import retrofit2.http.POST

class ApiSurfaceContractTest {
    @Test
    fun `native client exposes the complete v1 backend surface`() {
        val expected = mapOf(
            "exchangeMobileSession" to "POST auth/mobile/session",
            "logout" to "POST auth/logout",
            "guestSession" to "GET auth/session",
            "bootstrap" to "POST messages",
            "chatRun" to "POST run",
            "listConversations" to "GET conversations",
            "touchConversation" to "POST conversations",
            "deleteConversation" to "DELETE conversations",
            "stop" to "POST stop",
            "appendMessage" to "POST conversation",
            "createFileUpload" to "POST files",
            "downloadFile" to "GET files",
            "inspectFile" to "HEAD files",
            "deleteFile" to "DELETE files",
            "workspaceOperation" to "POST workspace",
            "intelligenceOperation" to "POST intelligence",
            "skillMarketplace" to "POST skill_marketplace",
            "listSkillUploads" to "GET skill-uploads",
            "mutateSkillUpload" to "POST skill-uploads",
            "searchPlaces" to "POST places",
            "planRoute" to "POST routes",
            "searchPapers" to "GET papers",
            "savePaper" to "POST papers",
            "readPaper" to "POST reader",
            "loadLibrary" to "GET library",
            "libraryOperation" to "POST library",
            "deleteLibrary" to "DELETE library",
            "extractDocumentText" to "POST document-text",
            "getProfile" to "GET profile",
            "profileOperation" to "POST profile",
            "proactiveOperation" to "POST proactive",
            "providerUsage" to "GET provider_usage",
            "resetState" to "POST reset",
            "resetFiles" to "POST reset-files",
        )

        val actual = FlorisApi::class.java.methods.mapNotNull { method ->
            val route = method.getAnnotation(POST::class.java)?.let { "POST ${it.value}" }
                ?: method.getAnnotation(GET::class.java)?.let { "GET ${it.value}" }
                ?: method.getAnnotation(HEAD::class.java)?.let { "HEAD ${it.value}" }
                ?: method.getAnnotation(DELETE::class.java)?.let { "DELETE ${it.value}" }
                ?: return@mapNotNull null
            method.name to route
        }.toMap()

        expected.forEach { (method, route) -> assertEquals(route, actual[method]) }
    }

    @Test
    fun `idempotent reconciliation backoff grows and caps`() {
        val backoff = ExponentialBackoff(
            initialDelayMillis = 850,
            maximumDelayMillis = 30_000,
        )

        assertEquals(
            listOf(850L, 1_700L, 3_400L, 6_800L, 13_600L, 27_200L, 30_000L, 30_000L),
            List(8) { backoff.nextDelayMillis() },
        )
        backoff.reset()
        assertEquals(850L, backoff.nextDelayMillis())
    }
}
