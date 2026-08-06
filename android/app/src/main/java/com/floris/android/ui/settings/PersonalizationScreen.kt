package com.floris.android.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.components.CatIconPill
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.IntelligenceState
import com.floris.android.core.model.MemoryProposal
import com.floris.android.core.model.ProactivePreferences
import com.floris.android.core.model.ProactiveRuleProposal
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.ProactiveWorkflow
import com.floris.android.core.model.ProactiveWorkflowStep
import com.floris.android.core.model.UserMemory
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.FlorisSwitch
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.SegmentedControl
import com.floris.android.ui.components.Stepper
import com.floris.android.ui.personalizationViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

class PersonalizationViewModel(
    private val repository: FlorisRepository,
) : ViewModel() {
    data class UiState(
        val intelligence: IntelligenceState = IntelligenceState(),
        val proactive: ProactiveState = ProactiveState(),
        val loading: Boolean = true,
        val busy: String? = null,
        val message: StringKey? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init {
        viewModelScope.launch {
            repository.proactiveStateFlow.collect { projection ->
                projection?.let { next -> _state.update { it.copy(proactive = next) } }
            }
        }
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        val conversationId = repository.activeConversationId()
        val intelligence = runCatching { repository.intelligenceState(conversationId) }
        val proactive = runCatching { repository.proactiveState(conversationId) }
        _state.update { current ->
            current.copy(
                intelligence = intelligence.getOrDefault(current.intelligence),
                proactive = proactive.getOrDefault(current.proactive),
                loading = false,
                message = if (intelligence.isFailure && proactive.isFailure) {
                    StringKey.SettingsSaveFailed
                } else null,
            )
        }
    }

    fun setMemoryEnabled(enabled: Boolean) = mutateIntelligence(
        key = "memory-preference",
        operation = "update_memory_preferences",
        input = buildJsonObject { putJsonObject("preferences") { put("enabled", enabled) } },
    )

    fun decideMemory(proposal: MemoryProposal, accepted: Boolean) = mutateIntelligence(
        key = proposal.id,
        operation = if (accepted) "confirm_memory" else "reject_memory",
        input = buildJsonObject {
            put("proposal_id", proposal.id)
            put("version", proposal.version)
        },
    )

    fun deleteMemory(memory: UserMemory) = mutateIntelligence(
        key = memory.id,
        operation = "delete_memory",
        input = buildJsonObject { put("memory_id", memory.id) },
    )

    fun rollbackMemory(memory: UserMemory) {
        val previous = memory.history.map { it.version }.filter { it < memory.version }.maxOrNull()
            ?: return
        mutateIntelligence(
            key = memory.id,
            operation = "rollback_memory",
            input = buildJsonObject {
                put("memory_id", memory.id)
                put("target_version", previous)
            },
        )
    }

    fun clearMemories() = mutateIntelligence("clear-memory", "clear_memories")

    fun decideRule(rule: ProactiveRuleProposal, accepted: Boolean) = mutateIntelligence(
        key = rule.id,
        operation = if (accepted) "confirm_rule" else "reject_rule",
        input = buildJsonObject {
            put("rule_id", rule.id)
            put("version", rule.version)
        },
    )

    fun updateProactive(changes: JsonObject) {
        val before = _state.value.proactive.preferences
        val optimistic = before.withChanges(changes)
        _state.update { it.copy(proactive = it.proactive.copy(preferences = optimistic)) }
        mutateProactive(
            key = "proactive-preferences",
            operation = "update_preferences",
            input = buildJsonObject { put("preferences", changes) },
            onFailure = {
                _state.update { it.copy(proactive = it.proactive.copy(preferences = before)) }
            },
        )
    }

    fun decideWorkflow(workflow: ProactiveWorkflow, accepted: Boolean) = mutateProactive(
        key = workflow.id,
        operation = if (accepted) "confirm_workflow" else "reject_workflow",
        input = workflowInput(workflow),
    )

    fun cancelWorkflow(workflow: ProactiveWorkflow) = mutateProactive(
        key = workflow.id,
        operation = "cancel_workflow",
        input = workflowInput(workflow),
    )

    fun decideWorkflowStep(
        workflow: ProactiveWorkflow,
        step: ProactiveWorkflowStep,
        operation: String,
    ) = mutateProactive(
        key = step.id,
        operation = operation,
        input = buildJsonObject {
            put("workflow_id", workflow.id)
            put("step_id", step.id)
        },
    )

    fun consumeMessage() = _state.update { it.copy(message = null) }

    private fun mutateIntelligence(
        key: String,
        operation: String,
        input: JsonObject = JsonObject(emptyMap()),
    ) {
        if (_state.value.busy != null) return
        _state.update { it.copy(busy = key) }
        viewModelScope.launch {
            runCatching {
                repository.mutateIntelligence(repository.activeConversationId(), operation, input)
            }.onSuccess { next ->
                _state.update {
                    it.copy(intelligence = next, busy = null, message = StringKey.SettingsSaved)
                }
            }.onFailure {
                _state.update { it.copy(busy = null, message = StringKey.SettingsSaveFailed) }
            }
        }
    }

    private fun mutateProactive(
        key: String,
        operation: String,
        input: JsonObject,
        onFailure: () -> Unit = {},
    ) {
        if (_state.value.busy != null) return
        _state.update { it.copy(busy = key) }
        viewModelScope.launch {
            runCatching {
                repository.mutateProactive(repository.activeConversationId(), operation, input)
            }.onSuccess { next ->
                _state.update {
                    it.copy(proactive = next, busy = null, message = StringKey.SettingsSaved)
                }
            }.onFailure {
                onFailure()
                _state.update { it.copy(busy = null, message = StringKey.SettingsSaveFailed) }
            }
        }
    }

    private fun workflowInput(workflow: ProactiveWorkflow) = buildJsonObject {
        put("workflow_id", workflow.id)
        put("version", workflow.version)
    }
}

private fun ProactivePreferences.withChanges(changes: JsonObject): ProactivePreferences = copy(
    enabled = (changes["enabled"] as? JsonPrimitive)?.content?.toBooleanStrictOrNull() ?: enabled,
    autonomy_mode = (changes["autonomy_mode"] as? JsonPrimitive)?.contentOrNull ?: autonomy_mode,
    quiet_hours = (changes["quiet_hours"] as? JsonObject)?.let { value ->
        quiet_hours.copy(
            enabled = (value["enabled"] as? JsonPrimitive)?.content?.toBooleanStrictOrNull()
                ?: quiet_hours.enabled,
        )
    } ?: quiet_hours,
    daily_limit = (changes["daily_limit"] as? JsonPrimitive)?.content?.toIntOrNull() ?: daily_limit,
    lookahead_hours = (changes["lookahead_hours"] as? JsonPrimitive)?.content?.toIntOrNull()
        ?: lookahead_hours,
    window_limit = (changes["window_limit"] as? JsonPrimitive)?.content?.toIntOrNull()
        ?: window_limit,
    provider_schedule_limit = (changes["provider_schedule_limit"] as? JsonPrimitive)
        ?.content?.toIntOrNull() ?: provider_schedule_limit,
    route_gap_hours = (changes["route_gap_hours"] as? JsonPrimitive)?.content?.toIntOrNull()
        ?: route_gap_hours,
    travel_buffer_minutes = (changes["travel_buffer_minutes"] as? JsonPrimitive)
        ?.content?.toIntOrNull() ?: travel_buffer_minutes,
)

@Composable
fun PersonalizationScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: PersonalizationViewModel = viewModel(
        factory = container.personalizationViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    var clearConfirmation by remember { mutableStateOf(false) }
    val localizedMessage = state.message?.let { t(it) }

    LaunchedEffect(localizedMessage) {
        localizedMessage?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() }
    }
    if (clearConfirmation) {
        AlertDialog(
            onDismissRequest = { clearConfirmation = false },
            title = { Text(t(StringKey.MemoryClearTitle)) },
            text = { Text(t(StringKey.MemoryClearBody)) },
            confirmButton = {
                TextButton(onClick = {
                    clearConfirmation = false
                    viewModel.clearMemories()
                }) { Text(t(StringKey.MemoryClear), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { clearConfirmation = false }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .navigationBarsPadding(),
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
            Text(t(StringKey.PersonalizationTitle), style = MaterialTheme.typography.headlineMedium)
        }
        Box(Modifier.weight(1f)) {
            if (state.loading) {
                CircularProgressIndicator(Modifier.align(Alignment.Center))
            } else {
                PersonalizationContent(
                    state = state,
                    onMemoryEnabled = viewModel::setMemoryEnabled,
                    onMemoryDecision = viewModel::decideMemory,
                    onDeleteMemory = viewModel::deleteMemory,
                    onRollbackMemory = viewModel::rollbackMemory,
                    onClearMemories = { clearConfirmation = true },
                    onRuleDecision = viewModel::decideRule,
                    onProactiveChange = viewModel::updateProactive,
                    onWorkflowDecision = viewModel::decideWorkflow,
                    onWorkflowCancel = viewModel::cancelWorkflow,
                    onWorkflowStep = viewModel::decideWorkflowStep,
                )
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter))
        }
    }
}

@Composable
private fun PersonalizationContent(
    state: PersonalizationViewModel.UiState,
    onMemoryEnabled: (Boolean) -> Unit,
    onMemoryDecision: (MemoryProposal, Boolean) -> Unit,
    onDeleteMemory: (UserMemory) -> Unit,
    onRollbackMemory: (UserMemory) -> Unit,
    onClearMemories: () -> Unit,
    onRuleDecision: (ProactiveRuleProposal, Boolean) -> Unit,
    onProactiveChange: (JsonObject) -> Unit,
    onWorkflowDecision: (ProactiveWorkflow, Boolean) -> Unit,
    onWorkflowCancel: (ProactiveWorkflow) -> Unit,
    onWorkflowStep: (ProactiveWorkflow, ProactiveWorkflowStep, String) -> Unit,
) {
    val intelligence = state.intelligence
    val proactive = state.proactive
    val enabled = state.busy == null
    LazyColumn(
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 56.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item { SectionHeader(t(StringKey.MemorySection)) }
        item {
            FlorisCard {
                Row(
                    Modifier.fillMaxWidth().padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(t(StringKey.MemoryEnabled), style = MaterialTheme.typography.titleMedium)
                        Text(
                            t(StringKey.MemoryEnabledDesc),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    FlorisSwitch(
                        checked = intelligence.memory_preferences.enabled,
                        onCheckedChange = onMemoryEnabled,
                        enabled = enabled,
                    )
                }
            }
        }
        val pendingMemories = intelligence.memory_proposals.filter { it.status == "pending" }
        if (pendingMemories.isNotEmpty()) item { SectionHeader(t(StringKey.MemoryPending)) }
        items(pendingMemories, key = { it.id }) { proposal ->
            DecisionCard(
                title = valueSummary(proposal.value),
                reason = proposal.reason,
                enabled = enabled,
                onConfirm = { onMemoryDecision(proposal, true) },
                onReject = { onMemoryDecision(proposal, false) },
            )
        }
        item { SectionHeader(t(StringKey.MemorySaved)) }
        if (intelligence.memories.isEmpty()) {
            item { EmptyCard(t(StringKey.MemoryEmpty)) }
        } else {
            items(intelligence.memories, key = { it.id }) { memory ->
                FlorisCard {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) {
                        Text(valueSummary(memory.value), style = MaterialTheme.typography.titleMedium)
                        Row(
                            Modifier.fillMaxWidth().padding(top = 12.dp),
                            horizontalArrangement = Arrangement.End,
                        ) {
                            if (memory.history.any { it.version < memory.version }) {
                                PillButton(
                                    t(StringKey.MemoryRollback),
                                    { onRollbackMemory(memory) },
                                    style = PillStyle.Ghost,
                                    compact = true,
                                    enabled = enabled,
                                )
                            }
                            PillButton(
                                t(StringKey.Delete),
                                { onDeleteMemory(memory) },
                                style = PillStyle.Danger,
                                compact = true,
                                enabled = enabled,
                            )
                        }
                    }
                }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    PillButton(
                        t(StringKey.MemoryClear), onClearMemories,
                        style = PillStyle.Danger, compact = true, enabled = enabled,
                    )
                }
            }
        }

        val pendingRules = intelligence.rule_proposals.filter { it.status == "pending" }
        if (pendingRules.isNotEmpty()) item { SectionHeader(t(StringKey.RulesSection)) }
        items(pendingRules, key = { it.id }) { rule ->
            DecisionCard(
                title = rule.reason,
                reason = "",
                enabled = enabled,
                onConfirm = { onRuleDecision(rule, true) },
                onReject = { onRuleDecision(rule, false) },
            )
        }

        item { SectionHeader(t(StringKey.ProactiveSection)) }
        item {
            ProactivePreferencesCard(
                preferences = proactive.preferences,
                enabled = enabled,
                onChange = onProactiveChange,
            )
        }

        item { SectionHeader(t(StringKey.WorkflowSection)) }
        val workflows = proactive.workflows.filter { it.status !in setOf("completed", "rejected", "cancelled") }
        if (workflows.isEmpty()) item { EmptyCard(t(StringKey.WorkflowEmpty)) }
        items(workflows, key = { it.id }) { workflow ->
            WorkflowCard(
                workflow = workflow,
                enabled = enabled,
                onDecision = onWorkflowDecision,
                onCancel = onWorkflowCancel,
                onStep = onWorkflowStep,
            )
        }
    }
}

@Composable
private fun DecisionCard(
    title: String,
    reason: String,
    enabled: Boolean,
    onConfirm: () -> Unit,
    onReject: () -> Unit,
) {
    FlorisCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            if (reason.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                PillButton(
                    t(StringKey.MemoryReject), onReject,
                    style = PillStyle.Ghost, compact = true, enabled = enabled,
                )
                Spacer(Modifier.width(6.dp))
                PillButton(t(StringKey.Confirm), onConfirm, compact = true, enabled = enabled)
            }
        }
    }
}

@Composable
private fun ProactivePreferencesCard(
    preferences: ProactivePreferences,
    enabled: Boolean,
    onChange: (JsonObject) -> Unit,
) {
    FlorisCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            PreferenceSwitch(
                t(StringKey.SettingsProactive), preferences.enabled, enabled,
            ) { onChange(buildJsonObject { put("enabled", it) }) }
            Spacer(Modifier.height(12.dp))
            Text(t(StringKey.ProactiveAutonomy), style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(7.dp))
            val modes = listOf("observe", "remind", "propose", "low_risk_auto")
            SegmentedControl(
                options = listOf(
                    t(StringKey.ProactiveObserve), t(StringKey.ProactiveRemind),
                    t(StringKey.ProactivePropose), t(StringKey.ProactiveLowRiskAuto),
                ),
                selectedIndex = modes.indexOf(preferences.autonomy_mode).coerceAtLeast(0),
                onSelect = { index ->
                    onChange(buildJsonObject { put("autonomy_mode", modes[index]) })
                },
                modifier = Modifier.fillMaxWidth(),
            )
            PreferenceSwitch(
                t(StringKey.ProactiveQuietHours), preferences.quiet_hours.enabled, enabled,
            ) { quiet ->
                onChange(buildJsonObject {
                    putJsonObject("quiet_hours") {
                        put("enabled", quiet)
                        put("start", preferences.quiet_hours.start)
                        put("end", preferences.quiet_hours.end)
                    }
                })
            }
            PreferenceStepper(t(StringKey.ProactiveDailyLimit), preferences.daily_limit, 0..20, enabled) {
                onChange(buildJsonObject { put("daily_limit", it) })
            }
            PreferenceStepper(t(StringKey.ProactiveLookahead), preferences.lookahead_hours, 1..72, enabled) {
                onChange(buildJsonObject { put("lookahead_hours", it) })
            }
            PreferenceStepper(t(StringKey.ProactiveWindowLimit), preferences.window_limit, 1..10, enabled) {
                onChange(buildJsonObject { put("window_limit", it) })
            }
            PreferenceStepper(t(StringKey.ProactiveProviderLimit), preferences.provider_schedule_limit, 1..12, enabled) {
                onChange(buildJsonObject { put("provider_schedule_limit", it) })
            }
            PreferenceStepper(t(StringKey.ProactiveRouteGap), preferences.route_gap_hours, 1..8, enabled) {
                onChange(buildJsonObject { put("route_gap_hours", it) })
            }
            PreferenceStepper(t(StringKey.ProactiveTravelBuffer), preferences.travel_buffer_minutes, 0..120, enabled) {
                onChange(buildJsonObject { put("travel_buffer_minutes", it) })
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WorkflowCard(
    workflow: ProactiveWorkflow,
    enabled: Boolean,
    onDecision: (ProactiveWorkflow, Boolean) -> Unit,
    onCancel: (ProactiveWorkflow) -> Unit,
    onStep: (ProactiveWorkflow, ProactiveWorkflowStep, String) -> Unit,
) {
    FlorisCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text(workflow.title, style = MaterialTheme.typography.titleMedium)
            if (workflow.reason.isNotBlank()) {
                Text(
                    workflow.reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            workflow.steps.forEachIndexed { index, step ->
                Row(Modifier.fillMaxWidth().padding(top = 10.dp)) {
                    Text(
                        "${index + 1}",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(step.title, style = MaterialTheme.typography.bodyMedium)
                        if (step.body.isNotBlank()) {
                            Text(
                                step.body,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        if (workflow.status == "active" && step.status in setOf("pending", "notified", "failed", "attention_required", "compensating")) {
                            FlowRow(
                                modifier = Modifier.padding(top = 6.dp),
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                if (step.status == "failed" || step.status == "attention_required") {
                                    PillButton(
                                        t(StringKey.Retry),
                                        { onStep(workflow, step, "retry_workflow_step") },
                                        style = PillStyle.Tonal,
                                        compact = true,
                                        enabled = enabled,
                                    )
                                } else if (step.status == "compensating") {
                                    PillButton(
                                        t(StringKey.WorkflowCompensationComplete),
                                        { onStep(workflow, step, "compensate_workflow_step") },
                                        compact = true,
                                        enabled = enabled,
                                    )
                                } else {
                                    PillButton(
                                        t(StringKey.WorkflowSkipStep),
                                        { onStep(workflow, step, "skip_workflow_step") },
                                        style = PillStyle.Ghost,
                                        compact = true,
                                        enabled = enabled,
                                    )
                                    PillButton(
                                        t(StringKey.WorkflowCompleteStep),
                                        { onStep(workflow, step, "complete_workflow_step") },
                                        compact = true,
                                        enabled = enabled,
                                    )
                                    PillButton(
                                        t(StringKey.WorkflowMarkFailed),
                                        { onStep(workflow, step, "fail_workflow_step") },
                                        style = PillStyle.Ghost,
                                        compact = true,
                                        enabled = enabled,
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                if (workflow.status == "awaiting_confirmation") {
                    PillButton(
                        t(StringKey.WorkflowReject), { onDecision(workflow, false) },
                        style = PillStyle.Ghost, compact = true, enabled = enabled,
                    )
                    Spacer(Modifier.width(6.dp))
                    PillButton(
                        t(StringKey.WorkflowConfirm), { onDecision(workflow, true) },
                        compact = true, enabled = enabled,
                    )
                } else {
                    PillButton(
                        t(StringKey.WorkflowCancel), { onCancel(workflow) },
                        style = PillStyle.Danger, compact = true, enabled = enabled,
                    )
                }
            }
        }
    }
}

@Composable
private fun PreferenceSwitch(
    label: String,
    checked: Boolean,
    enabled: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        FlorisSwitch(checked, onCheckedChange, enabled = enabled)
    }
}

@Composable
private fun PreferenceStepper(
    label: String,
    value: Int,
    range: IntRange,
    enabled: Boolean,
    onChange: (Int) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        Stepper(value, onChange, range = if (enabled) range else value..value)
    }
}

@Composable
private fun EmptyCard(text: String) {
    FlorisCard {
        Text(
            text,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth().padding(16.dp),
        )
    }
}

private fun valueSummary(value: JsonElement): String = when (value) {
    JsonNull -> ""
    is JsonPrimitive -> value.contentOrNull.orEmpty()
    is JsonArray -> value.joinToString(" · ") { valueSummary(it) }.take(240)
    is JsonObject -> value.values.joinToString(" · ") { valueSummary(it) }.take(240)
    else -> value.toString().take(240)
}
