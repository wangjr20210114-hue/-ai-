package com.floris.android.ui.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.core.chat.reduce
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.network.sse.ChatEvent
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.MediaGrid
import com.floris.android.ui.components.ProgressBar
import com.floris.android.ui.components.SearchSourcesRow
import com.floris.android.ui.components.pressable
import com.floris.android.ui.searchViewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

/**
 * AI search: a dedicated conversation id whose turns are rendered in a
 * search-optimized layout. All orchestration stays on the backend.
 */
class SearchViewModel(
    private val repository: FlorisRepository,
    private val json: Json,
) : ViewModel() {

    data class UiState(
        val query: String = "",
        val active: ChatMessageUi? = null,
        val searching: Boolean = false,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private var job: Job? = null
    private var conversationId: String? = null

    fun search(query: String) {
        val trimmed = query.trim()
        if (trimmed.isEmpty() || _state.value.searching) return
        val messageId = UUID.randomUUID().toString()
        _state.update {
            it.copy(
                query = trimmed,
                active = ChatMessageUi(id = messageId, role = ChatMessageUi.Role.AI, streaming = true),
                searching = true,
            )
        }
        job?.cancel()
        job = viewModelScope.launch {
            val id = conversationId ?: repository.searchConversationId().also { conversationId = it }
            runCatching {
                repository.streamChat(
                    id,
                    buildJsonObject {
                        put("message", trimmed)
                        put("client_message_id", messageId)
                    },
                ).collect { event ->
                    if (event is ChatEvent.LocationRequest) return@collect
                    _state.update { s -> s.copy(active = s.active?.reduce(event)) }
                }
            }
            _state.update { s ->
                s.copy(
                    searching = false,
                    active = s.active?.copy(
                        streaming = false,
                        failed = s.active.content.isBlank() && s.active.searchResults == null,
                        error = if (s.active.content.isBlank() && s.active.searchResults == null) "搜索失败，请重试" else null,
                    ),
                )
            }
        }
    }

    fun stop() {
        job?.cancel()
        viewModelScope.launch { conversationId?.let { runCatching { repository.stop(it) } } }
        _state.update { it.copy(searching = false, active = it.active?.copy(streaming = false)) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(container: AppContainer) {
    val viewModel: SearchViewModel = viewModel(factory = container.searchViewModelFactory())
    val state by viewModel.state.collectAsState()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    var input by remember { mutableStateOf("") }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text("搜索") },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text("搜索任何问题…") },
                    leadingIcon = { Icon(Icons.Default.Search, null) },
                    trailingIcon = {
                        if (input.isNotEmpty()) {
                            Icon(
                                Icons.Default.Close, "清除",
                                modifier = Modifier.pressable { input = "" },
                            )
                        }
                    },
                    singleLine = true,
                    shape = CircleShape,
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = MaterialTheme.colorScheme.surface,
                        unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                    ),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { viewModel.search(input) }),
                    modifier = Modifier.weight(1f),
                )
                if (state.searching) {
                    Spacer(Modifier.size(8.dp))
                    Text(
                        "停止",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.pressable(onClick = viewModel::stop).padding(8.dp),
                    )
                }
            }

            val active = state.active
            if (active == null) {
                EmptyState(
                    title = "AI 搜索",
                    subtitle = "实时联网检索，带来源引用与图片",
                    modifier = Modifier.weight(1f),
                )
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    item(key = "query") {
                        AnimateIn(0) {
                            Text(state.query, style = MaterialTheme.typography.headlineSmall)
                        }
                    }
                    item(key = "progress") {
                        active.progress?.let { progress ->
                            if (active.streaming) ProgressBar(progress)
                        }
                    }
                    active.searchResults?.let { meta ->
                        if (meta.results.isNotEmpty()) {
                            item(key = "sources") { SearchSourcesRow(meta) }
                        }
                        if (meta.media.isNotEmpty()) {
                            item(key = "media") { MediaGrid(meta.media) }
                        }
                    }
                    if (active.content.isNotBlank()) {
                        item(key = "answer") {
                            AnimateIn(1) {
                                Column(
                                    Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(16.dp))
                                        .then(Modifier),
                                ) {
                                    MarkdownText(active.content, streaming = active.streaming)
                                }
                            }
                        }
                    }
                    active.error?.let { error ->
                        item(key = "error") {
                            Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelLarge)
                        }
                    }
                    item { Spacer(Modifier.height(24.dp)) }
                }
            }
        }
    }
}
