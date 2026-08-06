package com.floris.android.ui.navigation

import com.floris.android.core.model.ConversationSummary
import org.junit.Assert.assertEquals
import org.junit.Test

class SidebarSearchTest {

    private fun conversation(id: String, title: String) =
        ConversationSummary(id = id, title = title)

    @Test
    fun `empty query keeps the full list`() {
        val items = listOf(conversation("1", "周末去哪玩"), conversation("2", "论文助读"))
        assertEquals(items, filterConversations(items, ""))
        assertEquals(items, filterConversations(items, "   "))
    }

    @Test
    fun `query filters by title ignoring case`() {
        val items = listOf(
            conversation("1", "AI 最新进展"),
            conversation("2", "周末行程"),
            conversation("3", "ai 绘画"),
        )
        assertEquals(listOf("1", "3"), filterConversations(items, "ai").map { it.id })
    }

    @Test
    fun `no match returns empty`() {
        val items = listOf(conversation("1", "周末行程"))
        assertEquals(emptyList<ConversationSummary>(), filterConversations(items, "会议"))
    }
}
