package com.floris.android.ui.calendar

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.Schedule
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.calendarViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class CalendarViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class UiState(val loading: Boolean = true, val error: String? = null)

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    /** Schedules stream shared with chat confirmations — always backend-confirmed. */
    val schedules = repository.schedulesFlow

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            runCatching { repository.loadSchedules(repository.activeConversationId()) }
                .onSuccess { repository.schedulesFlow.value = it; _state.value = UiState(loading = false) }
                .onFailure { _state.value = UiState(loading = false, error = "日程加载失败") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CalendarScreen(container: AppContainer) {
    val viewModel: CalendarViewModel = viewModel(factory = container.calendarViewModelFactory())
    val state by viewModel.state.collectAsState()
    val schedules by viewModel.schedules.collectAsState()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text("日程") },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        when {
            state.loading && schedules.isEmpty() ->
                androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().padding(padding)) { InlineLoading() }
            schedules.isEmpty() -> androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().padding(padding)) {
                EmptyState("暂无日程", "在聊天中让 Floris 帮你安排，确认后会出现在这里")
            }
            else -> {
                val grouped = schedules
                    .sortedBy { it.start_time }
                    .groupBy { dayKey(it.start_time) }
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(bottom = 32.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    grouped.forEach { (day, items) ->
                        item(key = "day-$day") { SectionHeader(day) }
                        items(items, key = { it.id }) { schedule ->
                            AnimateIn(0) {
                                ScheduleRow(schedule, Modifier.padding(horizontal = 16.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ScheduleRow(schedule: Schedule, modifier: Modifier = Modifier) {
    FlorisCard(modifier = modifier) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(end = 14.dp),
            ) {
                Text(timeOf(schedule.start_time), style = MaterialTheme.typography.titleMedium)
                if (schedule.end_time > 0) {
                    Text(
                        timeOf(schedule.end_time),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Column(Modifier.weight(1f)) {
                Text(schedule.title, style = MaterialTheme.typography.titleMedium)
                schedule.location?.let {
                    Spacer(Modifier.height(3.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.LocationOn, null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(13.dp),
                        )
                        Text(
                            it,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                schedule.notes?.let {
                    Spacer(Modifier.height(3.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (schedule.location_kind == "online") {
                StatusChip("线上", MaterialTheme.colorScheme.secondary)
            }
        }
    }
}

private fun dayKey(epochSeconds: Long): String {
    val millis = if (epochSeconds < 10_000_000_000L) epochSeconds * 1000 else epochSeconds
    val date = Date(millis)
    val today = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    val key = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(date)
    val label = SimpleDateFormat("M月d日 EEEE", Locale.CHINESE).format(date)
    return if (key == today) "今天 · $label" else label
}

private fun timeOf(epochSeconds: Long): String {
    val millis = if (epochSeconds < 10_000_000_000L) epochSeconds * 1000 else epochSeconds
    return SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(millis))
}
