package com.floris.android.ui.calendar

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
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
import com.floris.android.ui.components.pressable
import com.floris.android.ui.calendarViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
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

private val weekLabels = listOf("一", "二", "三", "四", "五", "六", "日")

@Composable
fun CalendarScreen(container: AppContainer, owner: ViewModelStoreOwner? = null) {
    val viewModel: CalendarViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "calendar",
        factory = container.calendarViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val schedules by viewModel.schedules.collectAsState()

    val today = remember { Calendar.getInstance() }
    var year by remember { mutableIntStateOf(today.get(Calendar.YEAR)) }
    var month by remember { mutableIntStateOf(today.get(Calendar.MONTH)) } // 0-based
    var selectedDay by remember { mutableStateOf(dayKeyOf(today)) }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .statusBarsPadding(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 6.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = "header") {
                Text(
                    t(StringKey.CalendarTitle),
                    style = MaterialTheme.typography.headlineMedium,
                    modifier = Modifier.padding(start = 4.dp, top = 6.dp, bottom = 6.dp),
                )
            }
            item(key = "month") {
                MonthCard(
                    year = year,
                    month = month,
                    schedules = schedules,
                    selectedDay = selectedDay,
                    onSelectDay = { selectedDay = it },
                    onPrevMonth = {
                        if (month == 0) { year--; month = 11 } else month--
                    },
                    onNextMonth = {
                        if (month == 11) { year++; month = 0 } else month++
                    },
                )
            }
            val daySchedules = schedules
                .filter { dayKey(it.start_time) == selectedDay }
                .sortedBy { it.start_time }
            item(key = "day-header") {
                SectionHeader(if (selectedDay == dayKeyOf(today)) t(StringKey.CalendarToday) else selectedDay)
            }
            if (daySchedules.isEmpty()) {
                item(key = "day-empty") {
                    FlorisCard {
                        Text(
                            t(StringKey.CalendarDayEmpty),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(16.dp),
                        )
                    }
                }
            } else {
                items(daySchedules, key = { it.id }) { schedule ->
                    AnimateIn(0) { ScheduleRow(schedule) }
                }
            }
            if (state.loading && schedules.isEmpty()) {
                item { InlineLoading() }
            }
            if (!state.loading && schedules.isEmpty()) {
                item(key = "all-empty") {
                    EmptyState(t(StringKey.CalendarEmptyTitle), t(StringKey.CalendarEmptyBody))
                }
            }
        }
    }
}

@Composable
private fun MonthCard(
    year: Int,
    month: Int,
    schedules: List<Schedule>,
    selectedDay: String,
    onSelectDay: (String) -> Unit,
    onPrevMonth: () -> Unit,
    onNextMonth: () -> Unit,
) {
    val eventDays = remember(schedules, year, month) {
        schedules.map { dayKey(it.start_time) }.toSet()
    }
    val todayKey = dayKeyOf(Calendar.getInstance())

    FlorisCard {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${year}年${month + 1}月",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                com.floris.android.ui.components.IconPill(
                    icon = Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                    contentDescription = "上月",
                    onClick = onPrevMonth,
                    size = 32.dp,
                    iconSize = 18.dp,
                )
                com.floris.android.ui.components.IconPill(
                    icon = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = "下月",
                    onClick = onNextMonth,
                    size = 32.dp,
                    iconSize = 18.dp,
                )
            }
            Spacer(Modifier.height(8.dp))
            Row {
                weekLabels.forEach { label ->
                    Text(
                        label,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            Spacer(Modifier.height(6.dp))

            val cal = Calendar.getInstance().apply {
                set(Calendar.YEAR, year)
                set(Calendar.MONTH, month)
                set(Calendar.DAY_OF_MONTH, 1)
            }
            // Monday-first offset
            val firstOffset = (cal.get(Calendar.DAY_OF_WEEK) + 5) % 7
            val daysInMonth = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
            val cells = firstOffset + daysInMonth
            val rows = (cells + 6) / 7

            for (row in 0 until rows) {
                Row {
                    for (col in 0..6) {
                        val day = row * 7 + col - firstOffset + 1
                        if (day < 1 || day > daysInMonth) {
                            Spacer(Modifier.weight(1f))
                        } else {
                            val key = "%04d-%02d-%02d".format(year, month + 1, day)
                            val hasEvent = key in eventDays
                            val isToday = key == todayKey
                            val isSelected = key == selectedDay
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .aspectRatio(1f)
                                    .padding(2.dp)
                                    .clip(CircleShape)
                                    .background(
                                        when {
                                            isSelected -> MaterialTheme.colorScheme.primary
                                            isToday -> MaterialTheme.colorScheme.primaryContainer
                                            else -> androidx.compose.ui.graphics.Color.Transparent
                                        },
                                    )
                                    .pressable { onSelectDay(key) },
                                contentAlignment = Alignment.Center,
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(
                                        "$day",
                                        style = MaterialTheme.typography.labelLarge,
                                        fontWeight = if (isToday || isSelected) FontWeight.Bold else FontWeight.Normal,
                                        color = when {
                                            isSelected -> MaterialTheme.colorScheme.onPrimary
                                            isToday -> MaterialTheme.colorScheme.onPrimaryContainer
                                            else -> MaterialTheme.colorScheme.onSurface
                                        },
                                    )
                                    if (hasEvent && !isSelected) {
                                        Box(
                                            Modifier
                                                .size(4.dp)
                                                .clip(CircleShape)
                                                .background(
                                                    if (isToday) MaterialTheme.colorScheme.primary
                                                    else MaterialTheme.colorScheme.primary.copy(alpha = 0.7f),
                                                ),
                                        )
                                    } else {
                                        Spacer(Modifier.height(4.dp))
                                    }
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
private fun ScheduleRow(schedule: Schedule) {
    FlorisCard {
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
                        Spacer(Modifier.width(2.dp))
                        Text(
                            it,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
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
    return SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(Date(millis))
}

private fun dayKeyOf(cal: Calendar): String =
    "%04d-%02d-%02d".format(
        cal.get(Calendar.YEAR),
        cal.get(Calendar.MONTH) + 1,
        cal.get(Calendar.DAY_OF_MONTH),
    )

private fun timeOf(epochSeconds: Long): String {
    val millis = if (epochSeconds < 10_000_000_000L) epochSeconds * 1000 else epochSeconds
    return SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(millis))
}
