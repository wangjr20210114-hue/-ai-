package com.floris.android.ui.calendar

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
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
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
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
import com.floris.android.core.model.SkillAccess
import com.floris.android.core.model.SkillAccessStatus
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.SkillAccessNotice
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.pressable
import com.floris.android.ui.calendarViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class CalendarViewModel(
    private val repository: FlorisRepository,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val error: String? = null,
        /** 后台静默刷新中（已有缓存时不遮挡界面）。 */
        val refreshing: Boolean = false,
        val saving: Boolean = false,
        val access: SkillAccess = SkillAccess(CALENDAR_SKILL_ID, SkillAccessStatus.Loading),
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    /** Schedules stream shared with chat confirmations — always backend-confirmed. */
    val schedules = repository.schedulesFlow

    init {
        viewModelScope.launch {
            repository.skillAccessFlow.collect { projection ->
                val access = projection.access(CALENDAR_SKILL_ID)
                val becameAvailable = access.available && !_state.value.access.available
                _state.value = _state.value.copy(
                    access = access,
                    loading = if (access.available) _state.value.loading else false,
                    refreshing = if (access.available) _state.value.refreshing else false,
                )
                if (becameAvailable) refresh()
            }
        }
        viewModelScope.launch {
            runCatching { repository.ensureSkillAccess(repository.activeConversationId()) }
        }
    }

    fun refresh() {
        if (!_state.value.access.available) return
        // 已有后端确认过的日程时不再空屏转圈：先展示旧数据，
        // 新数据到了再无声替换（云函数冷启动可能要好几秒）。
        val hasCache = repository.schedulesFlow.value.isNotEmpty()
        _state.value = _state.value.copy(loading = !hasCache, error = null, refreshing = true)
        viewModelScope.launch {
            runCatching { repository.loadSchedules(repository.activeConversationId()) }
                .onSuccess {
                    repository.schedulesFlow.value = it
                    _state.value = _state.value.copy(
                        loading = false,
                        refreshing = false,
                        error = null,
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        loading = false,
                        refreshing = false,
                        // 有缓存时失败不必打扰用户，继续看旧数据即可。
                        error = if (hasCache) null else strings.get(StringKey.CalendarLoadFailed),
                    )
                }
        }
    }

    fun saveSchedule(
        existingId: String?,
        title: String,
        startTime: Long,
        durationMinutes: Int,
        location: String,
    ) {
        if (title.isBlank() || _state.value.saving || !_state.value.access.available) return
        _state.value = _state.value.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching {
                repository.directCalendarChanges(
                    repository.activeConversationId(),
                    buildJsonArray {
                        add(buildJsonObject {
                            put("operation", if (existingId == null) "create" else "update")
                            existingId?.let { put("schedule_id", it) }
                            put("event", buildJsonObject {
                                put("title", title.trim())
                                put("start_time", startTime)
                                put("duration_minutes", durationMinutes.coerceAtLeast(1))
                                put("category", "other")
                                location.trim().takeIf { it.isNotEmpty() }?.let { put("location", it) }
                            })
                        })
                    },
                )
            }.onSuccess {
                _state.value = _state.value.copy(saving = false)
            }.onFailure {
                _state.value = _state.value.copy(
                    saving = false,
                    error = strings.get(StringKey.CalendarSaveFailed),
                )
            }
        }
    }

    fun deleteSchedule(schedule: Schedule) {
        if (_state.value.saving || !_state.value.access.available) return
        _state.value = _state.value.copy(saving = true, error = null)
        viewModelScope.launch {
            runCatching {
                repository.directCalendarChanges(
                    repository.activeConversationId(),
                    buildJsonArray {
                        add(buildJsonObject {
                            put("operation", "delete")
                            put("schedule_id", schedule.id)
                        })
                    },
                )
            }.onSuccess {
                _state.value = _state.value.copy(saving = false)
            }.onFailure {
                _state.value = _state.value.copy(
                    saving = false,
                    error = strings.get(StringKey.CalendarDeleteFailed),
                )
            }
        }
    }
}

@Composable
fun CalendarScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onRequestLogin: () -> Unit = {},
    onOpenSkills: () -> Unit = {},
) {
    val viewModel: CalendarViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "calendar",
        factory = container.calendarViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val schedules by viewModel.schedules.collectAsState()

    if (!state.access.available) {
        Column(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).statusBarsPadding(),
        ) {
            Text(
                t(StringKey.CalendarTitle),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.padding(start = 20.dp, top = 12.dp, bottom = 12.dp),
            )
            Box(Modifier.padding(horizontal = 16.dp)) {
                SkillAccessNotice(state.access, onRequestLogin, onOpenSkills)
            }
        }
        return
    }

    val today = remember { Calendar.getInstance() }
    var year by remember { mutableIntStateOf(today.get(Calendar.YEAR)) }
    var month by remember { mutableIntStateOf(today.get(Calendar.MONTH)) } // 0-based
    var selectedDay by remember { mutableStateOf(dayKeyOf(today)) }
    var editorOpen by remember { mutableStateOf(false) }
    var editingSchedule by remember { mutableStateOf<Schedule?>(null) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        // 状态栏由 statusBarsPadding 统一处理，避免与 innerPadding 叠加两遍。
        contentWindowInsets = WindowInsets(0),
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .statusBarsPadding(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 6.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = "header") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        t(StringKey.CalendarTitle),
                        style = MaterialTheme.typography.headlineMedium,
                        modifier = Modifier.weight(1f).padding(start = 4.dp, top = 6.dp, bottom = 6.dp),
                    )
                    com.floris.android.ui.components.IconPill(
                        icon = Icons.Default.Add,
                        contentDescription = t(StringKey.CalendarAdd),
                        onClick = {
                            editingSchedule = null
                            editorOpen = true
                        },
                    )
                }
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
                    AnimateIn(0) {
                        ScheduleRow(
                            schedule,
                            onEdit = {
                                editingSchedule = schedule
                                editorOpen = true
                            },
                            onDelete = { viewModel.deleteSchedule(schedule) },
                        )
                    }
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

    if (editorOpen) {
        ScheduleEditorDialog(
            schedule = editingSchedule,
            selectedDay = selectedDay,
            saving = state.saving,
            onDismiss = { editorOpen = false },
            onSave = { title, start, duration, location ->
                viewModel.saveSchedule(editingSchedule?.id, title, start, duration, location)
                editorOpen = false
            },
        )
    }
}

private const val CALENDAR_SKILL_ID = "calendar"

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
                    t(StringKey.CalendarYearMonth, year, month + 1),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                com.floris.android.ui.components.IconPill(
                    icon = Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                    contentDescription = t(StringKey.CalendarPreviousMonth),
                    onClick = onPrevMonth,
                    size = 32.dp,
                    iconSize = 18.dp,
                )
                com.floris.android.ui.components.IconPill(
                    icon = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = t(StringKey.CalendarNextMonth),
                    onClick = onNextMonth,
                    size = 32.dp,
                    iconSize = 18.dp,
                )
            }
            Spacer(Modifier.height(8.dp))
            Row {
                listOf(
                    StringKey.WeekMonday, StringKey.WeekTuesday, StringKey.WeekWednesday,
                    StringKey.WeekThursday, StringKey.WeekFriday, StringKey.WeekSaturday,
                    StringKey.WeekSunday,
                ).forEach { key ->
                    Text(
                        t(key),
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
private fun ScheduleRow(
    schedule: Schedule,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    FlorisCard {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(end = 14.dp),
            ) {
                Text(timeOf(schedule.start_time), style = MaterialTheme.typography.titleMedium)
                val endTime = schedule.end_time.takeIf { it > 0 }
                    ?: schedule.duration_minutes.takeIf { it > 0 }?.let {
                        schedule.start_time + it * 60L
                    }
                if (endTime != null) {
                    Text(
                        timeOf(endTime),
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
                StatusChip(t(StringKey.CalendarOnline), MaterialTheme.colorScheme.secondary)
            }
            com.floris.android.ui.components.IconPill(
                icon = Icons.Default.Edit,
                contentDescription = t(StringKey.CalendarEdit),
                onClick = onEdit,
                size = 32.dp,
                iconSize = 15.dp,
            )
            com.floris.android.ui.components.IconPill(
                icon = Icons.Default.DeleteOutline,
                contentDescription = t(StringKey.CalendarDelete),
                onClick = onDelete,
                size = 32.dp,
                iconSize = 15.dp,
                tint = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun ScheduleEditorDialog(
    schedule: Schedule?,
    selectedDay: String,
    saving: Boolean,
    onDismiss: () -> Unit,
    onSave: (String, Long, Int, String) -> Unit,
) {
    val context = LocalContext.current
    val initialStart = schedule?.start_time?.takeIf { it > 0 } ?: run {
        val day = SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).parse(selectedDay)?.time
            ?: System.currentTimeMillis()
        (day + 9 * 60 * 60 * 1000) / 1000
    }
    var title by remember(schedule?.id) { mutableStateOf(schedule?.title.orEmpty()) }
    var location by remember(schedule?.id) { mutableStateOf(schedule?.location.orEmpty()) }
    var start by remember(schedule?.id, selectedDay) { mutableStateOf(initialStart) }
    var duration by remember(schedule?.id) {
        mutableStateOf((schedule?.duration_minutes ?: 60).coerceAtLeast(1).toString())
    }
    val calendar = remember(start) {
        Calendar.getInstance().apply { timeInMillis = start * 1000 }
    }
    fun chooseDate() {
        DatePickerDialog(
            context,
            { _, year, month, day ->
                val next = Calendar.getInstance().apply {
                    timeInMillis = start * 1000
                    set(year, month, day)
                }
                start = next.timeInMillis / 1000
            },
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH),
            calendar.get(Calendar.DAY_OF_MONTH),
        ).show()
    }
    fun chooseTime() {
        TimePickerDialog(
            context,
            { _, hour, minute ->
                val next = Calendar.getInstance().apply {
                    timeInMillis = start * 1000
                    set(Calendar.HOUR_OF_DAY, hour)
                    set(Calendar.MINUTE, minute)
                    set(Calendar.SECOND, 0)
                }
                start = next.timeInMillis / 1000
            },
            calendar.get(Calendar.HOUR_OF_DAY),
            calendar.get(Calendar.MINUTE),
            true,
        ).show()
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (schedule == null) t(StringKey.CalendarAdd) else t(StringKey.CalendarEdit)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                CalendarField(title, { title = it }, t(StringKey.CalendarEventTitle))
                CalendarField(location, { location = it }, t(StringKey.CalendarLocation))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = ::chooseDate) {
                        Text(SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(Date(start * 1000)))
                    }
                    TextButton(onClick = ::chooseTime) { Text(timeOf(start)) }
                }
                CalendarField(
                    duration,
                    { duration = it.filter(Char::isDigit).take(4) },
                    t(StringKey.CalendarDuration),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = !saving && title.isNotBlank() && duration.toIntOrNull() != null,
                onClick = {
                    onSave(title, start, duration.toIntOrNull() ?: 60, location)
                },
            ) { Text(t(StringKey.CalendarSave)) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t(StringKey.Cancel)) } },
    )
}

@Composable
private fun CalendarField(value: String, onValueChange: (String) -> Unit, hint: String) {
    Box(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
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
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            modifier = Modifier.fillMaxWidth(),
        )
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
