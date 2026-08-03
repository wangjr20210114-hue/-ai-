package com.floris.android.ui.skills

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.arr
import com.floris.android.core.data.asString
import com.floris.android.core.data.obj
import com.floris.android.core.model.Skill
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.skillsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SkillsViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val skills: List<Skill> = emptyList(),
        val enabledIds: Set<String> = emptySet(),
        val busyId: String? = null,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(loading = true, error = null)
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
                        ?: skill.locked == true
                        ?: pref?.let { it != "false" } ?: true
                    if (isEnabled) skill.id else null
                }.toSet()
                _state.value = UiState(loading = false, skills = catalog.skills, enabledIds = enabled)
            }.onFailure {
                _state.value = UiState(loading = false, error = "技能市场加载失败")
            }
        }
    }

    fun toggle(skill: Skill, enabled: Boolean) {
        if (_state.value.busyId != null) return
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
            }.onFailure {
                _state.value = _state.value.copy(busyId = null, error = "操作失败，请重试")
            }
        }
    }

    fun consumeError() { _state.value = _state.value.copy(error = null) }
}

private val categoryOrder = listOf("foundation", "knowledge", "creative", "productivity", "location", "other")
private val categoryLabels = mapOf(
    "foundation" to "基础能力",
    "knowledge" to "知识检索",
    "creative" to "创作",
    "productivity" to "效率",
    "location" to "位置服务",
    "other" to "其他",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SkillsScreen(container: AppContainer) {
    val viewModel: SkillsViewModel = viewModel(factory = container.skillsViewModelFactory())
    val state by viewModel.state.collectAsState()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    var query by remember { mutableStateOf("") }
    val snackbar = androidx.compose.material3.SnackbarHostState()
    androidx.compose.runtime.LaunchedEffect(state.error) {
        state.error?.let { snackbar.showSnackbar(it); viewModel.consumeError() }
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        snackbarHost = { androidx.compose.material3.SnackbarHost(snackbar) },
        topBar = {
            LargeTopAppBar(
                title = { Text("技能") },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            TextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("搜索技能…") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                shape = CircleShape,
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.surface,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                ),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
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
                        contentPadding = PaddingValues(bottom = 32.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        grouped.forEach { (category, skills) ->
                            item(key = "header-$category") {
                                SectionHeader(categoryLabels[category] ?: category)
                            }
                            items(skills, key = { it.id }) { skill ->
                                AnimateIn(0) {
                                    SkillRow(
                                        skill = skill,
                                        enabled = skill.id in state.enabledIds,
                                        busy = state.busyId == skill.id,
                                        missing = skill.requires.filter { it !in state.enabledIds },
                                        onToggle = { enabled -> viewModel.toggle(skill, enabled) },
                                        modifier = Modifier.padding(horizontal = 16.dp),
                                    )
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
private fun SkillRow(
    skill: Skill,
    enabled: Boolean,
    busy: Boolean,
    missing: List<String>,
    onToggle: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    FlorisCard(modifier = modifier) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(skill.localizedName(), style = MaterialTheme.typography.titleMedium)
                    if (skill.locked == true) {
                        Spacer(Modifier.padding(2.dp))
                        StatusChip("内置", MaterialTheme.colorScheme.secondary)
                    }
                }
                Spacer(Modifier.height(3.dp))
                Text(
                    skill.localizedDescription(),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (missing.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "需要先启用：${missing.joinToString("、")}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.secondary,
                    )
                }
            }
            Switch(
                checked = enabled,
                onCheckedChange = onToggle,
                enabled = !busy && skill.locked != true,
            )
        }
    }
}

private fun Skill.localizedName(): String =
    name["zh-CN"] ?: name["zh"] ?: name["en"] ?: name.values.firstOrNull() ?: id

private fun Skill.localizedDescription(): String =
    description["zh-CN"] ?: description["zh"] ?: description["en"]
        ?: description.values.firstOrNull() ?: ""
