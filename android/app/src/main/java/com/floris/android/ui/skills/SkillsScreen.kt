package com.floris.android.ui.skills

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.components.CatIconPill
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.asString
import com.floris.android.core.data.obj
import com.floris.android.core.model.Skill
import com.floris.android.core.model.SkillUploadRecord
import com.floris.android.core.model.SkillConnectionState
import com.floris.android.core.model.SkillComponentAction
import com.floris.android.core.model.SkillComponentApi
import com.floris.android.core.model.UserSkill
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.FlorisSwitch
import com.floris.android.ui.components.GuestNotice
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.papers.SearchField
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.Language
import com.floris.android.ui.prefs.LocalLanguage
import com.floris.android.ui.prefs.userFacingError
import com.floris.android.ui.prefs.t
import com.floris.android.ui.skillsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SkillsViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val skills: List<Skill> = emptyList(),
        val enabledIds: Set<String> = emptySet(),
        val busyId: String? = null,
        val error: String? = null,
        /** 游客：只有契约里的 guest_skill_ids 可用，其余需登录。 */
        val isGuest: Boolean = false,
        val uploads: List<SkillUploadRecord> = emptyList(),
        val userSkills: List<UserSkill> = emptyList(),
        val connections: Map<String, SkillConnectionState> = emptyMap(),
        val componentApi: SkillComponentApi? = null,
        val importing: Boolean = false,
    )

    private val _state = MutableStateFlow(UiState(isGuest = authManager.isGuest))
    val state = _state.asStateFlow()

    init {
        refresh()
        // Tab 页 ViewModel 是 Activity 作用域，登录/登出后不会重建。
        // 必须订阅 AuthState，否则登录成功后这里仍是旧的游客态。
        viewModelScope.launch {
            authManager.state.collect { auth ->
                val guest = (auth as? AuthState.SignedIn)?.identity?.auth_type == "guest"
                val changed = guest != _state.value.isGuest
                _state.value = _state.value.copy(isGuest = guest)
                // 身份变了，可用技能范围也变了，重新拉一次目录。
                if (changed) refresh()
            }
        }
    }

    /**
     * 拉取技能目录。
     *
     * @param force true 表示用户主动下拉/身份变化，必须走网络；
     *              false 表示进入页面，已有数据就直接用缓存，不再转圈。
     */
    fun refresh(force: Boolean = true) {
        val guest = (authManager.state.value as? AuthState.SignedIn)
            ?.identity?.auth_type == "guest"
        // 已有数据且不是强制刷新：直接沿用，避免每次切页都空屏加载。
        if (!force && _state.value.skills.isNotEmpty()) {
            _state.value = _state.value.copy(isGuest = guest, loading = false)
            return
        }
        if (_state.value.loading && _state.value.skills.isNotEmpty()) return
        _state.value = _state.value.copy(
            loading = _state.value.skills.isEmpty(),
            error = null,
            isGuest = guest,
        )
        viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching {
                val catalog = repository.skillCatalog(conversationId)
                val uploads = if (guest) emptyList() else repository.listSkillUploads()
                catalog to uploads
            }.onSuccess { (catalog, uploadObjects) ->
                val enabled = catalog.skills.mapNotNull { skill ->
                    val pref = catalog.preferences[skill.id]
                    val isEnabled = skill.enabled
                        ?: skill.locked?.takeIf { it }
                        ?: pref
                        ?: true
                    if (isEnabled) skill.id else null
                }.toSet()
                _state.value = UiState(
                    loading = false,
                    skills = catalog.skills,
                    enabledIds = enabled,
                    isGuest = guest,
                    uploads = uploadObjects,
                    userSkills = catalog.user_skills,
                    connections = catalog.connections,
                    componentApi = catalog.component_api,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    loading = false,
                    error = strings.get(StringKey.SkillsMarketFailed),
                )
            }
        }
    }

    fun toggle(skill: Skill, enabled: Boolean) {
        if (_state.value.busyId != null) return
        // 游客越权由后端 403 拦截，这里先在客户端明确提示，避免无谓往返。
        if (skill.eligible == false) {
            _state.value = _state.value.copy(error = strings.get(StringKey.SkillsLoginHint))
            return
        }
        _state.value = _state.value.copy(busyId = skill.id)
        viewModelScope.launch {
            runCatching {
                repository.setSkillEnabled(repository.activeConversationId(), skill.id, enabled)
            }.onSuccess {
                _state.value = _state.value.copy(
                    busyId = null,
                    enabledIds = if (enabled) _state.value.enabledIds + skill.id
                    else _state.value.enabledIds - skill.id,
                )
            }.onFailure { error ->
                _state.value = _state.value.copy(
                    busyId = null,
                    error = strings.userFacingError(error, StringKey.SkillsOperationFailed),
                )
            }
        }
    }

    fun importUrl(url: String) = importOperation {
        val resolved = repository.resolveSkillUrl(url).obj("skill")
            ?: error(strings.get(StringKey.SkillsImportFailed))
        repository.installUserSkill(resolved)
    }

    fun importText(name: String, description: String, instructions: String) = importOperation {
        repository.installUserSkillText(name, description, instructions)
    }

    fun importFile(uri: Uri, filename: String) = importOperation {
        repository.importUserSkillFile(uri, filename)
    }

    private fun importOperation(block: suspend () -> JsonObject) {
        if (_state.value.importing) return
        _state.update { it.copy(importing = true, error = null) }
        viewModelScope.launch {
            runCatching { block() }
                .onSuccess {
                    _state.update { it.copy(importing = false) }
                    refresh(force = true)
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            importing = false,
                            error = strings.userFacingError(error, StringKey.SkillsImportFailed),
                        )
                    }
                }
        }
    }

    fun setUserSkillEnabled(skill: UserSkill, enabled: Boolean) {
        viewModelScope.launch {
            runCatching { repository.setUserSkillEnabled(skill.id, enabled) }
                .onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(error = strings.userFacingError(error, StringKey.SkillsOperationFailed))
                    }
                }
        }
    }

    fun removeUserSkill(skill: UserSkill) {
        viewModelScope.launch {
            runCatching { repository.removeUserSkill(skill.id) }
                .onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(error = strings.userFacingError(error, StringKey.SkillsOperationFailed))
                    }
                }
        }
    }

    fun requestReview(upload: SkillUploadRecord) {
        if (_state.value.busyId != null) return
        _state.update { it.copy(busyId = upload.id, error = null) }
        viewModelScope.launch {
            runCatching { repository.requestSkillReview(upload.id) }
                .onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            busyId = null,
                            error = strings.userFacingError(error, StringKey.SkillsSubmitFailed),
                        )
                    }
                }
        }
    }

    fun publishUserSkill(skill: UserSkill) {
        if (_state.value.busyId != null) return
        _state.update { it.copy(busyId = skill.id, error = null) }
        viewModelScope.launch {
            runCatching {
                repository.publishDeclarativeSkill(
                    sourceSkillId = skill.id,
                    name = skill.name,
                    description = skill.description,
                    instructions = skill.instructions,
                    installedAt = skill.installed_at,
                )
            }.onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            busyId = null,
                            error = strings.userFacingError(error, StringKey.SkillsSubmitFailed),
                        )
                    }
                }
        }
    }

    fun connect(skill: Skill, token: String) {
        if (_state.value.busyId != null || token.isBlank()) return
        _state.update { it.copy(busyId = skill.id, error = null) }
        viewModelScope.launch {
            runCatching {
                repository.configureSkillConnection(
                    repository.activeConversationId(), skill.id, token.trim(),
                )
            }.onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            busyId = null,
                            error = strings.userFacingError(error, StringKey.SkillsConnectFailed),
                        )
                    }
                }
        }
    }

    fun disconnect(skill: Skill) {
        if (_state.value.busyId != null) return
        _state.update { it.copy(busyId = skill.id, error = null) }
        viewModelScope.launch {
            runCatching {
                repository.disconnectSkillConnection(repository.activeConversationId(), skill.id)
            }.onSuccess { refresh(force = true) }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            busyId = null,
                            error = strings.userFacingError(error, StringKey.SkillsDisconnectFailed),
                        )
                    }
                }
        }
    }

    fun consumeError() { _state.value = _state.value.copy(error = null) }
}

/** Eligibility is the backend entitlement projection; Android never copies its rules. */
private val Skill.availableToGuest: Boolean get() = eligible != false

private val categoryOrder =
    listOf("foundation", "knowledge", "creative", "productivity", "location", "other")

@Composable
private fun categoryLabel(category: String): String = when (category) {
    "foundation" -> t(StringKey.SkillCategoryFoundation)
    "knowledge" -> t(StringKey.SkillCategoryKnowledge)
    "creative" -> t(StringKey.SkillCategoryCreative)
    "productivity" -> t(StringKey.SkillCategoryProductivity)
    "location" -> t(StringKey.SkillCategoryLocation)
    else -> t(StringKey.SkillCategoryOther)
}

private fun skillIcon(category: String?): ImageVector = when (category) {
    "knowledge" -> Icons.Default.Search
    "creative" -> Icons.Default.Edit
    "productivity" -> Icons.Default.DateRange
    "location" -> Icons.Default.Place
    else -> Icons.Default.Build
}

@Composable
fun SkillsScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onBack: () -> Unit = {},
    onRequestLogin: () -> Unit = {},
) {
    val viewModel: SkillsViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "skills",
        factory = container.skillsViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    val language = LocalLanguage.current
    var query by remember { mutableStateOf("") }
    var showImport by remember { mutableStateOf(false) }
    val pickSkill = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri?.let {
            viewModel.importFile(it, skillDisplayName(context, it))
            showImport = false
        }
    }
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.error) {
        state.error?.let { snackbar.showSnackbar(it); viewModel.consumeError() }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 6.dp, bottom = 10.dp)) {
            Text(
                t(StringKey.SkillsEyebrow),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                CatIconPill(
                    resId = R.drawable.ic_back,
                    contentDescription = t(StringKey.Back),
                    onClick = onBack,
                )
                Spacer(Modifier.width(2.dp))
                Text(
                    t(StringKey.SkillsTitle),
                    style = MaterialTheme.typography.headlineMedium,
                    modifier = Modifier.weight(1f),
                )
                if (!state.isGuest) {
                    PillButton(
                        text = t(StringKey.SkillsAdd),
                        leadingIcon = Icons.Default.Add,
                        compact = true,
                        enabled = !state.importing,
                        onClick = { showImport = true },
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    t(StringKey.SkillsSubtitle),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                StatusChip(
                    t(StringKey.SkillsEnabledCount, state.enabledIds.size, state.skills.size),
                    MaterialTheme.colorScheme.primary,
                )
            }
            if (state.isGuest) {
                Spacer(Modifier.height(10.dp))
                // 游客：直接给登录入口（和日程/地点一致），不再放“游客可使用”说明。
                GuestNotice(
                    text = t(StringKey.SkillsLoginHint),
                    actionText = t(StringKey.GuestSignInCta),
                    onAction = onRequestLogin,
                )
            }
            Spacer(Modifier.height(12.dp))
            SearchField(
                value = query,
                onValueChange = { query = it },
                hint = t(StringKey.SkillsSearchHint),
                onSearch = {},
            )
        }

        Box(Modifier.weight(1f)) {
            when {
                state.loading -> InlineLoading()
                state.skills.isEmpty() -> EmptyState(
                    t(StringKey.SkillsEmptyTitle), t(StringKey.SkillsEmptyBody),
                )
                else -> {
                    val filtered = state.skills.filter { skill ->
                        query.isBlank() ||
                            skill.localizedName(language).contains(query, true) ||
                            skill.localizedDescription(language).contains(query, true)
                    }
                    val grouped = filtered.groupBy { it.category ?: "other" }
                        .toList()
                        .sortedBy { (category) ->
                            categoryOrder.indexOf(category).let { if (it < 0) 99 else it }
                        }
                    LazyColumn(
                        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        if (state.userSkills.isNotEmpty()) {
                            item(key = "user-skills-header") {
                                SectionHeader("${t(StringKey.SkillsPrivate)} · ${state.userSkills.size}")
                            }
                            items(state.userSkills, key = { "user-${it.id}" }) { skill ->
                                UserSkillCard(
                                    skill = skill,
                                    busy = state.busyId == skill.id,
                                    onToggle = { viewModel.setUserSkillEnabled(skill, it) },
                                    onRemove = { viewModel.removeUserSkill(skill) },
                                    onPublish = { viewModel.publishUserSkill(skill) },
                                )
                            }
                        }
                        if (state.uploads.isNotEmpty()) {
                            item(key = "skill-uploads-header") {
                                SectionHeader("${t(StringKey.SkillsUploads)} · ${state.uploads.size}")
                            }
                            items(state.uploads, key = { "upload-${it.id}" }) { upload ->
                                SkillUploadCard(
                                    upload = upload,
                                    busy = state.busyId == upload.id,
                                    onPublish = { viewModel.requestReview(upload) },
                                )
                            }
                        }
                        grouped.forEach { (category, skills) ->
                            item(key = "header-$category") {
                                SectionHeader("${categoryLabel(category)} · ${skills.size}")
                            }
                            items(skills, key = { it.id }) { skill ->
                                AnimateIn(0) {
                                    SkillCard(
                                        skill = skill,
                                        enabled = skill.id in state.enabledIds,
                                        busy = state.busyId == skill.id,
                                        missing = skill.requires.filter { it !in state.enabledIds },
                                        needsLogin = state.isGuest && !skill.availableToGuest,
                                        connection = state.connections[skill.id],
                                        language = language,
                                        onToggle = { enabled -> viewModel.toggle(skill, enabled) },
                                        onConnect = { token -> viewModel.connect(skill, token) },
                                        onDisconnect = { viewModel.disconnect(skill) },
                                    )
                                }
                            }
                        }
                    }
                }
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter))
        }
    }

    if (showImport) {
        SkillImportDialog(
            busy = state.importing,
            onDismiss = { showImport = false },
            onChooseFile = {
                pickSkill.launch(arrayOf("text/markdown", "application/json", "application/zip"))
            },
            onImportUrl = {
                viewModel.importUrl(it)
                showImport = false
            },
            onImportText = { name, description, instructions ->
                viewModel.importText(name, description, instructions)
                showImport = false
            },
        )
    }
}

@Composable
private fun ComponentApiDialog(api: SkillComponentApi, onDismiss: () -> Unit) {
    val language = LocalLanguage.current
    val clipboard = LocalClipboardManager.current
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(t(StringKey.SkillsComponentApi)) },
        text = {
            LazyColumn(
                Modifier.fillMaxWidth().heightIn(max = 560.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    Text(
                        t(StringKey.SkillsComponentApiHint),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        t(StringKey.SkillsComponentApiVersion, api.version, api.actions.size),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                items(api.actions, key = { "component-${it.id}" }) { action ->
                    val example = actionExample(action)
                    FlorisCard {
                        Column(Modifier.padding(14.dp)) {
                            Text(
                                action.name.localized(language).ifBlank { action.id },
                                style = MaterialTheme.typography.titleMedium,
                            )
                            Text(
                                action.id,
                                style = MaterialTheme.typography.labelMedium.copy(
                                    fontFamily = FontFamily.Monospace,
                                ),
                                color = MaterialTheme.colorScheme.primary,
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                action.description_i18n.localized(language)
                                    .ifBlank { action.description },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            if (action.input.isNotEmpty()) {
                                Spacer(Modifier.height(10.dp))
                                Text(
                                    t(StringKey.SkillsComponentApiParameters),
                                    style = MaterialTheme.typography.labelLarge,
                                )
                                action.input.forEach { (name, type) ->
                                    Row(
                                        Modifier.fillMaxWidth().padding(top = 5.dp),
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    ) {
                                        Text(
                                            name,
                                            modifier = Modifier.weight(1f),
                                            style = MaterialTheme.typography.labelMedium.copy(
                                                fontFamily = FontFamily.Monospace,
                                            ),
                                        )
                                        Text(type, style = MaterialTheme.typography.labelMedium)
                                        Text(
                                            if (name in action.required) t(StringKey.Yes) else t(StringKey.No),
                                            style = MaterialTheme.typography.labelMedium,
                                            color = if (name in action.required) {
                                                MaterialTheme.colorScheme.primary
                                            } else MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                }
                            }
                            Spacer(Modifier.height(10.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    t(StringKey.SkillsComponentApiExample),
                                    modifier = Modifier.weight(1f),
                                    style = MaterialTheme.typography.labelLarge,
                                )
                                TextButton(
                                    onClick = { clipboard.setText(AnnotatedString(example)) },
                                ) { Text(t(StringKey.CopyPlainText)) }
                            }
                            SelectionContainer {
                                Text(
                                    example,
                                    modifier = Modifier.fillMaxWidth()
                                        .clip(RoundedCornerShape(10.dp))
                                        .background(
                                            MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
                                        )
                                        .padding(10.dp),
                                    style = MaterialTheme.typography.labelSmall.copy(
                                        fontFamily = FontFamily.Monospace,
                                    ),
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(t(StringKey.Close)) } },
    )
}

private val prettyJson = Json { prettyPrint = true }

private fun actionExample(action: SkillComponentAction): String {
    val payload = JsonObject(action.input.mapValues { (_, type) -> exampleValue(type) })
    return prettyJson.encodeToString(
        JsonObject.serializer(),
        buildJsonObject {
            put("action", action.id)
            put("payload", payload)
        },
    )
}

private fun exampleValue(type: String): JsonElement = when {
    type.endsWith("[]") -> JsonArray(emptyList())
    type.contains("object") || type.contains("clarification") -> JsonObject(emptyMap())
    type.contains("integer") || type.contains("number") -> JsonPrimitive(0)
    type.contains("boolean") -> JsonPrimitive(false)
    else -> JsonPrimitive("<$type>")
}

@Composable
private fun SkillImportDialog(
    busy: Boolean,
    onDismiss: () -> Unit,
    onChooseFile: () -> Unit,
    onImportUrl: (String) -> Unit,
    onImportText: (String, String, String) -> Unit,
) {
    var url by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var instructions by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(t(StringKey.SkillsImportTitle)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ImportField(url, { url = it }, t(StringKey.SkillsImportUrl))
                Text("—", color = MaterialTheme.colorScheme.onSurfaceVariant)
                ImportField(name, { name = it }, t(StringKey.SkillsImportName))
                ImportField(description, { description = it }, t(StringKey.SkillsImportDescription))
                ImportField(
                    instructions,
                    { instructions = it },
                    t(StringKey.SkillsImportInstructions),
                    singleLine = false,
                )
                PillButton(
                    text = t(StringKey.SkillsChooseFile),
                    onClick = onChooseFile,
                    style = PillStyle.Tonal,
                    enabled = !busy,
                    compact = true,
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && (url.isNotBlank() || instructions.isNotBlank()),
                onClick = {
                    if (url.isNotBlank()) onImportUrl(url)
                    else onImportText(name, description, instructions)
                },
            ) { Text(t(StringKey.SkillsImport)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(t(StringKey.Cancel)) }
        },
    )
}

@Composable
private fun ImportField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    singleLine: Boolean = true,
) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (value.isEmpty()) {
            Text(hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = singleLine,
            maxLines = if (singleLine) 1 else 6,
            textStyle = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun UserSkillCard(
    skill: UserSkill,
    busy: Boolean,
    onToggle: (Boolean) -> Unit,
    onRemove: () -> Unit,
    onPublish: () -> Unit,
) {
    FlorisCard {
        Column(Modifier.padding(14.dp)) {
          Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(skill.name, style = MaterialTheme.typography.titleMedium)
                if (skill.description.isNotBlank()) {
                    Text(
                        skill.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Text(
                    skill.source_type,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(onClick = onRemove) { Text(t(StringKey.SkillsRemove)) }
            FlorisSwitch(checked = skill.enabled, onCheckedChange = onToggle)
          }
          if (skill.review_status !in setOf("pending_review", "approved")) {
              Spacer(Modifier.height(8.dp))
              PillButton(
                  text = if (busy) t(StringKey.Loading) else t(StringKey.SkillsSubmitReview),
                  onClick = onPublish,
                  enabled = !busy,
                  compact = true,
                  style = PillStyle.Tonal,
              )
          } else {
              Spacer(Modifier.height(8.dp))
              StatusChip(skillReviewLabel(skill.review_status), skillReviewColor(skill.review_status))
          }
        }
    }
}

@Composable
private fun SkillUploadCard(
    upload: SkillUploadRecord,
    busy: Boolean,
    onPublish: () -> Unit,
) {
    FlorisCard {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(upload.name, style = MaterialTheme.typography.titleMedium)
                upload.description?.takeIf { it.isNotBlank() }?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.height(5.dp))
                StatusChip(skillReviewLabel(upload.review_status), skillReviewColor(upload.review_status))
            }
            if (upload.review_available && upload.review_status !in setOf("pending_review", "approved")) {
                Spacer(Modifier.width(8.dp))
                PillButton(
                    text = if (busy) t(StringKey.Loading) else t(StringKey.SkillsSubmitReview),
                    onClick = onPublish,
                    enabled = !busy,
                    compact = true,
                    style = PillStyle.Tonal,
                )
            }
        }
    }
}

@Composable
private fun skillReviewLabel(status: String): String = when (status) {
    "pending_review" -> t(StringKey.SkillsPendingReview)
    "approved" -> t(StringKey.SkillsApproved)
    "rejected" -> t(StringKey.SkillsRejected)
    else -> t(StringKey.SkillsStored)
}

@Composable
private fun skillReviewColor(status: String) = when (status) {
    "pending_review" -> MaterialTheme.colorScheme.secondary
    "approved" -> MaterialTheme.colorScheme.tertiary
    "rejected" -> MaterialTheme.colorScheme.error
    else -> MaterialTheme.colorScheme.onSurfaceVariant
}

private fun skillDisplayName(context: android.content.Context, uri: Uri): String =
    context.contentResolver.query(
        uri,
        arrayOf(OpenableColumns.DISPLAY_NAME),
        null,
        null,
        null,
    )?.use { cursor ->
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
    }?.takeIf { it.isNotBlank() } ?: "SKILL.md"

@Composable
private fun SkillCard(
    skill: Skill,
    enabled: Boolean,
    busy: Boolean,
    missing: List<String>,
    needsLogin: Boolean,
    connection: SkillConnectionState?,
    language: Language,
    onToggle: (Boolean) -> Unit,
    onConnect: (String) -> Unit,
    onDisconnect: () -> Unit,
) {
    var token by remember(skill.id) { mutableStateOf("") }
    FlorisCard {
        Column(Modifier.padding(14.dp).alpha(if (needsLogin) 0.5f else 1f)) {
        // 未登录不可用的技能整体压暗，一眼能分出哪些要登录。
        Row {
            Box(
                Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    skillIcon(skill.category), contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.size(20.dp),
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        skill.localizedName(language),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (needsLogin || skill.locked == true) {
                        Spacer(Modifier.width(5.dp))
                        Icon(
                            Icons.Default.Lock, contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                            modifier = Modifier.size(12.dp),
                        )
                    }
                }
                Text(
                    listOfNotNull(
                        (skill.publisher?.get("name")).asString(),
                        skill.version?.let { "v$it" },
                    ).joinToString(" · ").ifEmpty { t(StringKey.SkillsOfficial) },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    skill.localizedDescription(language),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (needsLogin) {
                        StatusChip(t(StringKey.SkillsLoginRequired), MaterialTheme.colorScheme.error)
                    }
                    if (skill.locked == true) {
                        StatusChip(t(StringKey.SkillsAlwaysOn), MaterialTheme.colorScheme.secondary)
                    }
                }
                if (skill.requires.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        t(StringKey.SkillsRequires, skill.requires.joinToString("、")),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (skill.conflicts.isNotEmpty()) {
                    Text(
                        t(StringKey.SkillsConflicts, skill.conflicts.joinToString("、")),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                if (skill.recommends.isNotEmpty()) {
                    Text(
                        t(StringKey.SkillsRecommends, skill.recommends.joinToString("、")),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (needsLogin) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        t(StringKey.SkillsLoginHint),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                } else if (missing.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        t(StringKey.SkillsRequires, missing.joinToString("、")),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.secondary,
                    )
                }
            }
            Spacer(Modifier.width(8.dp))
            FlorisSwitch(
                checked = enabled && !needsLogin,
                onCheckedChange = onToggle,
                enabled = !busy && !needsLogin && skill.locked != true,
            )
        }
        if (skill.external && enabled && !needsLogin && skill.credential?.kind == "token") {
            Spacer(Modifier.height(12.dp))
            val connected = connection?.configured == true || skill.configured
            if (connected) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(t(StringKey.SkillsConnected), MaterialTheme.colorScheme.tertiary)
                    Spacer(Modifier.weight(1f))
                    PillButton(
                        text = t(StringKey.SkillsDisconnect),
                        onClick = onDisconnect,
                        style = PillStyle.Danger,
                        compact = true,
                        enabled = !busy,
                    )
                }
            } else {
                val instructions = skill.credential.instructions.localized(language)
                if (instructions.isNotBlank()) {
                    Text(
                        instructions,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(8.dp))
                }
                Box(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    contentAlignment = Alignment.CenterStart,
                ) {
                    if (token.isEmpty()) {
                        Text(
                            t(StringKey.SkillsConnectionToken),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    BasicTextField(
                        value = token,
                        onValueChange = { token = it },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        textStyle = MaterialTheme.typography.bodySmall.copy(
                            color = MaterialTheme.colorScheme.onSurface,
                        ),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                Row(
                    Modifier.fillMaxWidth().padding(top = 8.dp),
                    horizontalArrangement = Arrangement.End,
                ) {
                    PillButton(
                        text = t(StringKey.SkillsConnect),
                        onClick = { onConnect(token) },
                        compact = true,
                        enabled = token.isNotBlank() && !busy,
                    )
                }
            }
        }
        }
    }
}

private fun Map<String, String>.localized(language: Language): String =
    this[language.tag]
        ?: (if (language in setOf(Language.CAT_CUTE, Language.CAT_COLD)) this["zh-CN"] else null)
        ?: this[if (language == Language.ZH_TW) "zh-TW" else language.tag]
        ?: this["en"]
        ?: this["zh-CN"]
        ?: this["zh"]
        ?: values.firstOrNull().orEmpty()

private fun Skill.localizedName(language: Language): String =
    name.localized(language).ifBlank { id }

private fun Skill.localizedDescription(language: Language): String =
    description.localized(language)
