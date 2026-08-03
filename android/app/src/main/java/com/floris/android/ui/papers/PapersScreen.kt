package com.floris.android.ui.papers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.arr
import com.floris.android.core.data.str
import com.floris.android.core.model.Paper
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.PaperListCard
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.papersViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class PapersViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class UiState(
        val searching: Boolean = false,
        val results: List<Paper> = emptyList(),
        val libraryItems: List<String> = emptyList(),
        val searched: Boolean = false,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { loadLibrary() }

    fun search(topic: String) {
        if (topic.isBlank()) return
        _state.value = _state.value.copy(searching = true, error = null)
        viewModelScope.launch {
            runCatching { repository.searchPapers(topic) }
                .onSuccess { _state.value = _state.value.copy(searching = false, results = it, searched = true) }
                .onFailure { _state.value = _state.value.copy(searching = false, error = "论文检索失败", searched = true) }
        }
    }

    fun loadLibrary() {
        viewModelScope.launch {
            runCatching { repository.loadLibrary() }
                .onSuccess { library ->
                    val titles = library.arr("items")?.mapNotNull { item ->
                        (item as? kotlinx.serialization.json.JsonObject)?.str("title")
                    }?.take(20).orEmpty()
                    _state.value = _state.value.copy(libraryItems = titles)
                }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PapersScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: PapersViewModel = viewModel(factory = container.papersViewModelFactory())
    val state by viewModel.state.collectAsState()
    var query by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("论文") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回") }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = "search") {
                TextField(
                    value = query,
                    onValueChange = { query = it },
                    placeholder = { Text("检索 arXiv 论文…") },
                    leadingIcon = { Icon(Icons.Default.Search, null) },
                    singleLine = true,
                    shape = CircleShape,
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = MaterialTheme.colorScheme.surface,
                        unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                    ),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { viewModel.search(query) }),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            when {
                state.searching -> item { InlineLoading() }
                state.results.isNotEmpty() -> item { PaperListCard(state.results) }
                state.searched -> item { EmptyState("没有找到相关论文", "换个关键词试试") }
                state.libraryItems.isNotEmpty() -> {
                    item { SectionHeader("阅读库") }
                    items(state.libraryItems) { title ->
                        AnimateIn(0) {
                            com.floris.android.ui.components.FlorisCard {
                                Text(
                                    title,
                                    style = MaterialTheme.typography.titleMedium,
                                    modifier = Modifier.padding(14.dp),
                                )
                            }
                        }
                    }
                }
                else -> item {
                    EmptyState("论文检索", "搜索经过验证的学术记录，或在聊天中让 Floris 帮你读论文")
                }
            }
        }
    }
}
