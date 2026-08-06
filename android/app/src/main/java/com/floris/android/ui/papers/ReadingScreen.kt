package com.floris.android.ui.papers

import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.automirrored.filled.DriveFileMove
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.core.content.FileProvider
import com.floris.android.AppContainer
import com.floris.android.BuildConfig
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.network.ReaderChunk
import com.floris.android.core.model.Paper
import com.floris.android.core.model.SkillAccess
import com.floris.android.core.model.SkillAccessStatus
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.FlorisSwitch
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.SkillAccessNotice
import com.floris.android.ui.components.pressable
import com.floris.android.ui.prefs.Language
import com.floris.android.ui.prefs.LocalLanguage
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.t
import com.floris.android.ui.readingViewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File

class ReadingViewModel(
    private val repository: FlorisRepository,
    private val strings: StringResolver,
) : ViewModel() {

    data class ReaderState(
        val title: String = "",
        val action: String = "",
        val content: String = "",
        val streaming: Boolean = false,
        val error: String? = null,
        val storageKey: String? = null,
        val sourceText: String = "",
        val saved: Boolean = false,
    )

    data class UiState(
        val searching: Boolean = false,
        val results: List<Paper> = emptyList(),
        val searched: Boolean = false,
        val library: FlorisRepository.Library = FlorisRepository.Library(),
        val loadingLibrary: Boolean = true,
        val uploading: Boolean = false,
        val savingPaperId: String? = null,
        val reader: ReaderState? = null,
        val openingItemId: String? = null,
        val openFilePath: String? = null,
        val error: String? = null,
        val access: SkillAccess = SkillAccess(READING_SKILL_ID, SkillAccessStatus.Loading),
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private var readerJob: Job? = null

    init {
        viewModelScope.launch {
            repository.skillAccessFlow.collect { projection ->
                val access = projection.access(READING_SKILL_ID)
                val becameAvailable = access.available && !_state.value.access.available
                _state.update {
                    it.copy(
                        access = access,
                        loadingLibrary = if (access.available) it.loadingLibrary else false,
                    )
                }
                if (becameAvailable) loadLibrary()
            }
        }
        viewModelScope.launch {
            runCatching { repository.ensureSkillAccess(repository.activeConversationId()) }
        }
    }

    fun search(topic: String) {
        if (topic.isBlank() || !_state.value.access.available) return
        _state.update { it.copy(searching = true, error = null) }
        viewModelScope.launch {
            runCatching { repository.searchPapers(topic) }
                .onSuccess { papers ->
                    _state.update { it.copy(searching = false, results = papers, searched = true) }
                }
                .onFailure {
                _state.update {
                    it.copy(
                        searching = false,
                        searched = true,
                        error = strings.get(StringKey.ReadingSearchFailed),
                    )
                }
                }
        }
    }

    fun loadLibrary() {
        if (!_state.value.access.available) return
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

    fun upload(uri: Uri, filename: String) {
        if (_state.value.uploading || !_state.value.access.available) return
        _state.update { it.copy(uploading = true, error = null) }
        viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching {
                repository.uploadReadingDocument(conversationId, uri, filename)
            }.onSuccess {
                _state.update { it.copy(uploading = false) }
                loadLibrary()
            }.onFailure { error ->
                _state.update {
                    it.copy(uploading = false, error = strings.get(StringKey.ReadingUploadFailed))
                }
            }
        }
    }

    fun save(paper: Paper) {
        if (!_state.value.access.available) return
        val id = paper.arxiv_id ?: paper.title
        _state.update { it.copy(savingPaperId = id, error = null) }
        viewModelScope.launch {
            runCatching { repository.savePaper(paper) }
                .onSuccess {
                    _state.update { it.copy(savingPaperId = null) }
                    loadLibrary()
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            savingPaperId = null,
                            error = strings.get(StringKey.ReadingSaveFailed),
                        )
                    }
                }
        }
    }

    fun deleteLibraryItem(id: String) {
        viewModelScope.launch {
            runCatching { repository.deleteReadingItem(id) }
                .onSuccess { loadLibrary() }
                .onFailure { error ->
                    _state.update { it.copy(error = strings.get(StringKey.ReadingDeleteFailed)) }
                }
        }
    }

    fun updateAutoOrganize(enabled: Boolean) {
        val before = _state.value.library
        _state.update { it.copy(library = it.library.copy(autoOrganize = enabled)) }
        viewModelScope.launch {
            runCatching { repository.updateReadingSettings(enabled) }
                .onFailure {
                    _state.update {
                        it.copy(library = before, error = strings.get(StringKey.ReadingOperationFailed))
                    }
                }
        }
    }

    fun createFolder(name: String) = mutateLibrary { repository.createReadingFolder(name) }

    fun renameFolder(folderId: String, name: String) =
        mutateLibrary { repository.renameReadingFolder(folderId, name) }

    fun deleteFolder(folderId: String) = mutateLibrary { repository.deleteReadingFolder(folderId) }

    fun moveItem(itemId: String, folderId: String?) =
        mutateLibrary { repository.moveReadingItem(itemId, folderId) }

    private fun mutateLibrary(operation: suspend () -> Any) {
        viewModelScope.launch {
            runCatching { operation() }
                .onSuccess { loadLibrary() }
                .onFailure { error ->
                    _state.update { it.copy(error = strings.get(StringKey.ReadingOperationFailed)) }
                }
        }
    }

    fun openDocument(item: FlorisRepository.LibraryItem) {
        if (_state.value.openingItemId != null) return
        _state.update { it.copy(openingItemId = item.id, openFilePath = null) }
        viewModelScope.launch {
            runCatching {
                runCatching { repository.touchReadingItem(item.id) }
                repository.materializeReadingDocument(item)
            }.onSuccess { file ->
                _state.update { it.copy(openingItemId = null, openFilePath = file.absolutePath) }
            }.onFailure { error ->
                _state.update {
                    it.copy(
                        openingItemId = null,
                        error = strings.get(StringKey.ReadingOpenFailed),
                    )
                }
            }
        }
    }

    fun consumeOpenFile() = _state.update { it.copy(openFilePath = null) }

    fun runStoredReader(
        action: String,
        item: FlorisRepository.LibraryItem,
        language: Language,
        question: String? = null,
    ) {
        readerJob?.cancel()
        _state.update {
            it.copy(reader = ReaderState(
                title = item.title,
                action = action,
                streaming = true,
                storageKey = item.storageKey,
                sourceText = item.preview.orEmpty(),
            ))
        }
        readerJob = viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching {
                repository.streamReader(
                    conversationId = conversationId,
                    action = action,
                    text = "",
                    responseLanguage = language.tag,
                    fileId = item.fileId,
                    question = question,
                ).collect { chunk ->
                    when (chunk) {
                        is ReaderChunk.Delta -> _state.update { state ->
                            state.copy(reader = state.reader?.copy(
                                content = state.reader.content + chunk.text,
                            ))
                        }
                        is ReaderChunk.Error -> _state.update { state ->
                            state.copy(reader = state.reader?.copy(
                                streaming = false,
                                error = chunk.message.ifBlank { strings.get(StringKey.ReadingRunFailed) },
                            ))
                        }
                        ReaderChunk.Done, ReaderChunk.Ignored -> Unit
                    }
                }
            }.onFailure { error ->
                _state.update { state ->
                    state.copy(reader = state.reader?.copy(
                        streaming = false,
                        error = strings.get(StringKey.ReadingRunFailed),
                    ))
                }
            }
            _state.update { state -> state.copy(reader = state.reader?.copy(streaming = false)) }
        }
    }

    fun saveReaderResult() {
        val reader = _state.value.reader ?: return
        val storageKey = reader.storageKey ?: return
        if (reader.streaming || reader.content.isBlank() || reader.saved) return
        viewModelScope.launch {
            runCatching {
                repository.saveAssistantResult(
                    storageKey = storageKey,
                    action = reader.action,
                    title = reader.title,
                    sourceText = reader.sourceText,
                    content = reader.content,
                )
            }.onSuccess {
                _state.update { it.copy(reader = it.reader?.copy(saved = true)) }
                loadLibrary()
            }.onFailure { error ->
                _state.update {
                    it.copy(
                        reader = it.reader?.copy(error = strings.get(StringKey.ReadingSaveFailed)),
                    )
                }
            }
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
                            s.copy(reader = s.reader?.copy(
                                streaming = false,
                                error = chunk.message.ifBlank { strings.get(StringKey.ReadingRunFailed) },
                            ))
                        }
                        ReaderChunk.Done, ReaderChunk.Ignored -> Unit
                    }
                }
            }.onFailure { error ->
                _state.update { s ->
                    s.copy(
                        reader = s.reader?.copy(
                            streaming = false,
                            error = strings.get(StringKey.ReadingRunFailed),
                        ),
                    )
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
fun ReadingScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onBack: () -> Unit = {},
    onRequestLogin: () -> Unit = {},
    onOpenSkills: () -> Unit = {},
) {
    val viewModel: ReadingViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "reading",
        factory = container.readingViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()

    if (!state.access.available) {
        Column(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).statusBarsPadding(),
        ) {
            Row(
                Modifier.padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconPill(
                    icon = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = t(StringKey.Back),
                    onClick = onBack,
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    t(StringKey.ReadingTitle),
                    style = MaterialTheme.typography.headlineMedium,
                )
            }
            Box(Modifier.padding(horizontal = 16.dp)) {
                SkillAccessNotice(state.access, onRequestLogin, onOpenSkills)
            }
        }
        return
    }
    val language = LocalLanguage.current
    val context = LocalContext.current
    var query by remember { mutableStateOf("") }
    var selectedFolder by remember { mutableStateOf<String?>(null) }
    var folderEditor by remember { mutableStateOf<FlorisRepository.LibraryFolder?>(null) }
    var creatingFolder by remember { mutableStateOf(false) }
    var folderName by remember { mutableStateOf("") }
    var movingItem by remember { mutableStateOf<FlorisRepository.LibraryItem?>(null) }
    var questionItem by remember { mutableStateOf<FlorisRepository.LibraryItem?>(null) }
    var question by remember { mutableStateOf("") }
    val pickDocument = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri?.let {
            runCatching {
                context.contentResolver.takePersistableUriPermission(
                    it,
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            viewModel.upload(it, displayName(context, it))
        }
    }

    LaunchedEffect(state.openFilePath) {
        val path = state.openFilePath ?: return@LaunchedEffect
        runCatching {
            val uri = FileProvider.getUriForFile(
                context,
                "${BuildConfig.APPLICATION_ID}.files",
                File(path),
            )
            context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/pdf")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        }
        viewModel.consumeOpenFile()
    }

    if (creatingFolder || folderEditor != null) {
        val editing = folderEditor
        AlertDialog(
            onDismissRequest = {
                creatingFolder = false
                folderEditor = null
            },
            title = {
                Text(t(if (editing == null) StringKey.ReadingFolderNew else StringKey.ReadingFolderRename))
            },
            text = {
                OutlinedTextField(
                    value = folderName,
                    onValueChange = { folderName = it.take(48) },
                    singleLine = true,
                    label = { Text(t(StringKey.ReadingFolderNew)) },
                )
            },
            confirmButton = {
                TextButton(
                    enabled = folderName.isNotBlank(),
                    onClick = {
                        if (editing == null) viewModel.createFolder(folderName)
                        else viewModel.renameFolder(editing.id, folderName)
                        creatingFolder = false
                        folderEditor = null
                    },
                ) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = {
                    creatingFolder = false
                    folderEditor = null
                }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    movingItem?.let { item ->
        AlertDialog(
            onDismissRequest = { movingItem = null },
            title = { Text(t(StringKey.ReadingMove)) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    FolderChoice(t(StringKey.ReadingAll)) {
                        viewModel.moveItem(item.id, null)
                        movingItem = null
                    }
                    state.library.folders.forEach { folder ->
                        FolderChoice(folder.name.ifBlank { t(StringKey.ReadingUntitledFolder) }) {
                            viewModel.moveItem(item.id, folder.id)
                            movingItem = null
                        }
                    }
                }
            },
            confirmButton = {},
            dismissButton = {
                TextButton(onClick = { movingItem = null }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    questionItem?.let { item ->
        AlertDialog(
            onDismissRequest = { questionItem = null },
            title = { Text(t(StringKey.ReadingAsk)) },
            text = {
                OutlinedTextField(
                    value = question,
                    onValueChange = { question = it },
                    label = { Text(t(StringKey.ReadingAskHint)) },
                    minLines = 2,
                )
            },
            confirmButton = {
                TextButton(
                    enabled = question.isNotBlank(),
                    onClick = {
                        viewModel.runStoredReader("qa", item, language, question.trim())
                        questionItem = null
                    },
                ) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { questionItem = null }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        // 标题区
        Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 6.dp, bottom = 10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconPill(
                    icon = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = t(StringKey.Back),
                    onClick = onBack,
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    t(StringKey.ReadingTitle),
                    style = MaterialTheme.typography.headlineMedium,
                    modifier = Modifier.weight(1f),
                )
                PillButton(
                    text = if (state.uploading) t(StringKey.ReadingUploading)
                    else t(StringKey.ReadingUpload),
                    leadingIcon = Icons.Outlined.CloudUpload,
                    enabled = !state.uploading,
                    compact = true,
                    onClick = { pickDocument.launch(arrayOf("application/pdf")) },
                )
            }
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
            state.error?.let { error ->
                item(key = "error") {
                    Text(
                        error,
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 4.dp),
                    )
                }
            }
            if (state.searching) {
                item { InlineLoading() }
            }

            if (state.results.isNotEmpty()) {
                item(key = "results-header") {
                    SectionHeader(t(StringKey.ReadingResults, state.results.size))
                }
                items(state.results, key = { it.arxiv_id ?: it.title }) { paper ->
                    AnimateIn(0) {
                        PaperCard(
                            paper = paper,
                            saving = state.savingPaperId == (paper.arxiv_id ?: paper.title),
                            onSave = { viewModel.save(paper) },
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
                        Text(
                            t(StringKey.ReadingAutoOrganize),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.width(5.dp))
                        FlorisSwitch(
                            checked = library.autoOrganize,
                            onCheckedChange = viewModel::updateAutoOrganize,
                        )
                        IconPill(
                            icon = Icons.Default.Add,
                            contentDescription = t(StringKey.ReadingFolderNew),
                            onClick = {
                                folderName = ""
                                creatingFolder = true
                            },
                            size = 34.dp,
                            iconSize = 18.dp,
                        )
                    }
                }
                if (library.folders.isNotEmpty()) {
                    item(key = "folders") {
                        LazyRow(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            item {
                                FolderChip(
                                    name = t(StringKey.ReadingAll),
                                    selected = selectedFolder == null,
                                    onClick = { selectedFolder = null },
                                )
                            }
                            items(library.folders, key = { it.id }) { folder ->
                                FolderChip(
                                    name = folder.name.ifBlank { t(StringKey.ReadingUntitledFolder) },
                                    selected = selectedFolder == folder.id,
                                    onClick = { selectedFolder = folder.id },
                                )
                            }
                        }
                    }
                    selectedFolder?.let { folderId ->
                        library.folders.firstOrNull { it.id == folderId }?.let { folder ->
                            item(key = "folder-actions-$folderId") {
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    PillButton(
                                        text = t(StringKey.ReadingFolderRename),
                                        leadingIcon = Icons.Default.Edit,
                                        compact = true,
                                        style = PillStyle.Ghost,
                                        onClick = {
                                            folderEditor = folder
                                            folderName = folder.name
                                        },
                                    )
                                    if (!folder.automatic) {
                                        PillButton(
                                            text = t(StringKey.ReadingFolderDelete),
                                            leadingIcon = Icons.Outlined.DeleteOutline,
                                            compact = true,
                                            style = PillStyle.Ghost,
                                            onClick = {
                                                viewModel.deleteFolder(folder.id)
                                                selectedFolder = null
                                            },
                                        )
                                    }
                                }
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
                                        item.title.ifBlank { t(StringKey.ReadingUntitledDocument) },
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
                                    StatusChip(t(StringKey.ReadingPaper), MaterialTheme.colorScheme.secondary)
                                }
                            }
                            LazyRow(
                                Modifier.padding(start = 42.dp, end = 10.dp, bottom = 10.dp),
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                item {
                                    PillButton(
                                        text = if (state.openingItemId == item.id) t(StringKey.ReadingOpening)
                                        else t(StringKey.ReadingOpen),
                                        leadingIcon = Icons.AutoMirrored.Filled.OpenInNew,
                                        enabled = state.openingItemId == null,
                                        compact = true,
                                        style = PillStyle.Tonal,
                                        onClick = { viewModel.openDocument(item) },
                                    )
                                }
                                item { ReaderAction(t(StringKey.ReadingSummarize)) { viewModel.runStoredReader("summarize", item, language) } }
                                item { ReaderAction(t(StringKey.ReadingTranslate)) { viewModel.runStoredReader("translate", item, language) } }
                                item { ReaderAction(t(StringKey.ReadingAnalyze)) { viewModel.runStoredReader("analyze", item, language) } }
                                item {
                                    ReaderAction(t(StringKey.ReadingAsk)) {
                                        question = ""
                                        questionItem = item
                                    }
                                }
                                item {
                                    PillButton(
                                        text = t(StringKey.ReadingMove),
                                        leadingIcon = Icons.AutoMirrored.Filled.DriveFileMove,
                                        compact = true,
                                        style = PillStyle.Ghost,
                                        onClick = { movingItem = item },
                                    )
                                }
                                item {
                                    PillButton(
                                        text = t(StringKey.ReadingDelete),
                                        leadingIcon = Icons.Outlined.DeleteOutline,
                                        compact = true,
                                        style = PillStyle.Ghost,
                                        onClick = { viewModel.deleteLibraryItem(item.id) },
                                    )
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
                        when (reader.action) {
                            "translate", "full-translate" -> t(StringKey.ReadingTranslate)
                            "analyze" -> t(StringKey.ReadingAnalyze)
                            "qa" -> t(StringKey.ReadingAsk)
                            else -> t(StringKey.ReadingSummarize)
                        },
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
                if (!reader.streaming && reader.content.isNotBlank() && reader.storageKey != null) {
                    Spacer(Modifier.height(12.dp))
                    PillButton(
                        text = if (reader.saved) t(StringKey.ReadingSaved)
                        else t(StringKey.ReadingSaveResult),
                        enabled = !reader.saved,
                        onClick = viewModel::saveReaderResult,
                    )
                }
            }
        }
    }
}

private const val READING_SKILL_ID = "paper-reading"

@Composable
private fun ReaderAction(text: String, onClick: () -> Unit) {
    PillButton(
        text = text,
        compact = true,
        style = PillStyle.Ghost,
        onClick = onClick,
    )
}

@Composable
private fun FolderChoice(name: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .pressable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.Folder, null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(9.dp))
        Text(name, style = MaterialTheme.typography.bodySmall)
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
private fun PaperCard(
    paper: Paper,
    saving: Boolean,
    onSave: () -> Unit,
    onSummarize: () -> Unit,
    onTranslate: () -> Unit,
) {
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
                    paper.citations?.let { t(StringKey.PaperCited, it) },
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
                    text = if (saving) t(StringKey.Loading) else t(StringKey.ReadingSave),
                    onClick = onSave,
                    enabled = !saving,
                    style = PillStyle.Ghost,
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

private fun displayName(context: android.content.Context, uri: Uri): String {
    val queried = context.contentResolver.query(
        uri,
        arrayOf(OpenableColumns.DISPLAY_NAME),
        null,
        null,
        null,
    )?.use { cursor ->
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
    }
    return queried?.takeIf { it.isNotBlank() } ?: "document.pdf"
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
