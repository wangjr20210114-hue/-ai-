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
    /** 全部已收到的阶段（同一 stage:activity 去重更新），用于绘制时间线。 */
    val progressTrail: List<ProgressComponent> = emptyList(),
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

    /** 本轮是否为生图意图（有生图/审图阶段，或已收到生成的图片）。 */
    val isImageIntent: Boolean
        get() = progressTrail.any { it.activity == "image_generation" || it.activity == "image_review" } ||
            searchResults?.media?.any { it.generated } == true

    /** 后端给出的搜索耗时（秒，一位小数）；没有则为 null。 */
    val searchDurationSeconds: String?
        get() = searchResults?.timings_ms?.get("search")?.takeIf { it > 0 }
            ?.let { "%.1f".format(it / 1000.0) }
}

/** Applies one SSE event to the in-flight assistant message. Pure function. */
fun ChatMessageUi.reduce(event: ChatEvent): ChatMessageUi = when (event) {
    is ChatEvent.AiResponse -> copy(content = content + event.content)
    ChatEvent.AiResponseReset -> copy(content = "")
    is ChatEvent.ToolActivity ->
        if (event.isCall) copy(toolNames = (toolNames + event.name).distinct()) else this
    is ChatEvent.Progress -> copy(
        progress = event.payload,
        progressTrail = progressTrail.mergeProgress(event.payload),
    )
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
    is ChatEvent.AnswerComplete -> copy(
        streaming = false,
        progress = progress?.copy(status = "completed"),
        progressTrail = progressTrail.map {
            if (it.status == "active") it.copy(status = "completed") else it
        },
    )
    is ChatEvent.FollowUps -> copy(followUps = event.items)
    is ChatEvent.Usage -> copy(usageTotal = event.totalTokens)
    is ChatEvent.Error -> copy(streaming = false, failed = true, error = event.content)
    // ping / location request / proactive / ignored / malformed: no UI impact here.
    else -> this
}

/**
 * 合并一个进度阶段，规则与网页端 mergeProgressStep 完全一致：
 *  - 以 `stage:activity` 为键做原地更新，否则追加；
 *  - `complete/completed` 到达时把仍处于 active 的阶段一并收尾；
 *  - 最多保留最近 8 条。
 */
internal fun List<ProgressComponent>.mergeProgress(
    incoming: ProgressComponent,
): List<ProgressComponent> {
    val key = "${incoming.stage}:${incoming.activity}"
    val index = indexOfFirst { "${it.stage}:${it.activity}" == key }
    val merged = if (index >= 0) {
        toMutableList().also { it[index] = incoming }
    } else {
        this + incoming
    }
    if (incoming.stage == "complete" && incoming.status == "completed") {
        return merged.map { if (it.status == "active") it.copy(status = "completed") else it }
            .takeLast(8)
    }
    return merged.takeLast(8)
}
