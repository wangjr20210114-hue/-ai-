package com.floris.android.ui.history

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.ConversationSummary
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.historyViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HistoryViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val conversations: List<ConversationSummary> = emptyList(),
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            runCatching { repository.listConversations() }
                .onSuccess { _state.value = UiState(loading = false, conversations = it) }
                .onFailure { _state.value = UiState(loading = false, error = "加载失败") }
        }
    }

    fun delete(id: String) {
        val before = _state.value.conversations
        _state.value = _state.value.copy(conversations = before.filterNot { it.id == id })
        viewModelScope.launch {
            runCatching { repository.deleteConversation(id) }
                .onFailure { _state.value = _state.value.copy(conversations = before) }
        }
    }

    suspend fun open(id: String) = repository.setActiveConversationId(id)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onOpenConversation: () -> Unit,
) {
    val viewModel: HistoryViewModel = viewModel(factory = container.historyViewModelFactory())
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconPill(
                icon = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = "返回",
                onClick = onBack,
            )
            Spacer(Modifier.width(4.dp))
            Text(t(StringKey.ChatHistory), style = MaterialTheme.typography.headlineMedium)
        }

        Box(Modifier.weight(1f)) {
            when {
                state.loading -> InlineLoading()
                state.conversations.isEmpty() -> EmptyState(
                    t(StringKey.ChatEmptyHistoryTitle),
                    t(StringKey.ChatEmptyHistoryBody),
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.conversations, key = { it.id }) { conversation ->
                        val dismissState = rememberSwipeToDismissBoxState(
                            confirmValueChange = { value ->
                                if (value == SwipeToDismissBoxValue.EndToStart) {
                                    viewModel.delete(conversation.id)
                                    true
                                } else false
                            },
                        )
                        AnimateIn(0) {
                            SwipeToDismissBox(
                                state = dismissState,
                                enableDismissFromStartToEnd = false,
                                backgroundContent = {
                                    Box(
                                        Modifier.fillMaxSize().padding(end = 20.dp),
                                        contentAlignment = Alignment.CenterEnd,
                                    ) {
                                        Icon(
                                            Icons.Default.DeleteOutline, "删除",
                                            tint = MaterialTheme.colorScheme.error,
                                            modifier = Modifier.size(20.dp),
                                        )
                                    }
                                },
                            ) {
                                ConversationRow(conversation) {
                                    scope.launch {
                                        viewModel.open(conversation.id)
                                        onOpenConversation()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ConversationRow(conversation: ConversationSummary, onClick: () -> Unit) {
    FlorisCard(onClick = onClick) {
        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    conversation.title.ifBlank { t(StringKey.ChatNew) },
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    "${conversation.messageCount} 条 · ${relativeTime(conversation.updatedAt)}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            when (conversation.activityStatus) {
                "running" -> StatusChip(t(StringKey.ActionActive), MaterialTheme.colorScheme.primary)
                "failed" -> StatusChip(t(StringKey.ActionFailed), MaterialTheme.colorScheme.error)
            }
        }
    }
}

private fun relativeTime(timestamp: Long): String {
    if (timestamp <= 0) return ""
    val millis = if (timestamp < 10_000_000_000L) timestamp * 1000 else timestamp
    val diff = System.currentTimeMillis() - millis
    return when {
        diff < 60_000 -> "刚刚"
        diff < 3_600_000 -> "${diff / 60_000} 分钟前"
        diff < 86_400_000 -> "${diff / 3_600_000} 小时前"
        diff < 7 * 86_400_000L -> "${diff / 86_400_000} 天前"
        else -> SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date(millis))
    }
}
