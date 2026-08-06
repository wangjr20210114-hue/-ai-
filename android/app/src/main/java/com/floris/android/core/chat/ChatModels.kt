package com.floris.android.core.chat

import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ExperienceHintItem
import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.Paper
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import com.floris.android.core.model.ChatRun
import com.floris.android.core.network.sse.ChatEvent

/** UI-level chat message, reduced from the SSE event stream. */
data class ChatMessageUi(
    val id: String,
    val role: Role,
    /** Stable owner shared by the user request and its assistant answer. */
    val clientMessageId: String? = null,
    val content: String = "",
    val searchResults: SearchMeta? = null,
    val papers: List<Paper> = emptyList(),
    val actions: List<WorkspaceAction> = emptyList(),
    val clarification: Clarification? = null,
    /**
     * 澄清卡已提交后留下的答案摘要。卡片本身会被摘掉（防止答案生效后
     * 用户还能改选），这里只保留一条只读记录说明当时选了什么。
     */
    val clarificationAnswered: String? = null,
    val followUps: List<String> = emptyList(),
    val progress: ProgressComponent? = null,
    /** 全部已收到的阶段（同一 stage:activity 去重更新），用于绘制时间线。 */
    val progressTrail: List<ProgressComponent> = emptyList(),
    /** Maker-reported stage timings; retained without exposing technical stage names. */
    val stageTimingsMs: Map<String, Double> = emptyMap(),
    val toolNames: List<String> = emptyList(),
    val hints: List<ExperienceHintItem> = emptyList(),
    val streaming: Boolean = false,
    val failed: Boolean = false,
    val error: String? = null,
    val usageTotal: Long? = null,
    /** Original send boundary; search timing is measured from here. */
    val turnStartedAt: Long? = null,
    val searchStartedAt: Long? = null,
    val searchCompletedAt: Long? = null,
) {
    enum class Role { USER, AI }

    val hasDurablePayload: Boolean
        get() = role == Role.USER || content.isNotBlank() || clarification != null ||
            clarificationAnswered != null || actions.isNotEmpty() || papers.isNotEmpty()

    /** 本轮是否为生图意图（有生图/审图阶段，或已收到生成的图片）。 */
    val isImageIntent: Boolean
        get() = progressTrail.any { it.activity == "image_generation" || it.activity == "image_review" } ||
            searchResults?.media?.any { it.generated } == true

    /** 后端给出的搜索耗时（秒，一位小数）；没有则为 null。 */
    val searchDurationSeconds: String?
        get() {
            val start = turnStartedAt ?: searchStartedAt
            val end = searchCompletedAt
            if (start != null && end != null && end > start) {
                return "%.1f".format((end - start) / 1000.0)
            }
            return (searchResults?.timings_ms?.get("search") ?: stageTimingsMs["search"])
                ?.takeIf { it > 0 }
                ?.let { "%.1f".format(it / 1000.0) }
        }
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
    is ChatEvent.StageTiming -> copy(stageTimingsMs = stageTimingsMs + event.timingsMs)
    is ChatEvent.SearchResults -> copy(searchResults = searchResults.mergeProjection(event.payload))
    is ChatEvent.SearchMedia -> copy(searchResults = searchResults.mergeProjection(event.payload))
    is ChatEvent.PaperResultsEvent -> copy(papers = event.payload.papers)
    is ChatEvent.WorkspaceActionEvent -> {
        val next = event.action
        val replaced = actions.map { if (it.id == next.id) next else it }
        copy(actions = if (actions.any { it.id == next.id }) replaced else actions + next)
    }
    is ChatEvent.ImageAction -> {
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
 * A /stop HTTP 200 is only an acknowledgement, not proof that the tombstone
 * survived the race with first-turn conversation creation.  Confirmation is
 * durable only when Maker's public /run projection can also observe it, or a
 * newer run proves the acknowledged old-turn tombstone was written alongside
 * an existing conversation.
 */
internal fun stopIsDurablyConfirmed(
    requestedClientMessageId: String,
    acknowledgementClientMessageId: String?,
    acknowledgementStatus: String?,
    run: ChatRun?,
): Boolean {
    val requested = requestedClientMessageId.trim()
    if (requested.isEmpty() || run == null) return false
    val runClientId = run.client_message_id.trim()
    if (runClientId == requested) return run.status == "cancelled"

    val acknowledged = acknowledgementClientMessageId == requested &&
        acknowledgementStatus in setOf("aborted", "discarded")
    if (!acknowledged) return false

    // A blank-id cancelled marker is the valid pre-admission tombstone shape.
    if (runClientId.isEmpty()) return run.status == "cancelled"
    // A different visible run means Maker already advanced the queue; the
    // explicit old-id acknowledgement can only have appended its tombstone.
    return true
}

/**
 * Search result and reviewed-media frames are independent stream projections,
 * so neither arrival order may erase fields already received from the other.
 */
fun SearchMeta?.mergeProjection(incoming: SearchMeta): SearchMeta {
    val previous = this ?: return incoming
    val resultsById = linkedMapOf<String, com.floris.android.core.model.SearchSource>()
    (previous.results + incoming.results).forEach { source ->
        val key = source.id.ifBlank { source.url }
        resultsById[key] = source
    }
    val mediaById = linkedMapOf<String, MediaItem>()
    (previous.media + incoming.media).forEach { item ->
        val key = item.id.ifBlank { item.url }
        mediaById[key] = item
    }
    val results = resultsById.values.toList()
    val media = mediaById.values.toList()
    return SearchMeta(
        query = incoming.query.ifBlank { previous.query },
        results = results,
        images = (previous.images + incoming.images).distinct(),
        media = media,
        sources_used = (previous.sources_used + incoming.sources_used).distinct(),
        total = maxOf(previous.total, incoming.total, results.size),
        target_date = incoming.target_date ?: previous.target_date,
        strict_date = incoming.strict_date ?: previous.strict_date,
        media_pending = when {
            media.isNotEmpty() -> false
            incoming.media_pending != null -> incoming.media_pending
            else -> previous.media_pending
        },
        timings_ms = previous.timings_ms + incoming.timings_ms,
    )
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
