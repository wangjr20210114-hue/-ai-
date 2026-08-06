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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.Person
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.components.CatIconPill
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.bool
import com.floris.android.core.data.num
import com.floris.android.core.data.obj
import com.floris.android.core.data.str
import com.floris.android.core.model.MapPreferences
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
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.ThemeMode
import com.floris.android.ui.prefs.t
import com.floris.android.ui.settingsViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SettingsViewModel(
    private val repository: FlorisRepository,
    val preferences: AppPreferences,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val proactiveEnabled: Boolean = true,
        val parallelImageSearch: Boolean = true,
        val mapPreferences: MapPreferences = MapPreferences(),
        val dailyTokens: Long = 0,
        val monthlyTokens: Long = 0,
        val loading: Boolean = true,
        val resetting: Boolean = false,
        val message: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private val preferenceMutationMutex = Mutex()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            val conversationId = repository.activeConversationId()
            runCatching { repository.intelligencePreferences(conversationId) }.onSuccess { intelligence ->
                val search = intelligence.obj("search_preferences")
                search?.num("result_limit")?.toInt()?.let { preferences.setWebResults(it) }
                search?.num("image_limit")?.toInt()?.let { preferences.setImageCandidates(it) }
                _state.value = _state.value.copy(
                    parallelImageSearch = search?.bool("parallel_image_search") ?: true,
                    mapPreferences = intelligence.obj("map_preferences")
                        ?.toMapPreferences() ?: MapPreferences(),
                )
            }
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
                _state.value = _state.value.copy(
                    proactiveEnabled = !enabled,
                    message = strings.get(StringKey.SettingsSaveFailed),
                )
            }
        }
    }

    fun setTheme(mode: ThemeMode) = viewModelScope.launch { preferences.setTheme(mode) }
    fun setLanguage(language: Language) = viewModelScope.launch { preferences.setLanguage(language) }
    fun setWebResults(value: Int) = viewModelScope.launch {
        val before = preferences.webResults.value
        preferences.setWebResults(value)
        runCatching {
            preferenceMutationMutex.withLock {
                repository.updateSearchPreferences(
                    repository.activeConversationId(),
                    value,
                    preferences.imageCandidates.value,
                    _state.value.parallelImageSearch,
                )
            }
        }.onFailure {
            preferences.setWebResults(before)
            _state.value = _state.value.copy(message = strings.get(StringKey.SettingsSaveFailed))
        }
    }

    fun setImageCandidates(value: Int) = viewModelScope.launch {
        val before = preferences.imageCandidates.value
        preferences.setImageCandidates(value)
        runCatching {
            preferenceMutationMutex.withLock {
                repository.updateSearchPreferences(
                    repository.activeConversationId(),
                    preferences.webResults.value,
                    value,
                    _state.value.parallelImageSearch,
                )
            }
        }.onFailure {
            preferences.setImageCandidates(before)
            _state.value = _state.value.copy(message = strings.get(StringKey.SettingsSaveFailed))
        }
    }

    fun setParallelImageSearch(enabled: Boolean) = viewModelScope.launch {
        val before = _state.value.parallelImageSearch
        _state.value = _state.value.copy(parallelImageSearch = enabled)
        runCatching {
            preferenceMutationMutex.withLock {
                repository.updateSearchPreferences(
                    repository.activeConversationId(),
                    preferences.webResults.value,
                    preferences.imageCandidates.value,
                    enabled,
                )
            }
        }.onFailure {
            _state.value = _state.value.copy(
                parallelImageSearch = before,
                message = strings.get(StringKey.SettingsSaveFailed),
            )
        }
    }

    fun setMapPreferences(next: MapPreferences) {
        val before = _state.value.mapPreferences
        _state.value = _state.value.copy(mapPreferences = next)
        viewModelScope.launch {
            runCatching {
                preferenceMutationMutex.withLock {
                    repository.updateMapPreferences(repository.activeConversationId(), next)
                }
            }.onSuccess { response ->
                _state.value = _state.value.copy(
                    mapPreferences = response.obj("map_preferences")?.toMapPreferences(next) ?: next,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    mapPreferences = before,
                    message = strings.get(StringKey.SettingsSaveFailed),
                )
            }
        }
    }

    fun resetData() {
        _state.value = _state.value.copy(resetting = true)
        viewModelScope.launch {
            runCatching { repository.resetAll(repository.activeConversationId()) }
                .onSuccess {
                    _state.value = _state.value.copy(
                        resetting = false,
                        message = strings.get(StringKey.SettingsResetSucceeded),
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        resetting = false,
                        message = strings.get(StringKey.SettingsResetFailed),
                    )
                }
        }
    }

    fun consumeMessage() { _state.value = _state.value.copy(message = null) }
}

private fun kotlinx.serialization.json.JsonObject.toMapPreferences(
    fallback: MapPreferences = MapPreferences(),
) = MapPreferences(
    service_mode = str("service_mode") ?: fallback.service_mode,
    place_result_limit = num("place_result_limit")?.toInt() ?: fallback.place_result_limit,
    route_stop_limit = num("route_stop_limit")?.toInt() ?: fallback.route_stop_limit,
    search_timeout_seconds = num("search_timeout_seconds")?.toInt() ?: fallback.search_timeout_seconds,
    preferred_route_mode = str("preferred_route_mode") ?: fallback.preferred_route_mode,
    route_strategy = str("route_strategy") ?: fallback.route_strategy,
    near_time_tolerance_minutes = num("near_time_tolerance_minutes")?.toInt()
        ?: fallback.near_time_tolerance_minutes,
    learn_route_preferences = bool("learn_route_preferences") ?: fallback.learn_route_preferences,
)

@Composable
fun SettingsScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onOpenPersonalization: () -> Unit,
) {
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
            CatIconPill(
                resId = R.drawable.ic_back,
                contentDescription = t(StringKey.Back),
                onClick = onBack,
            )
            Spacer(Modifier.width(4.dp))
            Text(t(StringKey.SettingsTitle), style = MaterialTheme.typography.headlineMedium)
        }

        Box(Modifier.weight(1f)) {
            LazyColumn(
                // 底部多留白：清空数据是危险操作，不该紧贴屏幕边缘。
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 56.dp),
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
                item {
                    SettingRow(
                        title = t(StringKey.SettingsPersonalization),
                        subtitle = t(StringKey.SettingsPersonalizationDesc),
                        icon = Icons.Default.Person,
                        onClick = onOpenPersonalization,
                    )
                }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsParallelImages),
                        subtitle = t(StringKey.SettingsParallelImagesDesc),
                        icon = Icons.Default.Image,
                        trailing = {
                            FlorisSwitch(
                                checked = state.parallelImageSearch,
                                onCheckedChange = viewModel::setParallelImageSearch,
                            )
                        },
                    )
                }

                item { SectionHeader(t(StringKey.SettingsMapExperience)) }
                item {
                    FlorisCard {
                        val map = state.mapPreferences
                        Column(Modifier.padding(16.dp)) {
                            Text(
                                t(StringKey.SettingsMapExperienceDesc),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Spacer(Modifier.height(14.dp))
                            PreferenceLabel(t(StringKey.SettingsMapServiceMode))
                            SegmentedControl(
                                options = listOf(
                                    t(StringKey.SettingsMapFast),
                                    t(StringKey.SettingsMapBalanced),
                                    t(StringKey.SettingsMapComplete),
                                ),
                                selectedIndex = listOf("fast", "balanced", "complete")
                                    .indexOf(map.service_mode).coerceAtLeast(0),
                                onSelect = { index ->
                                    val mode = listOf("fast", "balanced", "complete")[index]
                                    val defaults = when (mode) {
                                        "fast" -> Triple(4, 4, 20)
                                        "complete" -> Triple(10, 12, 55)
                                        else -> Triple(6, 8, 30)
                                    }
                                    viewModel.setMapPreferences(
                                        map.copy(
                                            service_mode = mode,
                                            place_result_limit = defaults.first,
                                            route_stop_limit = defaults.second,
                                            search_timeout_seconds = defaults.third,
                                        ),
                                    )
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(12.dp))
                            PreferenceStepperRow(
                                t(StringKey.SettingsMapPlaceCount), map.place_result_limit, 3..12,
                            ) { viewModel.setMapPreferences(map.copy(place_result_limit = it)) }
                            PreferenceStepperRow(
                                t(StringKey.SettingsMapRouteStops), map.route_stop_limit, 2..12,
                            ) { viewModel.setMapPreferences(map.copy(route_stop_limit = it)) }
                            PreferenceStepperRow(
                                t(StringKey.SettingsMapTimeout), map.search_timeout_seconds, 10..55,
                            ) { viewModel.setMapPreferences(map.copy(search_timeout_seconds = it)) }
                            Spacer(Modifier.height(8.dp))
                            PreferenceLabel(t(StringKey.SettingsPreferredRoute))
                            SegmentedControl(
                                options = listOf(
                                    t(StringKey.RouteDriving), t(StringKey.RouteTransit),
                                    t(StringKey.RouteWalking), t(StringKey.RouteBicycling),
                                ),
                                selectedIndex = listOf("driving", "transit", "walking", "bicycling")
                                    .indexOf(map.preferred_route_mode).coerceAtLeast(0),
                                onSelect = { index ->
                                    viewModel.setMapPreferences(
                                        map.copy(
                                            preferred_route_mode = listOf(
                                                "driving", "transit", "walking", "bicycling",
                                            )[index],
                                        ),
                                    )
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(12.dp))
                            PreferenceLabel(t(StringKey.SettingsRouteStrategy))
                            SegmentedControl(
                                options = listOf(
                                    t(StringKey.StrategyTimeCost),
                                    t(StringKey.StrategyLeastTime),
                                    t(StringKey.StrategyLeastCost),
                                ),
                                selectedIndex = listOf("time_then_cost", "least_time", "least_cost")
                                    .indexOf(map.route_strategy).coerceAtLeast(0),
                                onSelect = { index ->
                                    viewModel.setMapPreferences(
                                        map.copy(
                                            route_strategy = listOf(
                                                "time_then_cost", "least_time", "least_cost",
                                            )[index],
                                        ),
                                    )
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(8.dp))
                            PreferenceStepperRow(
                                t(StringKey.SettingsNearTolerance),
                                map.near_time_tolerance_minutes,
                                0..30,
                            ) {
                                viewModel.setMapPreferences(map.copy(near_time_tolerance_minutes = it))
                            }
                            Row(
                                Modifier.fillMaxWidth().padding(top = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    t(StringKey.SettingsLearnRoute),
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.weight(1f),
                                )
                                FlorisSwitch(
                                    checked = map.learn_route_preferences,
                                    onCheckedChange = {
                                        viewModel.setMapPreferences(map.copy(learn_route_preferences = it))
                                    },
                                )
                            }
                        }
                    }
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
                item { Spacer(Modifier.height(8.dp)) }
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
                                text = if (state.resetting) t(StringKey.SettingsResetting)
                                else t(StringKey.SettingsResetConfirm),
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
private fun PreferenceLabel(label: String) {
    Text(label, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 7.dp))
}

@Composable
private fun PreferenceStepperRow(
    label: String,
    value: Int,
    range: IntRange,
    onValueChange: (Int) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        Stepper(value = value, onValueChange = onValueChange, range = range)
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
