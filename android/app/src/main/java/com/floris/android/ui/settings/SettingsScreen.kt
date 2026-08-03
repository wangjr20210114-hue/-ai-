package com.floris.android.ui.settings

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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Badge
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.TravelExplore
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
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
import com.floris.android.ui.components.CheckMark
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.FlorisSwitch
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.SegmentedControl
import com.floris.android.ui.components.SettingRow
import com.floris.android.ui.components.Stepper
import com.floris.android.ui.components.pressable
import com.floris.android.ui.prefs.AppPreferences
import com.floris.android.ui.prefs.Language
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.ThemeMode
import com.floris.android.ui.prefs.t
import com.floris.android.ui.settingsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SettingsViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
    val preferences: AppPreferences,
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
            }.onFailure {
                _state.value = _state.value.copy(proactiveEnabled = !enabled, message = "设置失败")
            }
        }
    }

    fun updateDisplayName(name: String) {
        if (name.isBlank()) return
        viewModelScope.launch {
            runCatching { repository.updateDisplayName(name.trim()) }
                .onSuccess {
                    _state.value = _state.value.copy(displayName = name.trim(), message = "昵称已更新")
                }
                .onFailure { _state.value = _state.value.copy(message = "更新失败") }
        }
    }

    fun setTheme(mode: ThemeMode) = viewModelScope.launch { preferences.setTheme(mode) }
    fun setLanguage(language: Language) = viewModelScope.launch { preferences.setLanguage(language) }
    fun setWebResults(value: Int) = viewModelScope.launch { preferences.setWebResults(value) }
    fun setImageCandidates(value: Int) = viewModelScope.launch { preferences.setImageCandidates(value) }
    fun replayOnboarding() = viewModelScope.launch { preferences.setOnboardingDone(false) }

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

@Composable
fun SettingsScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: SettingsViewModel = viewModel(factory = container.settingsViewModelFactory())
    val state by viewModel.state.collectAsState()
    val themeMode by viewModel.preferences.theme.collectAsState()
    val language by viewModel.preferences.language.collectAsState()
    val webResults by viewModel.preferences.webResults.collectAsState()
    val imageCandidates by viewModel.preferences.imageCandidates.collectAsState()

    val snackbar = remember { SnackbarHostState() }
    var confirmReset by remember { mutableStateOf(false) }
    var languageSheet by remember { mutableStateOf(false) }

    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() }
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text(t(StringKey.SettingsResetTitle)) },
            text = { Text(t(StringKey.SettingsResetBody)) },
            confirmButton = {
                TextButton(onClick = { viewModel.resetData(); confirmReset = false }) {
                    Text(t(StringKey.SettingsResetConfirm), color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmReset = false }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    if (languageSheet) {
        AlertDialog(
            onDismissRequest = { languageSheet = false },
            title = { Text(t(StringKey.SettingsLanguage)) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Language.entries.forEach { option ->
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .pressable {
                                    viewModel.setLanguage(option)
                                    languageSheet = false
                                }
                                .padding(horizontal = 12.dp, vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                option.label,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.weight(1f),
                            )
                            CheckMark(visible = option == language)
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { languageSheet = false }) { Text(t(StringKey.Close)) }
            },
        )
    }

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
            Text(t(StringKey.SettingsTitle), style = MaterialTheme.typography.headlineMedium)
        }

        Box(Modifier.weight(1f)) {
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                // 外观
                item { SectionHeader(t(StringKey.SettingsAppearance)) }
                item {
                    FlorisCard(modifier = Modifier.onboardingTarget(TourStepKey.THEME)) {
                        Column(Modifier.padding(16.dp)) {
                            Text(t(StringKey.SettingsTheme), style = MaterialTheme.typography.titleMedium)
                            Spacer(Modifier.height(10.dp))
                            SegmentedControl(
                                options = listOf(
                                    t(StringKey.SettingsThemeSystem),
                                    t(StringKey.SettingsThemeLight),
                                    t(StringKey.SettingsThemeDark),
                                ),
                                selectedIndex = themeMode.ordinal,
                                onSelect = { viewModel.setTheme(ThemeMode.entries[it]) },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsLanguage),
                        subtitle = language.label,
                        icon = Icons.Default.Language,
                        onClick = { languageSheet = true },
                    )
                }

                // 偏好
                item { SectionHeader(t(StringKey.SettingsPreferences)) }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsProactive),
                        subtitle = t(StringKey.SettingsProactiveDesc),
                        icon = Icons.Default.NotificationsActive,
                        trailing = {
                            FlorisSwitch(
                                checked = state.proactiveEnabled,
                                onCheckedChange = viewModel::setProactiveEnabled,
                            )
                        },
                    )
                }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsWebResults),
                        subtitle = t(StringKey.SettingsWebResultsDesc),
                        icon = Icons.Default.TravelExplore,
                        trailing = {
                            Stepper(
                                value = webResults,
                                onValueChange = viewModel::setWebResults,
                                range = 3..12,
                            )
                        },
                    )
                }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsImageCandidates),
                        subtitle = t(StringKey.SettingsImageCandidatesDesc),
                        icon = Icons.Default.Image,
                        trailing = {
                            Stepper(
                                value = imageCandidates,
                                onValueChange = viewModel::setImageCandidates,
                                range = 0..8,
                            )
                        },
                    )
                }

                // 用量
                item { SectionHeader(t(StringKey.SettingsUsage)) }
                item {
                    FlorisCard {
                        Column(Modifier.padding(16.dp)) {
                            UsageRow(t(StringKey.SettingsDailyTokens), state.dailyTokens)
                            Spacer(Modifier.height(10.dp))
                            UsageRow(t(StringKey.SettingsMonthlyTokens), state.monthlyTokens)
                        }
                    }
                }

                // 数据
                item { SectionHeader(t(StringKey.SettingsData)) }
                item {
                    FlorisCard {
                        Row(
                            Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(
                                Modifier
                                    .size(34.dp)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(MaterialTheme.colorScheme.error.copy(alpha = 0.12f)),
                                contentAlignment = Alignment.Center,
                            ) {
                                androidx.compose.material3.Icon(
                                    Icons.Default.DeleteOutline, null,
                                    tint = MaterialTheme.colorScheme.error,
                                    modifier = Modifier.size(18.dp),
                                )
                            }
                            Spacer(Modifier.width(12.dp))
                            Text(
                                t(StringKey.SettingsResetData),
                                style = MaterialTheme.typography.titleMedium,
                                modifier = Modifier.weight(1f),
                            )
                            PillButton(
                                text = if (state.resetting) "清除中…" else t(StringKey.SettingsResetConfirm),
                                onClick = { confirmReset = true },
                                style = PillStyle.Danger,
                                compact = true,
                                enabled = !state.resetting,
                            )
                        }
                    }
                }
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter))
        }
    }
}

@Composable
private fun UsageRow(label: String, value: Long) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text("%,d".format(value), style = MaterialTheme.typography.titleMedium)
    }
}
