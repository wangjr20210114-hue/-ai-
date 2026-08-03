package com.floris.android.core.chat

import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ExperienceHintItem
import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.Paper
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import com.floris.android.core.network.sse.ChatEvent

/** UI-level chat message, reduced from the SSE event stream. */
data class ChatMessageUi(
    val id: String,
    val role: Role,
    val content: String = "",
    val searchResults: SearchMeta? = null,
    val papers: List<Paper> = emptyList(),
    val actions: List<WorkspaceAction> = emptyList(),
    val clarification: Clarification? = null,
    val followUps: List<String> = emptyList(),
    val progress: ProgressComponent? = null,
    val toolNames: List<String> = emptyList(),
    val hints: List<ExperienceHintItem> = emptyList(),
    val streaming: Boolean = false,
    val failed: Boolean = false,
    val error: String? = null,
    val usageTotal: Long? = null,
) {
    enum class Role { USER, AI }

    val hasDurablePayload: Boolean
        get() = role == Role.USER || content.isNotBlank() || clarification != null ||
            actions.isNotEmpty() || papers.isNotEmpty()
}

/** Applies one SSE event to the in-flight assistant message. Pure function. */
fun ChatMessageUi.reduce(event: ChatEvent): ChatMessageUi = when (event) {
    is ChatEvent.AiResponse -> copy(content = content + event.content)
    ChatEvent.AiResponseReset -> copy(content = "")
    is ChatEvent.ToolActivity ->
        if (event.isCall) copy(toolNames = (toolNames + event.name).distinct()) else this
    is ChatEvent.Progress -> copy(progress = event.payload)
    is ChatEvent.SearchResults -> copy(searchResults = event.payload)
    is ChatEvent.SearchMedia -> {
        val base = searchResults
        copy(
            searchResults = (base ?: SearchMeta(query = event.payload.query)).copy(
                media = (base?.media.orEmpty() + event.payload.media).distinctBy { it.id },
                images = (base?.images.orEmpty() + event.payload.images).distinct(),
                media_pending = false,
            ),
        )
    }
    is ChatEvent.PaperResultsEvent -> copy(papers = event.payload.papers)
    is ChatEvent.WorkspaceActionEvent -> {
        val next = event.action
        val replaced = actions.map { if (it.id == next.id) next else it }
        copy(actions = if (actions.any { it.id == next.id }) replaced else actions + next)
    }
    is ChatEvent.ClarificationEvent -> copy(clarification = event.clarification)
    is ChatEvent.ExperienceHint -> copy(hints = event.items)
    is ChatEvent.AnswerComplete -> copy(streaming = false, progress = progress?.copy(status = "completed"))
    is ChatEvent.FollowUps -> copy(followUps = event.items)
    is ChatEvent.Usage -> copy(usageTotal = event.totalTokens)
    is ChatEvent.Error -> copy(streaming = false, failed = true, error = event.content)
    // ping / location request / proactive / ignored / malformed: no UI impact here.
    else -> this
}
