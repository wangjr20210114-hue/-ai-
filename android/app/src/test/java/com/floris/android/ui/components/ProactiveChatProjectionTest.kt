package com.floris.android.ui.components

import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.ProactiveWorkflow
import com.floris.android.core.model.ProactiveWorkflowStep
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProactiveChatProjectionTest {

    private fun notification(id: String, status: String = "unread") =
        ProactiveNotification(id = id, title = "t-$id", status = status)

    private fun step(id: String, status: String) =
        ProactiveWorkflowStep(id = id, title = "s-$id", status = status)

    @Test
    fun `notifications drop dismissed and cap at three`() {
        val state = ProactiveState(
            notifications = listOf(
                notification("1"),
                notification("2", "snoozed"),
                notification("3"),
                notification("4", "dismissed"),
                notification("5"),
            ),
        )
        val visible = chatProactiveNotifications(state)
        assertEquals(listOf("1", "2", "3"), visible.map { it.id })
    }

    @Test
    fun `empty state hides card`() {
        assertFalse(chatProactiveHasItems(null))
        assertFalse(chatProactiveHasItems(ProactiveState()))
    }

    @Test
    fun `workflows are projected by status`() {
        val state = ProactiveState(
            workflows = listOf(
                ProactiveWorkflow(id = "a", status = "awaiting_confirmation", version = 2),
                ProactiveWorkflow(id = "b", status = "active"),
                ProactiveWorkflow(id = "c", status = "cancelled"),
            ),
        )
        assertEquals(listOf("a"), chatAwaitingWorkflows(state).map { it.id })
        assertEquals(listOf("b"), chatActiveWorkflows(state).map { it.id })
        assertTrue(chatProactiveHasItems(state))
    }

    @Test
    fun `active step skips terminal states`() {
        val workflow = ProactiveWorkflow(
            id = "w",
            status = "active",
            steps = listOf(
                step("1", "completed"),
                step("2", "skipped"),
                step("3", "notified"),
                step("4", "pending"),
            ),
        )
        assertEquals("3", chatActiveWorkflowStep(workflow)?.id)
    }

    @Test
    fun `finished workflow has no active step`() {
        val workflow = ProactiveWorkflow(
            id = "w",
            status = "active",
            steps = listOf(step("1", "completed"), step("2", "compensated")),
        )
        assertNull(chatActiveWorkflowStep(workflow))
    }
}
