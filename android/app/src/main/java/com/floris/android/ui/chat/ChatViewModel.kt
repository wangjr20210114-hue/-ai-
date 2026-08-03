package com.floris.android.ui.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.core.chat.StreamTypewriter
import com.floris.android.core.chat.reduce
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.arr
import com.floris.android.core.data.asString
import com.floris.android.core.data.obj
import com.floris.android.core.data.str
import com.floris.android.core.model.Clarification
import com.floris.android.core.model.Paper
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import com.floris.android.core.network.sse.ChatEvent
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.util.UUID

data class ChatUiState(
    val conversationId: String = "",
    val messages: List<ChatMessageUi> = emptyList(),
    val streaming: Boolean = false,
    val bootstrapping: Boolean = true,
    val busyActionId: String? = null,
    val submittingClarification: Boolean = false,
    val locationRequestReason: String? = null,
    val transientError: String? = null,
)

class ChatViewModel(
    private val repository: FlorisRepository,
    private val json: Json,
) : ViewModel() {

    private val _state = MutableStateFlow(ChatUiState())
    val state = _state.asStateFlow()

    private var streamJob: Job? = null
    private var lastUserMessage: String? = null
    private var lastClientMessageId: String? = null
    private var restored = false

    init {
        viewModelScope.launch {
            val id = repository.activeConversationId()
            _state.update { it.copy(conversationId = id) }
            restore(id)
        }
    }

    // ---------- Restore ----------

    fun openConversation(id: String) {
        if (id == _state.value.conversationId && restored) return
        streamJob?.cancel()
        viewModelScope.launch {
            repository.setActiveConversationId(id)
            _state.value = ChatUiState(conversationId = id)
            restore(id)
        }
    }

    fun newConversation() {
        streamJob?.cancel()
        val id = repository.newConversationId()
        viewModelScope.launch { repository.setActiveConversationId(id) }
        _state.value = ChatUiState(conversationId = id, bootstrapping = false)
        restored = true
    }

    private suspend fun restore(conversationId: String) {
        _state.update { it.copy(bootstrapping = true) }
        runCatching { repository.bootstrap(conversationId) }
            .onSuccess { data ->
                val parsed = data.messages.mapNotNull(::parseRestoredMessage)
                _state.update { it.copy(messages = parsed, bootstrapping = false) }
                data.schedules.takeIf { it.isNotEmpty() }?.let {
                    repository.schedulesFlow.value = repository.parseSchedules(JsonArray(it))
                }
            }
            .onFailure { _state.update { it.copy(bootstrapping = false, transientError = "历史恢复失败") } }
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
            content = content(),
            searchResults = search,
            papers = papers,
            actions = actions,
            followUps = followUps,
            clarification = clarification,
            streaming = false,
        ).takeIf { it.hasDurablePayload }
    }

    // ---------- Send ----------

    fun send(text: String, referenceImages: List<String> = emptyList(), location: Pair<Double, Double>? = null) {
        val message = text.trim()
        if (message.isEmpty() || _state.value.streaming) return
        val clientMessageId = UUID.randomUUID().toString()
        lastUserMessage = message
        lastClientMessageId = clientMessageId

        val userMessage = ChatMessageUi(
            id = clientMessageId,
            role = ChatMessageUi.Role.USER,
            content = message,
        )
        val assistantId = UUID.randomUUID().toString()
        _state.update {
            it.copy(
                messages = it.messages + userMessage + ChatMessageUi(
                    id = assistantId,
                    role = ChatMessageUi.Role.AI,
                    streaming = true,
                ),
                streaming = true,
                transientError = null,
            )
        }

        val body = buildJsonObject {
            put("message", message)
            put("client_message_id", clientMessageId)
            if (referenceImages.isNotEmpty()) {
                putJsonArray("reference_images") {
                    referenceImages.take(3).forEach { add(JsonPrimitive(it)) }
                }
            }
            location?.let { (lat, lng) ->
                put("current_location", buildJsonObject {
                    put("latitude", lat)
                    put("longitude", lng)
                })
            }
        }
        startStream(assistantId, body)
    }

    private fun startStream(assistantId: String, body: JsonObject) {
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

            runCatching {
                repository.streamChat(conversationId, body).collect { event ->
                    when (event) {
                        is ChatEvent.LocationRequest ->
                            _state.update { it.copy(locationRequestReason = event.reason) }
                        // 正文交给打字机排队，其余事件立即生效。
                        is ChatEvent.AiResponse -> typewriter.offer(event.content)
                        ChatEvent.AiResponseReset -> {
                            typewriter.reset()
                            updateAssistant(assistantId) { it.copy(content = "") }
                        }
                        is ChatEvent.AnswerComplete -> {
                            sawTerminal = true
                            typewriter.finish()
                            drain(typewriter, assistantId)
                            updateAssistant(assistantId) { it.reduce(event) }
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
            }.onFailure { error ->
                typewriter.finish()
                drain(typewriter, assistantId)
                updateAssistant(assistantId) {
                    it.copy(streaming = false, failed = true, error = error.message ?: "网络错误")
                }
            }
            // 无论如何都把缓冲里剩下的字符补齐，终态与后端一致。
            typewriter.finish()
            drain(typewriter, assistantId)
            painter.cancel()

            updateAssistant(assistantId) { current ->
                if (current.streaming) current.copy(
                    streaming = false,
                    failed = !sawTerminal && current.content.isBlank() && !current.hasDurablePayload,
                    error = if (!sawTerminal && current.content.isBlank()) "连接中断，请重试" else current.error,
                ) else current
            }
            _state.update { it.copy(streaming = false) }
            // Keep the tenant-level conversation index fresh (fire-and-forget).
            runCatching {
                repository.touchConversation(
                    conversationId,
                    lastUserMessage?.take(40) ?: "新对话",
                    _state.value.messages.count { it.hasDurablePayload },
                )
            }
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

    fun stop() {
        val conversationId = _state.value.conversationId
        streamJob?.cancel()
        viewModelScope.launch { runCatching { repository.stop(conversationId) } }
        updateAll { if (it.streaming) it.copy(streaming = false) else it }
        _state.update { it.copy(streaming = false) }
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
        val message = lastUserMessage ?: return
        send(message, location = latitude to longitude)
    }

    fun dismissLocationRequest() {
        _state.update { it.copy(locationRequestReason = null) }
    }

    // ---------- Clarification ----------

    fun submitClarification(clarification: Clarification, answers: Map<String, Any>) {
        if (_state.value.streaming) return
        _state.update { it.copy(submittingClarification = true) }
        val summary = answers.entries.joinToString("；") { "${it.key}: ${it.value}" }
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
                    id = assistantId, role = ChatMessageUi.Role.AI, streaming = true,
                ),
                streaming = true,
                submittingClarification = false,
            )
        }
        val body = buildJsonObject {
            put("message", "（已提交澄清）$summary")
            put("client_message_id", UUID.randomUUID().toString())
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
        startStream(assistantId, body)
    }

    // ---------- Workspace actions ----------

    fun confirmAction(action: WorkspaceAction) = workspaceAction(action, "confirm_action")
    fun cancelAction(action: WorkspaceAction) = workspaceAction(action, "cancel_action")

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

    private fun workspaceAction(action: WorkspaceAction, operation: String) {
        val conversationId = _state.value.conversationId
        _state.update { it.copy(busyActionId = action.id) }
        viewModelScope.launch {
            runCatching {
                repository.workspaceOperation(
                    conversationId, operation,
                    buildJsonObject {
                        put("action_id", action.id)
                        put("version", action.version)
                    },
                )
            }.onSuccess { response ->
                // Only the backend-confirmed action status is rendered.
                response.obj("action")?.let { element ->
                    runCatching {
                        json.decodeFromJsonElement(WorkspaceAction.serializer(), element)
                    }.getOrNull()?.let(::replaceAction)
                }
                response.arr("schedules")?.let {
                    repository.schedulesFlow.value = repository.parseSchedules(it)
                }
            }.onFailure {
                _state.update { s -> s.copy(transientError = "操作失败，请稍后重试") }
            }
            _state.update { it.copy(busyActionId = null) }
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
}
