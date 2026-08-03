package com.floris.android.ui.papers

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.network.ReaderChunk
import com.floris.android.core.model.Paper
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.pressable
import com.floris.android.ui.prefs.Language
import com.floris.android.ui.prefs.LocalLanguage
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import com.floris.android.ui.readingViewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class ReadingViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class ReaderState(
        val title: String = "",
        val action: String = "",
        val content: String = "",
        val streaming: Boolean = false,
        val error: String? = null,
    )

    data class UiState(
        val searching: Boolean = false,
        val results: List<Paper> = emptyList(),
        val searched: Boolean = false,
        val library: FlorisRepository.Library = FlorisRepository.Library(),
        val loadingLibrary: Boolean = true,
        val reader: ReaderState? = null,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private var readerJob: Job? = null

    init { loadLibrary() }

    fun search(topic: String) {
        if (topic.isBlank()) return
        _state.update { it.copy(searching = true, error = null) }
        viewModelScope.launch {
            runCatching { repository.searchPapers(topic) }
                .onSuccess { papers ->
                    _state.update { it.copy(searching = false, results = papers, searched = true) }
                }
                .onFailure {
                    _state.update { it.copy(searching = false, searched = true, error = "论文检索失败") }
                }
        }
    }

    fun loadLibrary() {
        // 已有书架数据时不再显示加载态：后端云函数可能要几秒才回，
        // 先让用户看到上次的内容，新数据到了再替换。
        if (!_state.value.library.isEmpty) {
            _state.update { it.copy(loadingLibrary = false) }
        }
        viewModelScope.launch {
            runCatching { repository.readingLibrary() }
                .onSuccess { library ->
                    _state.update { it.copy(library = library, loadingLibrary = false) }
                }
                .onFailure { _state.update { it.copy(loadingLibrary = false) } }
        }
    }

    /** 论文助读：总结 / 翻译，走后端 /reader 流式。 */
    fun runReader(action: String, title: String, sourceText: String, language: Language) {
        readerJob?.cancel()
        _state.update {
            it.copy(reader = ReaderState(title = title, action = action, streaming = true))
        }
        readerJob = viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching {
                repository.streamReader(
                    conversationId = conversationId,
                    action = action,
                    text = sourceText,
                    responseLanguage = language.tag,
                ).collect { chunk ->
                    when (chunk) {
                        is ReaderChunk.Delta -> _state.update { s ->
                            s.copy(reader = s.reader?.copy(content = s.reader.content + chunk.text))
                        }
                        is ReaderChunk.Error -> _state.update { s ->
                            s.copy(reader = s.reader?.copy(streaming = false, error = chunk.message))
                        }
                        ReaderChunk.Done, ReaderChunk.Ignored -> Unit
                    }
                }
            }.onFailure { error ->
                _state.update { s ->
                    s.copy(reader = s.reader?.copy(streaming = false, error = error.message ?: "阅读失败"))
                }
            }
            _state.update { s -> s.copy(reader = s.reader?.copy(streaming = false)) }
        }
    }

    fun closeReader() {
        readerJob?.cancel()
        _state.update { it.copy(reader = null) }
    }

    fun consumeError() = _state.update { it.copy(error = null) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReadingScreen(container: AppContainer, owner: ViewModelStoreOwner? = null) {
    val viewModel: ReadingViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "reading",
        factory = container.readingViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val language = LocalLanguage.current
    var query by remember { mutableStateOf("") }
    var selectedFolder by remember { mutableStateOf<String?>(null) }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        // 标题区
        Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 6.dp, bottom = 10.dp)) {
            Text(t(StringKey.ReadingTitle), style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(10.dp))
            SearchField(
                value = query,
                onValueChange = { query = it },
                hint = t(StringKey.ReadingSearchHint),
                onSearch = { viewModel.search(query) },
            )
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (state.searching) {
                item { InlineLoading() }
            }

            if (state.results.isNotEmpty()) {
                item(key = "results-header") { SectionHeader("检索结果 · ${state.results.size}") }
                items(state.results, key = { it.arxiv_id ?: it.title }) { paper ->
                    AnimateIn(0) {
                        PaperCard(
                            paper = paper,
                            onSummarize = {
                                viewModel.runReader(
                                    "summarize",
                                    paper.title,
                                    readerSource(paper),
                                    language,
                                )
                            },
                            onTranslate = {
                                viewModel.runReader(
                                    "translate",
                                    paper.title,
                                    readerSource(paper),
                                    language,
                                )
                            },
                        )
                    }
                }
            } else if (state.searched && !state.searching) {
                item(key = "no-result") {
                    EmptyState(t(StringKey.ReadingNoResultTitle), t(StringKey.ReadingNoResultBody))
                }
            }

            // 阅读库（后端自动整理的文件夹）
            val library = state.library
            if (library.items.isNotEmpty() || library.folders.isNotEmpty()) {
                item(key = "library-header") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        SectionHeader(t(StringKey.ReadingLibrary), Modifier.weight(1f))
                        if (library.autoOrganize) {
                            StatusChip("自动整理", MaterialTheme.colorScheme.tertiary)
                        }
                    }
                }
                if (library.folders.isNotEmpty()) {
                    item(key = "folders") {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            FolderChip(
                                name = "全部",
                                selected = selectedFolder == null,
                                onClick = { selectedFolder = null },
                            )
                            library.folders.take(3).forEach { folder ->
                                FolderChip(
                                    name = folder.name,
                                    selected = selectedFolder == folder.id,
                                    onClick = {
                                        selectedFolder = if (selectedFolder == folder.id) null else folder.id
                                    },
                                )
                            }
                        }
                    }
                }
                val visible = library.items.filter { selectedFolder == null || it.folderId == selectedFolder }
                items(visible, key = { it.id }) { item ->
                    AnimateIn(0) {
                        FlorisCard {
                            Row(
                                Modifier.padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    Icons.Outlined.Description, null,
                                    tint = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(10.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        item.title,
                                        style = MaterialTheme.typography.titleMedium,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    item.preview?.let {
                                        Text(
                                            it,
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                        )
                                    }
                                }
                                if (item.isPaper) {
                                    StatusChip("论文", MaterialTheme.colorScheme.secondary)
                                }
                            }
                        }
                    }
                }
            } else if (state.results.isEmpty() && !state.searched && !state.loadingLibrary) {
                item(key = "empty") {
                    EmptyState(t(StringKey.ReadingEmptyTitle), t(StringKey.ReadingEmptyBody))
                }
            }
        }
    }

    // 助读结果面板
    state.reader?.let { reader ->
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(
            onDismissRequest = viewModel::closeReader,
            sheetState = sheetState,
            containerColor = MaterialTheme.colorScheme.surface,
        ) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 240.dp)
                    .padding(horizontal = 20.dp)
                    .padding(bottom = 28.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(
                        if (reader.action == "translate") t(StringKey.ReadingTranslate)
                        else t(StringKey.ReadingSummarize),
                        MaterialTheme.colorScheme.primary,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        reader.title,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                }
                Spacer(Modifier.height(14.dp))
                if (reader.content.isBlank() && reader.streaming) {
                    InlineLoading()
                } else {
                    MarkdownText(reader.content, streaming = reader.streaming)
                }
                reader.error?.let {
                    Spacer(Modifier.height(10.dp))
                    Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

private fun readerSource(paper: Paper): String = buildString {
    appendLine(paper.title)
    paper.authors?.let { appendLine("Authors: $it") }
    paper.abstract_zh?.let { appendLine(); appendLine(it) }
    paper.key_contribution?.let { appendLine(); appendLine(it) }
}

@Composable
private fun FolderChip(name: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(
                if (selected) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surface,
            )
            .pressable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Default.Folder, null,
            tint = if (selected) MaterialTheme.colorScheme.onPrimaryContainer
            else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(5.dp))
        Text(
            name,
            style = MaterialTheme.typography.labelMedium,
            color = if (selected) MaterialTheme.colorScheme.onPrimaryContainer
            else MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
        )
    }
}

@Composable
private fun PaperCard(paper: Paper, onSummarize: () -> Unit, onTranslate: () -> Unit) {
    val uriHandler = LocalUriHandler.current
    FlorisCard {
        Column(Modifier.padding(14.dp)) {
            Text(
                paper.title,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                listOfNotNull(
                    paper.authors?.split(",")?.take(2)?.joinToString(", "),
                    paper.year?.toString(),
                    paper.citations?.let { "被引 $it" },
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            paper.abstract_zh?.let {
                Spacer(Modifier.height(8.dp))
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PillButton(
                    text = t(StringKey.ReadingSummarize),
                    onClick = onSummarize,
                    style = PillStyle.Tonal,
                    compact = true,
                )
                PillButton(
                    text = t(StringKey.ReadingTranslate),
                    onClick = onTranslate,
                    style = PillStyle.Ghost,
                    compact = true,
                )
                Spacer(Modifier.weight(1f))
                paper.arxiv_url?.let { url ->
                    PillButton(
                        text = "arXiv",
                        onClick = { runCatching { uriHandler.openUri(url) } },
                        style = PillStyle.Ghost,
                        compact = true,
                    )
                }
            }
        }
    }
}

/** 统一的搜索输入（无边框、药丸底衬，避免突兀文本框）。 */
@Composable
fun SearchField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    onSearch: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(999.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Default.Search, null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(17.dp),
        )
        Spacer(Modifier.width(9.dp))
        Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
            if (value.isEmpty()) {
                Text(
                    hint,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodySmall.copy(
                    color = MaterialTheme.colorScheme.onSurface,
                ),
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { onSearch() }),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        AnimatedVisibility(visible = value.isNotEmpty()) {
            Text(
                t(StringKey.Search),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.pressable(onClick = onSearch).padding(start = 8.dp),
            )
        }
    }
}
