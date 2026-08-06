package com.floris.android.ui.chat

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.core.chat.ChatRuntimeStore
import com.floris.android.core.chat.PendingChatTurn
import com.floris.android.core.chat.mergeProjection
import com.floris.android.core.chat.StreamTypewriter
import com.floris.android.core.chat.reduce
import com.floris.android.core.chat.stopIsDurablyConfirmed
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.arr
import com.floris.android.core.data.asString
import com.floris.android.core.data.obj
import com.floris.android.core.data.num
import com.floris.android.core.data.str
import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ChatRun
import com.floris.android.core.model.Paper
import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.ProactiveWorkflow
import com.floris.android.core.model.ProactiveWorkflowStep
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.RunPresentation
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import com.floris.android.core.network.ExponentialBackoff
import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.userFacingError
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.yield
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.time.LocalDate
import java.util.Locale
import java.util.UUID

data class ChatUiState(
    val conversationId: String = "",
    /** 顶栏显示的对话名（来自 Maker 会话索引，新对话用占位名）。 */
    val conversationTitle: String = "",
    val messages: List<ChatMessageUi> = emptyList(),
    val streaming: Boolean = false,
    val bootstrapping: Boolean = true,
    val busyActionId: String? = null,
    /** 会话内 proactive 卡片的忙碌键（通知/工作流操作）。 */
    val busyProactiveKey: String? = null,
    val submittingClarification: Boolean = false,
    val uploadingDocument: Boolean = false,
    val locationRequestReason: String? = null,
    val transientError: String? = null,
    val queuedTurns: List<PendingChatTurn> = emptyList(),
    val recovering: Boolean = false,
    /** Maker 主动提醒投影：通知 + 工作流（服务端状态机决定内容）。 */
    val proactive: ProactiveState? = null,
)

enum class ChatSendDisposition { STARTED, QUEUED, QUEUE_FULL, IGNORED }

class ChatViewModel(
    private val repository: FlorisRepository,
    private val runtimeStore: ChatRuntimeStore,
    private val json: Json,
    private val strings: StringResolver,
) : ViewModel() {

    private val _state = MutableStateFlow(ChatUiState())
    val state = _state.asStateFlow()

    private var streamJob: Job? = null
    private var lastUserMessage: String? = null
    private var lastClientMessageId: String? = null
    private var activeTurn: PendingChatTurn? = null
    private val stopConfirmationJobs = mutableMapOf<String, Job>()
    private var lastPresentationRevision = -1L
    private var restored = false
    private var activeConversationPending = true

    init {
        viewModelScope.launch {
            val id = repository.activeConversationId()
            _state.update {
                it.copy(conversationId = id, queuedTurns = runtimeStore.loadQueue(id))
            }
            refreshConversationTitle(id)
            restore(id)
        }
        viewModelScope.launch {
            repository.proactiveStateFlow.collect { projection ->
                _state.update { it.copy(proactive = projection) }
            }
        }
    }

    // ---------- Restore ----------

    fun openConversation(id: String) {
        if (id == _state.value.conversationId && restored) return
        streamJob?.cancel()
        viewModelScope.launch {
            repository.setActiveConversationId(id)
            _state.value = ChatUiState(
                conversationId = id,
                queuedTurns = runtimeStore.loadQueue(id),
            )
            refreshConversationTitle(id)
            restore(id)
        }
    }

    fun newConversation() {
        if (activeConversationPending && _state.value.messages.isEmpty() &&
            _state.value.queuedTurns.isEmpty() && !_state.value.streaming
        ) return
        // The Maker run is not cancelled here. Reopening the old conversation
        // restores the exact run through POST /run.
        streamJob?.cancel()
        val id = repository.newConversationId()
        viewModelScope.launch { repository.setActiveConversationId(id) }
        _state.value = ChatUiState(
            conversationId = id,
            bootstrapping = false,
            queuedTurns = runtimeStore.loadQueue(id),
            conversationTitle = strings.get(StringKey.ChatNew),
        )
        activeConversationPending = true
        restored = true
    }

    /** 从 Maker 会话索引取标题；新对话尚未命名时保持占位名。 */
    private suspend fun refreshConversationTitle(id: String) {
        if (id.isBlank()) return
        runCatching {
            repository.listConversations()
                .firstOrNull { it.id == id }
                ?.title?.takeIf { it.isNotBlank() }
        }.getOrNull()?.let { title ->
            _state.update { it.copy(conversationTitle = title) }
        }
    }

    private suspend fun restore(conversationId: String) {
        _state.update { it.copy(bootstrapping = true) }
        runCatching { repository.bootstrap(conversationId) }
            .onSuccess { data ->
                if (_state.value.conversationId != conversationId) return@onSuccess
                val parsed = data.messages.mapNotNull(::parseRestoredMessage)
                val savedActiveTurn = runtimeStore.loadActiveTurn(conversationId)
                activeTurn = savedActiveTurn
                lastClientMessageId = savedActiveTurn?.id
                    ?: data.run?.client_message_id?.takeIf { it.isNotBlank() }
                lastUserMessage = parsed.lastOrNull { it.role == ChatMessageUi.Role.USER }?.content
                    ?: savedActiveTurn?.text
                activeConversationPending = if (parsed.isEmpty()) {
                    runCatching { repository.listConversations() }
                        .getOrNull()
                        ?.firstOrNull { it.id == conversationId }
                        ?.let { it.pending && !it.manuallyRenamed }
                        ?: true
                } else false
                val run = data.run
                val activeRun = run?.takeIf { it.active }
                val runActive = activeRun != null
                val restoredMessages = if (activeRun != null) {
                    restoreActiveMessage(parsed, activeRun, data.presentation)
                } else if (run?.status == "cancelled") {
                    parsed.filterNot {
                        it.role == ChatMessageUi.Role.AI &&
                            it.clientMessageId == run.client_message_id
                    }
                } else parsed
                _state.update {
                    it.copy(
                        messages = restoredMessages,
                        bootstrapping = false,
                        streaming = runActive,
                        recovering = runActive,
                    )
                }
                data.schedules.takeIf { it.isNotEmpty() }?.let {
                    repository.schedulesFlow.value = repository.parseSchedules(JsonArray(it))
                }
                if (data.map_places.isNotEmpty()) {
                    repository.publishMapWorkspace(
                        buildJsonObject {
                            put("places", JsonArray(data.map_places))
                            put("title", data.map_title)
                            put("route_mode", data.map_route_mode)
                            put("route_strategy", data.map_route_strategy)
                            put("show_route", data.map_show_route)
                            data.map_route?.let { put("route", it) }
                        },
                        data.map_title,
                    )
                }

                val stoppedClientId = runtimeStore.stoppedClientMessageId(conversationId)
                when {
                    stoppedClientId.isNotBlank() -> {
                        discardAssistantTurn(stoppedClientId)
                        confirmStop(conversationId, stoppedClientId, run)
                    }
                    activeRun != null -> recoverExistingRun(conversationId, activeRun)
                    run != null && run.status in setOf("completed", "failed", "cancelled") -> {
                        runtimeStore.clearActiveTurn(conversationId, run.client_message_id)
                        activeTurn = null
                        drainQueue()
                    }
                    savedActiveTurn != null -> executeTurn(savedActiveTurn)
                    else -> drainQueue()
                }
            }
            .onFailure {
                if (_state.value.conversationId == conversationId) {
                    _state.update {
                        it.copy(
                            bootstrapping = false,
                            transientError = strings.get(StringKey.ChatRestoreFailed),
                        )
                    }
                }
            }
        restored = true
    }

    private fun parseRestoredMessage(raw: JsonObject): ChatMessageUi? {
        val role = raw.str("role") ?: return null
        val metadata = raw.obj("metadata") ?: raw
        fun content(): String = raw.str("content")?.takeIf { it.isNotEmpty() }
            ?: metadata.str("content") ?: ""

        fun <T> decode(key: String, decode: (JsonElement) -> T): T? {
            val element = metadata[key] ?: raw[key] ?: return null
            return runCatching { decode(element) }.getOrNull()
        }

        val search = decode("searchResults") { json.decodeFromJsonElement(SearchMeta.serializer(), it) }
        val papers = decode("papers") {
            json.decodeFromJsonElement(
                kotlinx.serialization.builtins.ListSerializer(Paper.serializer()), it,
            )
        } ?: emptyList()
        val actions = decode("workspaceActions") {
            json.decodeFromJsonElement(
                kotlinx.serialization.builtins.ListSerializer(WorkspaceAction.serializer()), it,
            )
        } ?: emptyList()
        val followUps = (metadata.arr("followUps") ?: raw.arr("followUps"))
            ?.mapNotNull { it.asString() } ?: emptyList()
        val clarification = decode("clarification") {
            json.decodeFromJsonElement(Clarification.serializer(), it)
        }

        return ChatMessageUi(
            id = raw.str("id") ?: metadata.str("id") ?: UUID.randomUUID().toString(),
            role = if (role == "user") ChatMessageUi.Role.USER else ChatMessageUi.Role.AI,
            clientMessageId = raw.str("client_message_id")
                ?: metadata.str("client_message_id")
                ?: metadata.str("id"),
            content = content(),
            searchResults = search,
            papers = papers,
            actions = actions,
            followUps = followUps,
            clarification = clarification,
            streaming = false,
            turnStartedAt = raw.num("turnStartedAt") ?: metadata.num("turnStartedAt"),
            searchStartedAt = raw.num("searchStartedAt") ?: metadata.num("searchStartedAt"),
            searchCompletedAt = raw.num("searchCompletedAt") ?: metadata.num("searchCompletedAt"),
        ).takeIf { it.hasDurablePayload }
    }

    private fun restoreActiveMessage(
        messages: List<ChatMessageUi>,
        run: ChatRun,
        presentation: RunPresentation?,
    ): List<ChatMessageUi> {
        lastClientMessageId = run.client_message_id
        lastPresentationRevision = presentation?.revision ?: -1
        val existingIndex = messages.indexOfLast {
            it.role == ChatMessageUi.Role.AI && it.clientMessageId == run.client_message_id
        }
        val target = if (existingIndex >= 0) messages[existingIndex] else ChatMessageUi(
            id = "ai-recover-${run.run_id.ifBlank { System.currentTimeMillis().toString() }}",
            role = ChatMessageUi.Role.AI,
            clientMessageId = run.client_message_id,
            streaming = true,
            turnStartedAt = presentation?.turn_started_at ?: run.started_at,
        )
        val restored = presentation?.let { applyPresentation(target, it) }
            ?: target.copy(streaming = true)
        return if (existingIndex >= 0) {
            messages.mapIndexed { index, item -> if (index == existingIndex) restored else item }
        } else messages + restored
    }

    private fun applyPresentation(
        current: ChatMessageUi,
        presentation: RunPresentation,
    ): ChatMessageUi {
        val progress = presentation.progress.mapNotNull { raw ->
            runCatching {
                json.decodeFromJsonElement(ProgressComponent.serializer(), raw)
            }.getOrNull()
        }
        val searchResults = presentation.search_results?.let { raw ->
            runCatching { json.decodeFromJsonElement(SearchMeta.serializer(), raw) }.getOrNull()
        }
        val searchMedia = presentation.search_media?.let { raw ->
            runCatching { json.decodeFromJsonElement(SearchMeta.serializer(), raw) }.getOrNull()
        }
        val mergedSearch = listOfNotNull(searchResults, searchMedia).fold(current.searchResults) {
                accumulated, projection -> accumulated.mergeProjection(projection)
            }
        return current.copy(
            clientMessageId = presentation.client_message_id.ifBlank { current.clientMessageId },
            content = presentation.content,
            progress = progress.lastOrNull() ?: current.progress,
            progressTrail = if (progress.isNotEmpty()) progress else current.progressTrail,
            searchResults = mergedSearch,
            actions = presentation.workspace_actions.ifEmpty { current.actions },
            clarification = presentation.clarification ?: current.clarification,
            papers = presentation.papers?.papers?.ifEmpty { current.papers } ?: current.papers,
            followUps = presentation.follow_ups.ifEmpty { current.followUps },
            hints = presentation.experience_hints.ifEmpty { current.hints },
            streaming = true,
            turnStartedAt = presentation.turn_started_at ?: current.turnStartedAt,
            searchStartedAt = presentation.search_started_at ?: current.searchStartedAt,
            searchCompletedAt = presentation.search_completed_at ?: current.searchCompletedAt,
            error = presentation.error ?: current.error,
        )
    }

    // ---------- Send ----------

    fun send(
        text: String,
        referenceImages: List<String> = emptyList(),
        location: Pair<Double, Double>? = null,
    ): ChatSendDisposition {
        val message = text.trim()
        if (message.isEmpty() || _state.value.bootstrapping) return ChatSendDisposition.IGNORED
        val turn = PendingChatTurn(
            id = UUID.randomUUID().toString(),
            text = message,
            referenceImages = referenceImages.take(3),
            latitude = location?.first,
            longitude = location?.second,
        )
        if (_state.value.streaming || streamJob?.isActive == true) {
            return if (enqueue(turn)) ChatSendDisposition.QUEUED
            else ChatSendDisposition.QUEUE_FULL
        }
        executeTurn(turn)
        return ChatSendDisposition.STARTED
    }

    // ---------- Chat document upload ----------

    /**
     * 聊天内 PDF 上传：走 Maker 预签名上传 → 注册阅读库 → 发送 file_uploaded 信号，
     * 并在会话内追加“已上传文档 / 已打开”提示消息（对齐网页端输入栏）。
     */
    fun uploadDocument(uri: Uri, filename: String) {
        val conversationId = _state.value.conversationId
        if (conversationId.isBlank() || _state.value.uploadingDocument) return
        _state.update { it.copy(uploadingDocument = true) }
        viewModelScope.launch {
            runCatching {
                repository.uploadReadingDocument(conversationId, uri, filename)
            }.onSuccess {
                appendUploadMessages(filename)
            }.onFailure {
                _state.update { s ->
                    s.copy(transientError = strings.get(StringKey.ChatUploadFailed))
                }
            }
            _state.update { it.copy(uploadingDocument = false) }
        }
    }

    private fun appendUploadMessages(filename: String) {
        val now = System.currentTimeMillis()
        val userMessage = ChatMessageUi(
            id = "upload-$now",
            role = ChatMessageUi.Role.USER,
            clientMessageId = "upload-$now",
            content = strings.get(StringKey.ChatUploadedDocument, filename),
            turnStartedAt = now,
        )
        val aiMessage = ChatMessageUi(
            id = "file-${now + 1}",
            role = ChatMessageUi.Role.AI,
            clientMessageId = "upload-$now",
            content = strings.get(StringKey.ChatPaperOpened),
            turnStartedAt = now + 1,
        )
        _state.update { it.copy(messages = it.messages + userMessage + aiMessage) }
    }

    // ---------- Proactive in-chat actions ----------

    /** 网页端同款“帮我处理”：把建议话术填入输入框并标记已读。 */
    fun applyProactiveSuggestion(item: ProactiveNotification) {
        repository.pendingDraftFlow.value = item.actionPrompt
            ?.takeIf { it.isNotBlank() }
            ?: strings.get(StringKey.HelpMeHandle, item.title)
        runProactive("read:${item.id}", "mark_read") {
            put("notification_id", item.id)
        }
    }

    fun snoozeNotification(notificationId: String) = runProactive(
        "snooze:$notificationId",
        "snooze",
    ) {
        put("notification_id", notificationId)
        put("until", System.currentTimeMillis() / 1000 + 3600)
    }

    fun dismissNotification(notificationId: String) = runProactive(
        "dismiss:$notificationId",
        "dismiss",
    ) {
        put("notification_id", notificationId)
    }

    fun confirmWorkflow(workflow: ProactiveWorkflow) = runProactive(
        "workflow:${workflow.id}",
        "confirm_workflow",
    ) {
        put("workflow_id", workflow.id)
        put("version", workflow.version)
    }

    fun rejectWorkflow(workflow: ProactiveWorkflow) = runProactive(
        "reject:${workflow.id}",
        "reject_workflow",
    ) {
        put("workflow_id", workflow.id)
        put("version", workflow.version)
    }

    fun cancelWorkflow(workflow: ProactiveWorkflow) = runProactive(
        "cancel:${workflow.id}",
        "cancel_workflow",
    ) {
        put("workflow_id", workflow.id)
        put("version", workflow.version)
    }

    fun workflowStep(
        workflow: ProactiveWorkflow,
        step: ProactiveWorkflowStep,
        operation: String,
    ) = runProactive("$operation:${step.id}", operation) {
        put("workflow_id", workflow.id)
        put("step_id", step.id)
    }

    private fun runProactive(
        busyKey: String,
        operation: String,
        input: JsonObjectBuilder.() -> Unit = {},
    ) {
        val conversationId = _state.value.conversationId
        if (conversationId.isBlank()) return
        _state.update { it.copy(busyProactiveKey = busyKey) }
        viewModelScope.launch {
            runCatching {
                repository.proactive(conversationId, operation, buildJsonObject(input))
            }
                .onFailure {
                    _state.update { s ->
                        s.copy(transientError = strings.get(StringKey.OperationFailed))
                    }
                }
            _state.update { it.copy(busyProactiveKey = null) }
        }
    }

    // ---------- Route -> calendar offer ----------

    /** 网页端同款“添加到日程”：以 route_calendar_offer_accepted 活动发送一轮。 */
    fun requestRouteCalendarProposal(action: WorkspaceAction) {
        val routePlanId = action.payload.route_plan_id ?: return
        val turn = PendingChatTurn(
            id = UUID.randomUUID().toString(),
            text = strings.get(StringKey.RouteCalendarRequest),
            activity = "route_calendar_offer_accepted",
            routePlanId = routePlanId,
        )
        if (_state.value.streaming || streamJob?.isActive == true) {
            enqueue(turn, first = true)
            return
        }
        executeTurn(turn)
    }

    private fun executeTurn(turn: PendingChatTurn) {
        val conversationId = _state.value.conversationId
        if (conversationId.isBlank()) return
        activeTurn = turn
        runtimeStore.saveActiveTurn(conversationId, turn)
        lastUserMessage = turn.text
        lastClientMessageId = turn.id
        lastPresentationRevision = -1

        val firstQuestion = activeConversationPending &&
            _state.value.messages.none { it.role == ChatMessageUi.Role.USER }
        activeConversationPending = false
        if (firstQuestion) {
            _state.update { it.copy(conversationTitle = turn.text.take(30)) }
        }
        val userMessage = ChatMessageUi(
            id = turn.id,
            role = ChatMessageUi.Role.USER,
            clientMessageId = turn.id,
            content = turn.text,
            turnStartedAt = turn.createdAt,
        )
        val assistantId = _state.value.messages.lastOrNull {
            it.role == ChatMessageUi.Role.AI && it.clientMessageId == turn.id
        }?.id ?: UUID.randomUUID().toString()
        _state.update { current ->
            val hasUser = current.messages.any {
                it.role == ChatMessageUi.Role.USER && it.clientMessageId == turn.id
            }
            val hasAssistant = current.messages.any {
                it.role == ChatMessageUi.Role.AI && it.clientMessageId == turn.id
            }
            current.copy(
                messages = current.messages +
                    (if (hasUser) emptyList() else listOf(userMessage)) +
                    (if (hasAssistant) emptyList() else listOf(ChatMessageUi(
                    id = assistantId,
                    role = ChatMessageUi.Role.AI,
                    clientMessageId = turn.id,
                    streaming = true,
                    turnStartedAt = turn.createdAt,
                ))),
                streaming = true,
                recovering = false,
                transientError = null,
            )
        }

        // Index immediately so a new conversation moves to the top and its
        // first question becomes the default title before generation ends.
        viewModelScope.launch {
            runCatching {
                repository.touchConversation(
                    conversationId = conversationId,
                    title = turn.text.take(40).takeIf { firstQuestion },
                    messageCount = _state.value.messages.count { it.hasDurablePayload },
                )
            }
        }

        val body = buildJsonObject {
            put("message", turn.text)
            put("client_message_id", turn.id)
            turn.activity?.let { put("activity", it) }
            turn.routePlanId?.let { put("route_plan_id", it) }
            if (turn.referenceImages.isNotEmpty()) {
                putJsonArray("reference_images") {
                    turn.referenceImages.forEach { add(JsonPrimitive(it)) }
                }
            }
            if (turn.latitude != null && turn.longitude != null) {
                put("current_location", buildJsonObject {
                    put("latitude", turn.latitude)
                    put("longitude", turn.longitude)
                })
            }
        }
        startStream(assistantId, turn, body)
    }

    private fun enqueue(turn: PendingChatTurn, first: Boolean = false): Boolean {
        val state = _state.value
        if (state.queuedTurns.size >= ChatRuntimeStore.MAX_WAITING_TURNS) {
            return false
        }
        val next = if (first) listOf(turn) + state.queuedTurns else state.queuedTurns + turn
        runtimeStore.saveQueue(state.conversationId, next)
        _state.update { it.copy(queuedTurns = next) }
        return true
    }

    fun updateQueuedTurn(id: String, text: String) {
        val normalized = text.trim()
        if (normalized.isEmpty()) return
        val next = _state.value.queuedTurns.map {
            if (it.id == id) it.copy(text = normalized) else it
        }
        runtimeStore.saveQueue(_state.value.conversationId, next)
        _state.update { it.copy(queuedTurns = next) }
    }

    fun removeQueuedTurn(id: String) {
        val next = _state.value.queuedTurns.filterNot { it.id == id }
        runtimeStore.saveQueue(_state.value.conversationId, next)
        _state.update { it.copy(queuedTurns = next) }
    }

    fun interruptWithQueuedTurn(id: String) {
        val selected = _state.value.queuedTurns.firstOrNull { it.id == id } ?: return
        val reordered = listOf(selected) + _state.value.queuedTurns.filterNot { it.id == id }
        runtimeStore.saveQueue(_state.value.conversationId, reordered)
        _state.update { it.copy(queuedTurns = reordered) }
        stop()
    }

    private fun drainQueue() {
        val state = _state.value
        if (state.bootstrapping || state.streaming || streamJob?.isActive == true) return
        val next = state.queuedTurns.firstOrNull() ?: return
        val rest = state.queuedTurns.drop(1)
        runtimeStore.saveQueue(state.conversationId, rest)
        _state.update { it.copy(queuedTurns = rest) }
        executeTurn(next)
    }

    private fun startStream(assistantId: String, turn: PendingChatTurn, body: JsonObject) {
        val conversationId = _state.value.conversationId
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            var sawTerminal = false
            val typewriter = StreamTypewriter()

            // 独立的呈现时钟：把后端的文本分块按字符匀速吐到 UI，
            // 得到真正连续的流式观感（不改动任何字符内容）。
            val painter = launch {
                while (isActive) {
                    val slice = typewriter.nextFrame()
                    if (slice.isNotEmpty()) {
                        updateAssistant(assistantId) { it.copy(content = it.content + slice) }
                    }
                    delay(StreamTypewriter.FRAME_MILLIS)
                }
            }

            var streamError: Throwable? = null
            try {
                repository.streamChat(conversationId, body).collect { event ->
                    when (event) {
                        is ChatEvent.LocationRequest ->
                            _state.update { it.copy(locationRequestReason = event.reason) }
                        is ChatEvent.ProactiveUpdate ->
                            repository.publishProactiveUpdate(event.payload)
                        // 正文交给打字机排队，其余事件立即生效。
                        is ChatEvent.AiResponse -> typewriter.offer(event.content)
                        ChatEvent.AiResponseReset -> {
                            typewriter.reset()
                            updateAssistant(assistantId) { it.copy(content = "") }
                        }
                        is ChatEvent.Progress -> {
                            updateAssistant(assistantId) { current ->
                                val searchStart = if (
                                    event.payload.activity == "web_search" &&
                                    current.searchStartedAt == null
                                ) turn.createdAt else current.searchStartedAt
                                val searchEnd = if (
                                    event.payload.activity == "web_search" &&
                                    event.payload.status == "completed"
                                ) System.currentTimeMillis() else current.searchCompletedAt
                                current.reduce(event).copy(
                                    searchStartedAt = searchStart,
                                    searchCompletedAt = searchEnd,
                                )
                            }
                        }
                        is ChatEvent.AnswerComplete -> {
                            sawTerminal = true
                            typewriter.finish()
                            drain(typewriter, assistantId)
                            updateAssistant(assistantId) {
                                it.reduce(event).copy(
                                    searchCompletedAt = if (it.searchStartedAt != null) {
                                        System.currentTimeMillis()
                                    } else it.searchCompletedAt,
                                )
                            }
                        }
                        is ChatEvent.Error -> {
                            sawTerminal = true
                            typewriter.finish()
                            drain(typewriter, assistantId)
                            updateAssistant(assistantId) { it.reduce(event) }
                        }
                        else -> updateAssistant(assistantId) { it.reduce(event) }
                    }
                }
            } catch (error: Throwable) {
                streamError = error
            }
            // 无论如何都把缓冲里剩下的字符补齐，终态与后端一致。
            typewriter.finish()
            drain(typewriter, assistantId)
            painter.cancel()

            if (streamError != null && !sawTerminal) {
                _state.update { it.copy(recovering = true) }
                val recovered = recoverRun(conversationId, turn.id, assistantId)
                if (recovered) return@launch
                updateAssistant(assistantId) {
                    it.copy(
                        streaming = false,
                        failed = true,
                        error = strings.userFacingError(
                            streamError ?: IllegalStateException(),
                            StringKey.ChatConnectionInterrupted,
                        ),
                    )
                }
            }

            updateAssistant(assistantId) { current ->
                if (current.streaming) current.copy(
                    streaming = false,
                    failed = !sawTerminal && current.content.isBlank() && !current.hasDurablePayload,
                    error = if (!sawTerminal && current.content.isBlank()) {
                        strings.get(StringKey.ChatConnectionInterrupted)
                    } else current.error,
                ) else current
            }
            _state.update { it.copy(streaming = false, recovering = false) }
            runtimeStore.clearActiveTurn(conversationId, turn.id)
            activeTurn = null
            // Keep the tenant-level conversation index fresh (fire-and-forget).
            runCatching {
                repository.touchConversation(
                    conversationId,
                    title = null,
                    messageCount = _state.value.messages.count { it.hasDurablePayload },
                )
            }
            yield()
            streamJob = null
            drainQueue()
        }
    }

    /** 把打字机缓冲一次性排空到消息内容里。 */
    private fun drain(typewriter: StreamTypewriter, assistantId: String) {
        if (!typewriter.hasPending) return
        val rest = typewriter.nextFrame()
        if (rest.isNotEmpty()) {
            updateAssistant(assistantId) { it.copy(content = it.content + rest) }
        }
    }

    private fun updateAssistant(id: String, transform: (ChatMessageUi) -> ChatMessageUi) {
        _state.update { state ->
            state.copy(messages = state.messages.map { if (it.id == id) transform(it) else it })
        }
    }

    private fun updateAssistantByOwner(
        clientMessageId: String,
        transform: (ChatMessageUi) -> ChatMessageUi,
    ) {
        _state.update { state ->
            val index = state.messages.indexOfLast {
                it.role == ChatMessageUi.Role.AI && it.clientMessageId == clientMessageId
            }
            if (index < 0) state else state.copy(
                messages = state.messages.mapIndexed { itemIndex, item ->
                    if (itemIndex == index) transform(item) else item
                },
            )
        }
    }

    private fun recoverExistingRun(conversationId: String, run: ChatRun) {
        val assistantId = _state.value.messages.lastOrNull {
            it.role == ChatMessageUi.Role.AI && it.clientMessageId == run.client_message_id
        }?.id ?: return
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            recoverRun(conversationId, run.client_message_id, assistantId)
        }
    }

    /** Poll only Maker's existing checkpoint; never starts a second model turn. */
    private suspend fun recoverRun(
        conversationId: String,
        clientMessageId: String,
        assistantId: String,
    ): Boolean {
        var absentChecks = 0
        while (_state.value.conversationId == conversationId) {
            val state = runCatching { repository.chatRun(conversationId) }.getOrNull()
            val run = state?.run
            val sameTurn = run != null && (
                clientMessageId.isBlank() || run.client_message_id == clientMessageId
            )
            if (sameTurn && run?.active == true) {
                absentChecks = 0
                state.presentation?.takeIf {
                    it.client_message_id == clientMessageId && it.revision > lastPresentationRevision
                }?.let { presentation ->
                    lastPresentationRevision = presentation.revision
                    updateAssistant(assistantId) { applyPresentation(it, presentation) }
                }
                delay(RECOVERY_POLL_MS)
                continue
            }
            if (sameTurn && run?.status == "completed") {
                val data = runCatching { repository.bootstrap(conversationId) }.getOrNull()
                if (data != null && _state.value.conversationId == conversationId) {
                    _state.update { current ->
                        current.copy(
                            messages = data.messages.mapNotNull(::parseRestoredMessage),
                            streaming = false,
                            recovering = false,
                        )
                    }
                } else {
                    updateAssistant(assistantId) { it.copy(streaming = false) }
                    _state.update { it.copy(streaming = false, recovering = false) }
                }
                finishRecoveredTurn(conversationId, clientMessageId)
                return true
            }
            if (sameTurn && run?.status == "cancelled") {
                discardAssistantTurn(clientMessageId)
                _state.update { it.copy(streaming = false, recovering = false) }
                runtimeStore.clearStopIntent(conversationId, clientMessageId)
                finishRecoveredTurn(conversationId, clientMessageId)
                return true
            }
            if (sameTurn && run?.status == "failed") {
                updateAssistant(assistantId) {
                    it.copy(
                        streaming = false,
                        failed = true,
                        error = run.error ?: strings.get(StringKey.ChatGenerationFailed),
                    )
                }
                _state.update { it.copy(streaming = false, recovering = false) }
                finishRecoveredTurn(conversationId, clientMessageId)
                return true
            }
            if (run?.active == true) {
                // A newer turn may already own Maker. Never overwrite it with
                // stale presentation from the disconnected turn.
                delay(RECOVERY_POLL_MS)
                continue
            }
            absentChecks += 1
            if (absentChecks >= RECOVERY_ABSENT_GRACE_CHECKS) return false
            delay(RECOVERY_POLL_MS)
        }
        return true
    }

    private fun finishRecoveredTurn(conversationId: String, clientMessageId: String) {
        runtimeStore.clearActiveTurn(conversationId, clientMessageId)
        activeTurn = null
        streamJob = null
        viewModelScope.launch {
            yield()
            drainQueue()
        }
    }

    private fun discardAssistantTurn(clientMessageId: String) {
        _state.update { state ->
            state.copy(messages = state.messages.filterNot {
                it.role == ChatMessageUi.Role.AI && it.clientMessageId == clientMessageId
            })
        }
    }

    fun stop() {
        val conversationId = _state.value.conversationId
        val clientMessageId = activeTurn?.id
            ?: lastClientMessageId
            ?: _state.value.messages.lastOrNull { it.streaming }?.clientMessageId
            ?: return
        runtimeStore.markStopIntent(conversationId, clientMessageId)
        streamJob?.cancel()
        streamJob = null
        discardAssistantTurn(clientMessageId)
        _state.update { it.copy(streaming = false, recovering = false) }
        activeTurn = null
        confirmStop(conversationId, clientMessageId, null)
    }

    private fun confirmStop(conversationId: String, clientMessageId: String, knownRun: ChatRun?) {
        val confirmationKey = "$conversationId:$clientMessageId"
        if (stopConfirmationJobs[confirmationKey]?.isActive == true) return
        val job = viewModelScope.launch {
            var run = knownRun
            val backoff = ExponentialBackoff(RECOVERY_POLL_MS, STOP_RETRY_MAX_MS)
            try {
                while (runtimeStore.stoppedClientMessageId(conversationId) == clientMessageId) {
                    val acknowledgement = runCatching {
                        repository.stop(conversationId, clientMessageId)
                    }.getOrNull()
                    run = runCatching { repository.chatRun(conversationId).run }.getOrNull()
                    if (stopIsDurablyConfirmed(
                            requestedClientMessageId = clientMessageId,
                            acknowledgementClientMessageId = acknowledgement?.str("client_message_id"),
                            acknowledgementStatus = acknowledgement?.str("status"),
                            run = run,
                        )
                    ) {
                        runtimeStore.clearStopIntent(conversationId, clientMessageId)
                        runtimeStore.clearActiveTurn(conversationId, clientMessageId)
                        break
                    }
                    delay(backoff.nextDelayMillis())
                }
            } finally {
                stopConfirmationJobs.remove(confirmationKey)
                if (
                    _state.value.conversationId == conversationId &&
                    runtimeStore.stoppedClientMessageId(conversationId).isBlank()
                ) drainQueue()
            }
        }
        stopConfirmationJobs[confirmationKey] = job
    }

    fun retryLast() {
        val last = lastUserMessage ?: return
        // Drop the failed assistant tail before retrying.
        _state.update { state ->
            val trimmed = state.messages.dropLastWhile {
                it.role == ChatMessageUi.Role.AI && it.failed
            }
            state.copy(messages = trimmed)
        }
        send(last)
    }

    private fun updateAll(transform: (ChatMessageUi) -> ChatMessageUi) {
        _state.update { state -> state.copy(messages = state.messages.map(transform)) }
    }

    // ---------- Location ----------

    fun provideLocation(latitude: Double, longitude: Double) {
        _state.update { it.copy(locationRequestReason = null) }
        val roundedLatitude = String.format(Locale.ROOT, "%.2f", latitude)
        val roundedLongitude = String.format(Locale.ROOT, "%.2f", longitude)
        viewModelScope.launch {
            runCatching {
                repository.proactive(
                    _state.value.conversationId,
                    "ingest_signal",
                    buildJsonObject {
                        put("signal_type", "browser_location_weather")
                        put("dedup_key", "${LocalDate.now()}:$roundedLatitude:$roundedLongitude")
                        put("payload", buildJsonObject {
                            put("latitude", roundedLatitude.toDouble())
                            put("longitude", roundedLongitude.toDouble())
                        })
                    },
                )
            }
        }
        val message = lastUserMessage ?: return
        enqueue(
            PendingChatTurn(
                id = UUID.randomUUID().toString(),
                text = message,
                latitude = latitude,
                longitude = longitude,
            ),
            first = true,
        )
    }

    fun dismissLocationRequest() {
        _state.update { it.copy(locationRequestReason = null) }
    }

    // ---------- Clarification ----------

    fun submitClarification(clarification: Clarification, answers: Map<String, Any>) {
        if (_state.value.streaming) return
        _state.update { it.copy(submittingClarification = true) }
        val summary = answers.entries.joinToString("；") { "${it.key}: ${it.value}" }
        val turn = PendingChatTurn(
            id = UUID.randomUUID().toString(),
            text = strings.get(StringKey.ClarificationAnswered, summary),
        )
        activeTurn = turn
        lastClientMessageId = turn.id
        lastUserMessage = turn.text
        val assistantId = UUID.randomUUID().toString()
        _state.update { state ->
            state.copy(
                messages = state.messages
                    // 提交后立刻摘掉这张澄清卡：答案已经在路上，
                    // 不能让用户对着已生效的选择继续改。
                    .map { message ->
                        if (message.clarification?.id == clarification.id) {
                            message.copy(clarification = null, clarificationAnswered = summary)
                        } else {
                            message
                        }
                    } + ChatMessageUi(
                    id = assistantId,
                    role = ChatMessageUi.Role.AI,
                    clientMessageId = turn.id,
                    streaming = true,
                    turnStartedAt = turn.createdAt,
                ),
                streaming = true,
                submittingClarification = false,
            )
        }
        val body = buildJsonObject {
            put("message", turn.text)
            put("client_message_id", turn.id)
            put("clarification_response", buildJsonObject {
                put("clarification_id", clarification.id)
                answers.forEach { (key, value) ->
                    when (value) {
                        is Boolean -> put(key, value)
                        is Number -> put(key, value.toDouble())
                        is List<*> -> putJsonArray(key) { value.forEach { v -> add(JsonPrimitive(v.toString())) } }
                        else -> put(key, value.toString())
                    }
                }
            })
        }
        startStream(assistantId, turn, body)
    }

    // ---------- Workspace actions ----------

    fun confirmAction(action: WorkspaceAction) = workspaceAction(action, "confirm_action")
    fun cancelAction(action: WorkspaceAction) = workspaceAction(action, "cancel_action")
    fun updateMeetingAction(
        action: WorkspaceAction,
        subject: String,
        startTime: String,
        endTime: String,
    ) = workspaceAction(
        action,
        "update_meeting_action",
        buildJsonObject {
            put("subject", subject)
            put("start_time", startTime)
            put("end_time", endTime)
        },
    )

    fun activateMap(action: WorkspaceAction) {
        val conversationId = _state.value.conversationId
        _state.update { it.copy(busyActionId = action.id) }
        viewModelScope.launch {
            runCatching {
                repository.workspaceOperation(
                    conversationId, "activate_map",
                    buildJsonObject {
                        put("action_id", action.id)
                        put("version", action.version)
                    },
                )
            }.onSuccess { response ->
                response.obj("map")?.let { map ->
                    repository.publishMapWorkspace(map, action.payload.title)
                }
                response.obj("action")?.let { element ->
                    runCatching {
                        json.decodeFromJsonElement(WorkspaceAction.serializer(), element)
                    }.getOrNull()?.let(::replaceAction)
                }
            }
            _state.update { it.copy(busyActionId = null) }
        }
    }

    /** Continue an existing image action through the shared Maker /image stream. */
    fun editImage(action: WorkspaceAction, prompt: String) {
        val instruction = prompt.trim()
        if (instruction.isEmpty() || _state.value.busyActionId != null) return
        val conversationId = _state.value.conversationId
        _state.update { it.copy(busyActionId = action.id, transientError = null) }
        viewModelScope.launch {
            runCatching {
                repository.streamImageEdit(conversationId, instruction, action.id).collect { event ->
                    when (event) {
                        is ChatEvent.ImageAction -> {
                            replaceAction(event.action)
                            ingestGeneratedImage(event.action)
                        }
                        is ChatEvent.WorkspaceActionEvent -> {
                            replaceAction(event.action)
                            ingestGeneratedImage(event.action)
                        }
                        is ChatEvent.Error -> error(event.content)
                        else -> Unit
                    }
                }
            }.onFailure { failure ->
                _state.update {
                    it.copy(
                        transientError = strings.userFacingError(failure, StringKey.ChatImageFailed),
                    )
                }
            }
            _state.update { it.copy(busyActionId = null) }
        }
    }

    private fun workspaceAction(
        action: WorkspaceAction,
        operation: String,
        input: JsonObject = JsonObject(emptyMap()),
    ) {
        val conversationId = _state.value.conversationId
        _state.update { it.copy(busyActionId = action.id) }
        viewModelScope.launch {
            runCatching {
                repository.workspaceOperation(
                    conversationId, operation,
                    buildJsonObject {
                        put("action_id", action.id)
                        put("version", action.version)
                        input.forEach { (key, value) -> put(key, value) }
                    },
                )
            }.onSuccess { response ->
                // Only the backend-confirmed action status is rendered.
                response.obj("action")?.let { element ->
                    runCatching {
                        json.decodeFromJsonElement(WorkspaceAction.serializer(), element)
                    }.getOrNull()?.let { next ->
                        replaceAction(next)
                        ingestGeneratedImage(next)
                    }
                }
                response.arr("schedules")?.let {
                    repository.schedulesFlow.value = repository.parseSchedules(it)
                }
            }.onFailure {
                _state.update {
                    it.copy(transientError = strings.get(StringKey.OperationFailed))
                }
            }
            _state.update { it.copy(busyActionId = null) }
        }
    }

    private suspend fun ingestGeneratedImage(action: WorkspaceAction) {
        val prompt = action.payload.prompt
            ?: action.result?.str("prompt")
            ?: return
        if (action.kind != "image_generate" || action.status != "succeeded" || prompt.isBlank()) return
        val hasPrevious = !action.payload.parent_action_id.isNullOrBlank()
        runCatching {
            repository.proactive(
                _state.value.conversationId,
                "ingest_signal",
                buildJsonObject {
                    put("signal_type", "image_generated")
                    put("dedup_key", action.id)
                    put("payload", buildJsonObject {
                        put("action_id", action.id)
                        put("prompt", prompt)
                        put("has_reference_image", hasPrevious)
                        put("has_previous_version", hasPrevious)
                    })
                },
            )
        }
    }

    private fun replaceAction(next: WorkspaceAction) {
        updateAll { message ->
            if (message.actions.any { it.id == next.id }) {
                message.copy(actions = message.actions.map { if (it.id == next.id) next else it })
            } else message
        }
    }

    fun consumeError() = _state.update { it.copy(transientError = null) }

    private companion object {
        const val RECOVERY_POLL_MS = 850L
        const val STOP_RETRY_MAX_MS = 30_000L
        const val RECOVERY_ABSENT_GRACE_CHECKS = 8
    }
}
