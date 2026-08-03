package com.floris.android.ui.settings

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.bool
import com.floris.android.core.data.num
import com.floris.android.core.data.obj
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.settingsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SettingsViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
) : ViewModel() {

    data class UiState(
        val proactiveEnabled: Boolean = true,
        val displayName: String = "",
        val dailyTokens: Long = 0,
        val monthlyTokens: Long = 0,
        val loading: Boolean = true,
        val resetting: Boolean = false,
        val message: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching { repository.proactive(conversationId, "get") }.onSuccess { proactive ->
                val enabled = proactive.obj("preferences")?.bool("enabled") ?: true
                _state.value = _state.value.copy(proactiveEnabled = enabled)
            }
            runCatching { repository.providerUsage(conversationId) }.onSuccess { usage ->
                _state.value = _state.value.copy(
                    dailyTokens = usage.obj("usage")?.num("daily_tokens") ?: 0,
                    monthlyTokens = usage.obj("usage")?.num("monthly_tokens") ?: 0,
                )
            }
            runCatching { repository.getProfile() }.onSuccess { profile ->
                _state.value = _state.value.copy(displayName = profile.display_name ?: "")
            }
            _state.value = _state.value.copy(loading = false)
        }
    }

    fun setProactiveEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(proactiveEnabled = enabled)
        viewModelScope.launch {
            runCatching {
                repository.proactive(
                    repository.activeConversationId(),
                    "update_preferences",
                    buildJsonObject { put("enabled", enabled) },
                )
            }.onFailure { _state.value = _state.value.copy(proactiveEnabled = !enabled, message = "设置失败") }
        }
    }

    fun updateDisplayName(name: String) {
        if (name.isBlank()) return
        viewModelScope.launch {
            runCatching { repository.updateDisplayName(name.trim()) }
                .onSuccess { _state.value = _state.value.copy(displayName = name.trim(), message = "昵称已更新") }
                .onFailure { _state.value = _state.value.copy(message = "更新失败") }
        }
    }

    fun resetData() {
        _state.value = _state.value.copy(resetting = true)
        viewModelScope.launch {
            runCatching { repository.resetAll(repository.activeConversationId()) }
                .onSuccess { _state.value = _state.value.copy(resetting = false, message = "数据已清除") }
                .onFailure { _state.value = _state.value.copy(resetting = false, message = "清除失败，请重试") }
        }
    }

    fun consumeMessage() { _state.value = _state.value.copy(message = null) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: SettingsViewModel = viewModel(factory = container.settingsViewModelFactory())
    val state by viewModel.state.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    var editingName by remember { mutableStateOf(false) }
    var nameDraft by remember { mutableStateOf("") }
    var confirmReset by remember { mutableStateOf(false) }

    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() }
    }

    if (editingName) {
        AlertDialog(
            onDismissRequest = { editingName = false },
            title = { Text("修改昵称") },
            text = {
                OutlinedTextField(
                    value = nameDraft,
                    onValueChange = { nameDraft = it },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(onClick = { viewModel.updateDisplayName(nameDraft); editingName = false }) { Text("保存") }
            },
            dismissButton = { TextButton(onClick = { editingName = false }) { Text("取消") } },
        )
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text("清除全部数据？") },
            text = { Text("将删除账号下的全部会话、工作区与文件，且无法恢复。") },
            confirmButton = {
                TextButton(onClick = { viewModel.resetData(); confirmReset = false }) {
                    Text("确认清除", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("取消") } },
        )
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = { Text("设置") },
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
            item { SectionHeader("账号") }
            item {
                FlorisCard(onClick = { nameDraft = state.displayName; editingName = true }) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("昵称", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                        Text(
                            state.displayName.ifBlank { "未设置" },
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            item { SectionHeader("偏好") }
            item {
                FlorisCard {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("主动提醒", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "日程变化、天气与行程的主动播报",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Switch(checked = state.proactiveEnabled, onCheckedChange = viewModel::setProactiveEnabled)
                    }
                }
            }

            item { SectionHeader("用量") }
            item {
                FlorisCard {
                    Column(Modifier.padding(14.dp)) {
                        Row(Modifier.fillMaxWidth()) {
                            Text("今日 Token", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                            Text("%,d".format(state.dailyTokens), style = MaterialTheme.typography.titleMedium)
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(Modifier.fillMaxWidth()) {
                            Text("本月 Token", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                            Text("%,d".format(state.monthlyTokens), style = MaterialTheme.typography.titleMedium)
                        }
                    }
                }
            }

            item { SectionHeader("数据") }
            item {
                FlorisCard(onClick = { confirmReset = true }) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            if (state.resetting) "清除中…" else "清除全部数据",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.titleMedium,
                        )
                    }
                }
            }

            item {
                Text(
                    "Floris Android 1.0.0 · 契约 v1 · floris-dev.jlutx.com",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
}
