package com.floris.android.ui.skills

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.asString
import com.floris.android.core.data.obj
import com.floris.android.core.model.Skill
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.FlorisSwitch
import com.floris.android.ui.components.GuestNotice
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.papers.SearchField
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import com.floris.android.ui.skillsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SkillsViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val skills: List<Skill> = emptyList(),
        val enabledIds: Set<String> = emptySet(),
        val busyId: String? = null,
        val error: String? = null,
        /** 游客：只有契约里的 guest_skill_ids 可用，其余需登录。 */
        val isGuest: Boolean = false,
    )

    private val _state = MutableStateFlow(UiState(isGuest = authManager.isGuest))
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(loading = true, error = null, isGuest = authManager.isGuest)
        viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching {
                val catalog = repository.skillCatalog(conversationId)
                val preferences = repository.intelligencePreferences(conversationId)
                catalog to preferences
            }.onSuccess { (catalog, intelligence) ->
                val prefs = intelligence.obj("preferences")?.obj("skills")
                val enabled = catalog.skills.mapNotNull { skill ->
                    val pref = prefs?.get(skill.id)?.asString()
                    val isEnabled = skill.enabled
                        ?: skill.locked?.takeIf { it }
                        ?: pref?.let { it != "false" }
                        ?: true
                    if (isEnabled) skill.id else null
                }.toSet()
                _state.value = UiState(
                    loading = false,
                    skills = catalog.skills,
                    enabledIds = enabled,
                    isGuest = authManager.isGuest,
                )
            }.onFailure {
                _state.value = _state.value.copy(loading = false, error = "技能市场加载失败")
            }
        }
    }

    fun toggle(skill: Skill, enabled: Boolean) {
        if (_state.value.busyId != null) return
        // 游客越权由后端 403 拦截，这里先在客户端明确提示，避免无谓往返。
        if (_state.value.isGuest && !skill.availableToGuest) {
            _state.value = _state.value.copy(error = "请先登录后使用此技能")
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
                    error = error.message?.takeIf { it.isNotBlank() } ?: "操作失败，请重试",
                )
            }
        }
    }

    fun consumeError() { _state.value = _state.value.copy(error = null) }
}

/**
 * 游客可用技能，取自 contracts/entitlements.v1.json 的 guest_skill_ids。
 * 与后端 auth/entitlements.js skillAccess() 判定保持一致。
 */
private val GUEST_SKILL_IDS = setOf("core", "proactive-agent")

private val Skill.availableToGuest: Boolean get() = id in GUEST_SKILL_IDS

private val categoryOrder =
    listOf("foundation", "knowledge", "creative", "productivity", "location", "other")

private val categoryLabels = mapOf(
    "foundation" to "基础能力",
    "knowledge" to "知识检索",
    "creative" to "创作",
    "productivity" to "效率",
    "location" to "位置服务",
    "other" to "其他",
)

private fun skillIcon(category: String?): ImageVector = when (category) {
    "knowledge" -> Icons.Default.Search
    "creative" -> Icons.Default.Edit
    "productivity" -> Icons.Default.DateRange
    "location" -> Icons.Default.Place
    else -> Icons.Default.Build
}

@Composable
fun SkillsScreen(container: AppContainer, owner: ViewModelStoreOwner? = null) {
    val viewModel: SkillsViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "skills",
        factory = container.skillsViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    var query by remember { mutableStateOf("") }
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
            Text(t(StringKey.SkillsTitle), style = MaterialTheme.typography.headlineMedium)
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
                GuestNotice(t(StringKey.SkillsGuestNotice))
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
                state.skills.isEmpty() -> EmptyState("暂无技能", "技能市场暂时为空")
                else -> {
                    val filtered = state.skills.filter { skill ->
                        query.isBlank() ||
                            skill.localizedName().contains(query, true) ||
                            skill.localizedDescription().contains(query, true)
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
                        grouped.forEach { (category, skills) ->
                            item(key = "header-$category") {
                                SectionHeader("${categoryLabels[category] ?: category} · ${skills.size}")
                            }
                            items(skills, key = { it.id }) { skill ->
                                AnimateIn(0) {
                                    SkillCard(
                                        skill = skill,
                                        enabled = skill.id in state.enabledIds,
                                        busy = state.busyId == skill.id,
                                        missing = skill.requires.filter { it !in state.enabledIds },
                                        needsLogin = state.isGuest && !skill.availableToGuest,
                                        onToggle = { enabled -> viewModel.toggle(skill, enabled) },
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
}

@Composable
private fun SkillCard(
    skill: Skill,
    enabled: Boolean,
    busy: Boolean,
    missing: List<String>,
    needsLogin: Boolean,
    onToggle: (Boolean) -> Unit,
) {
    FlorisCard {
        // 未登录不可用的技能整体压暗，一眼能分出哪些要登录。
        Row(Modifier.padding(14.dp).alpha(if (needsLogin) 0.5f else 1f)) {
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
                        skill.localizedName(),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (needsLogin || skill.locked == true || skill.builtin == true) {
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
                    ).joinToString(" · ").ifEmpty { "Floris 官方" },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    skill.localizedDescription(),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (needsLogin) {
                        StatusChip(t(StringKey.SkillsLoginRequired), MaterialTheme.colorScheme.error)
                    } else {
                        StatusChip(t(StringKey.SkillsGuestReady), MaterialTheme.colorScheme.tertiary)
                    }
                    if (skill.locked == true) {
                        StatusChip(t(StringKey.SkillsAlwaysOn), MaterialTheme.colorScheme.secondary)
                    }
                    if (skill.requires.isNotEmpty()) {
                        StatusChip(
                            "${t(StringKey.SkillsDependencies)} ${skill.requires.size}",
                            MaterialTheme.colorScheme.primary,
                        )
                    }
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
    }
}

private fun Skill.localizedName(): String =
    name["zh-CN"] ?: name["zh"] ?: name["en"] ?: name.values.firstOrNull() ?: id

private fun Skill.localizedDescription(): String =
    description["zh-CN"] ?: description["zh"] ?: description["en"]
        ?: description.values.firstOrNull() ?: ""
