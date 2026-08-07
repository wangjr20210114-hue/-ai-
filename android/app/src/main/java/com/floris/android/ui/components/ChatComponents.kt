package com.floris.android.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.NorthEast
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.floris.android.core.model.Clarification
import com.floris.android.core.model.ExperienceHintItem
import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.Paper
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.ProactiveWorkflow
import com.floris.android.core.model.ProactiveWorkflowStep
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import com.floris.android.core.chat.sourceBoundSegments
import com.floris.android.core.data.str
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import java.net.URI
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ---------- Search results ----------

@Composable
fun SourceBoundAnswer(
    content: String,
    searchMeta: SearchMeta?,
    streaming: Boolean,
) {
    val segments = remember(content, searchMeta) { sourceBoundSegments(content, searchMeta) }
    segments.forEachIndexed { index, segment ->
        if (segment.markdown.isNotEmpty()) {
            MarkdownText(
                markdown = segment.markdown,
                streaming = streaming && index == segments.lastIndex,
            )
        }
        if (segment.media.isNotEmpty()) MediaGrid(segment.media)
    }
}

@Composable
fun SearchSourcesRow(meta: SearchMeta, modifier: Modifier = Modifier) {
    if (meta.results.isEmpty()) return
    val uriHandler = LocalUriHandler.current
    Column(modifier) {
        Text(
            t(StringKey.ChatSourceCount, meta.total.coerceAtLeast(meta.results.size)),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 6.dp),
        )
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(meta.results.take(12), key = { _, s -> s.id }) { index, source ->
                FlorisCard(
                    modifier = Modifier.width(210.dp),
                    corner = 14.dp,
                    onClick = { runCatching { uriHandler.openUri(source.url) } },
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier.size(20.dp).clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.primaryContainer),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    "${index + 1}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                            Spacer(Modifier.width(6.dp))
                            Text(
                                hostOf(source.url),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        Spacer(Modifier.height(6.dp))
                        Text(
                            source.title,
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Medium,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
}

private fun hostOf(url: String): String =
    runCatching { URI(url).host?.removePrefix("www.") ?: url }.getOrDefault(url)

@Composable
fun MediaGrid(media: List<MediaItem>, modifier: Modifier = Modifier) {
    if (media.isEmpty()) return
    val items = media.filter { it.url.isNotEmpty() }.take(6)
    Column(modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(2).forEach { rowItems ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                rowItems.forEach { item ->
                    AsyncImage(
                        model = item.url,
                        contentDescription = item.alt.ifEmpty { item.caption },
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .weight(1f)
                            .aspectRatio(1.4f)
                            .clip(RoundedCornerShape(14.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant),
                    )
                }
                if (rowItems.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

// ---------- Papers ----------

@Composable
fun PaperListCard(papers: List<Paper>, modifier: Modifier = Modifier) {
    if (papers.isEmpty()) return
    val uriHandler = LocalUriHandler.current
    Column(modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        papers.take(5).forEach { paper ->
            FlorisCard(onClick = paper.arxiv_url?.let { url -> { runCatching { uriHandler.openUri(url) } } }) {
                Column(Modifier.padding(14.dp)) {
                    Text(
                        paper.title,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(4.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val meta = listOfNotNull(
                            paper.authors?.split(",")?.take(2)?.joinToString(", "),
                            paper.year?.toString(),
                            paper.citations?.let { t(StringKey.PaperCited, it) },
                        ).joinToString(" · ")
                        Text(
                            meta,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    paper.abstract_zh?.let {
                        Spacer(Modifier.height(6.dp))
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 3,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
}

// ---------- Workspace actions ----------

@Composable
fun WorkspaceActionCard(
    action: WorkspaceAction,
    busy: Boolean,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    onShowMap: () -> Unit,
    onEditImage: (String) -> Unit,
    onUpdateMeeting: (String, String, String) -> Unit,
    onRouteCalendarProposal: () -> Unit,
    hasCalendarProposal: Boolean,
    onSaveImage: () -> Unit,
    savingImage: Boolean,
    modifier: Modifier = Modifier,
) {
    if (!action.isKnownKind) {
        // Unknown action kind: degrade to text + upgrade hint (contract rule).
        FlorisCard(modifier = modifier.padding(top = 8.dp)) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Info, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                Text(
                    action.payload.title ?: t(StringKey.ActionUnknown),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        return
    }

    val accent = when (action.status) {
        "succeeded" -> MaterialTheme.colorScheme.tertiary
        "failed", "cancelled" -> MaterialTheme.colorScheme.error
        "awaiting_confirmation" -> MaterialTheme.colorScheme.secondary
        else -> MaterialTheme.colorScheme.primary
    }
    val statusLabel = when (action.status) {
        "ready" -> t(StringKey.ActionReady)
        "active" -> t(StringKey.ActionActive)
        "awaiting_confirmation" -> t(StringKey.ActionAwaiting)
        "executing" -> t(StringKey.ActionExecuting)
        "succeeded" -> t(StringKey.ActionSucceeded)
        "failed" -> t(StringKey.ActionFailed)
        "cancelled" -> t(StringKey.ActionCancelled)
        "reconciliation_required" -> t(StringKey.ActionNeedsReview)
        else -> action.status
    }

    FlorisCard(modifier = modifier.padding(top = 8.dp)) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    when (action.kind) {
                        "map_recommendation" -> Icons.Default.Place
                        "calendar_changes" -> Icons.Default.DateRange
                        "meeting_create" -> Icons.Default.Star
                        else -> Icons.Default.Star
                    },
                    contentDescription = null,
                    tint = accent,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    action.payload.title ?: kindLabel(action.kind),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                StatusChip(statusLabel, accent)
            }

            action.payload.summary?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            val canConfirm = if (action.kind == "meeting_create") {
                meetingActionBody(action, busy, onUpdateMeeting)
            } else {
                when (action.kind) {
                    "map_recommendation" -> MapActionBody(action)
                    "calendar_changes" -> CalendarActionBody(action)
                    "image_generate" -> ImageActionBody(
                        action,
                        busy,
                        onEditImage,
                        onSaveImage,
                        savingImage,
                    )
                }
                true
            }

            action.error?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
            }
            if (action.kind != "meeting_create") action.payload.warnings.forEach {
                Text("⚠ $it", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary)
            }

            // 地图推荐在 ready/active/awaiting_confirmation 均可操作（网页端同款），
            // 其余动作只在等待确认时提供决策；成功只来自后端确认的状态。
            val mapActionable = action.kind == "map_recommendation" &&
                action.status in setOf("ready", "active", "awaiting_confirmation")
            AnimatedVisibility(visible = action.status == "awaiting_confirmation" || mapActionable) {
                Row(
                    Modifier.padding(top = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (mapActionable) {
                        PillButton(
                            text = action.payload.action_text ?: t(StringKey.MapShowOnMap),
                            onClick = onShowMap,
                            style = PillStyle.Tonal,
                            enabled = !busy,
                            compact = true,
                        )
                        if (action.payload.calendar_offer == true && !hasCalendarProposal) {
                            PillButton(
                                text = t(StringKey.ChatAddSchedule),
                                onClick = onRouteCalendarProposal,
                                style = PillStyle.Tonal,
                                enabled = !busy,
                                compact = true,
                            )
                        }
                    }
                    if (action.status == "awaiting_confirmation") {
                        PillButton(
                            text = if (busy) t(StringKey.Loading) else t(StringKey.Confirm),
                            onClick = onConfirm,
                            enabled = !busy && canConfirm,
                            compact = true,
                        )
                        PillButton(
                            text = t(StringKey.Cancel),
                            onClick = onCancel,
                            style = PillStyle.Ghost,
                            enabled = !busy,
                            compact = true,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun kindLabel(kind: String) = when (kind) {
    "map_recommendation" -> t(StringKey.ActionMapTitle)
    "calendar_changes" -> t(StringKey.ActionCalendarTitle)
    "meeting_create" -> t(StringKey.ActionMeetingTitle)
    "image_generate" -> t(StringKey.ActionImageTitle)
    else -> t(StringKey.ActionWorkspaceTitle)
}

@Composable
private fun MapActionBody(action: WorkspaceAction) {
    if (action.payload.places.isEmpty()) return
    Spacer(Modifier.height(8.dp))
    action.payload.places.take(4).forEach { place ->
        Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.LocationOn, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Column {
                Text(place.name, style = MaterialTheme.typography.labelLarge)
                Text(
                    place.address,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
    action.payload.route_mode?.let {
        Text(
            t(StringKey.ActionRouteMode, routeModeLabel(it)),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

@Composable
fun routeModeLabel(mode: String) = when (mode) {
    "driving" -> t(StringKey.RouteDriving)
    "transit" -> t(StringKey.RouteTransit)
    "walking" -> t(StringKey.RouteWalking)
    "bicycling" -> t(StringKey.RouteBicycling)
    "bus" -> t(StringKey.RouteBus)
    "subway", "metro" -> t(StringKey.RouteSubway)
    "rail", "train" -> t(StringKey.RouteRail)
    else -> mode
}

@Composable
private fun CalendarActionBody(action: WorkspaceAction) {
    if (action.payload.changes.isEmpty()) return
    Spacer(Modifier.height(8.dp))
    action.payload.changes.take(5).forEach { change ->
        val title = change["event"]?.let { (it as? kotlinx.serialization.json.JsonObject) }
            ?.get("title")?.toString()?.trim('"')
            ?: change["title"]?.toString()?.trim('"')
            ?: change["operation"]?.toString()?.trim('"')
            ?: t(StringKey.ActionCalendarTitle)
        val operation = change["operation"]?.toString()?.trim('"') ?: "create"
        Row(Modifier.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            val (label, color) = when (operation) {
                "delete" -> t(StringKey.Delete) to MaterialTheme.colorScheme.error
                "update" -> t(StringKey.CalendarChangeUpdate) to MaterialTheme.colorScheme.secondary
                else -> t(StringKey.CalendarChangeAdd) to MaterialTheme.colorScheme.tertiary
            }
            StatusChip(label, color)
            Spacer(Modifier.width(8.dp))
            Text(title, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun meetingActionBody(
    action: WorkspaceAction,
    busy: Boolean,
    onUpdate: (String, String, String) -> Unit,
): Boolean {
    val payload = action.payload
    val uriHandler = LocalUriHandler.current
    val result = action.result
    if (action.status != "awaiting_confirmation") {
        if (payload.subject == null && payload.start_time == null && result == null) return true
        Spacer(Modifier.height(8.dp))
        payload.subject?.let {
            Text(t(StringKey.MeetingSubject, it), style = MaterialTheme.typography.labelLarge)
        }
        if (payload.start_time != null) {
            Text(
                t(
                    StringKey.MeetingTime,
                    meetingTimeLabel(meetingEpoch(payload.start_time)),
                    meetingTimeLabel(meetingEpoch(payload.end_time)),
                ),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        result?.str("join_url")?.takeIf { it.startsWith("https://") }?.let { joinUrl ->
            Spacer(Modifier.height(8.dp))
            PillButton(
                text = t(StringKey.MeetingJoin),
                onClick = { uriHandler.openUri(joinUrl) },
                compact = true,
            )
        }
        result?.str("meeting_code")?.takeIf { it.isNotBlank() }?.let { code ->
            Spacer(Modifier.height(6.dp))
            Text(
                t(StringKey.MeetingCode, code),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        result?.str("start_time")?.takeIf { it.isNotBlank() }?.let { start ->
            Spacer(Modifier.height(4.dp))
            Text(
                t(StringKey.MeetingStartValue, start),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        result?.str("trace_id")?.takeIf { it.isNotBlank() }?.let { traceId ->
            Spacer(Modifier.height(4.dp))
            Text(
                t(StringKey.TraceId, traceId),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
            )
        }
        return true
    }

    var subject by remember(action.id, action.version) { mutableStateOf(payload.subject.orEmpty()) }
    var startMillis by remember(action.id, action.version) {
        mutableStateOf(meetingEpoch(payload.start_time))
    }
    var endMillis by remember(action.id, action.version) {
        mutableStateOf(meetingEpoch(payload.end_time))
    }
    var pickerTarget by remember(action.id, action.version) { mutableStateOf<String?>(null) }
    var pendingDate by remember(action.id, action.version) { mutableStateOf<LocalDate?>(null) }
    val acknowledged = remember(action.id, action.version) { mutableStateMapOf<String, Boolean>() }

    Spacer(Modifier.height(8.dp))
    Text(t(StringKey.MeetingSubjectLabel), style = MaterialTheme.typography.labelMedium)
    Box(
        Modifier
            .fillMaxWidth()
            .padding(top = 5.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
            .padding(horizontal = 12.dp, vertical = 11.dp),
    ) {
        if (subject.isBlank()) {
            Text(
                t(StringKey.MeetingSubjectLabel),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        BasicTextField(
            value = subject,
            onValueChange = { subject = it.take(120) },
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
            ),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            modifier = Modifier.fillMaxWidth(),
        )
    }

    FlowRow(
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        PillButton(
            text = "${t(StringKey.MeetingStartTime)} · ${meetingTimeLabel(startMillis)}",
            onClick = { pickerTarget = "start"; pendingDate = null },
            style = PillStyle.Tonal,
            compact = true,
            enabled = !busy,
        )
        PillButton(
            text = "${t(StringKey.MeetingEndTime)} · ${meetingTimeLabel(endMillis)}",
            onClick = { pickerTarget = "end"; pendingDate = null },
            style = PillStyle.Tonal,
            compact = true,
            enabled = !busy,
        )
    }

    payload.validation_errors.forEach { message ->
        Text(message, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
    }
    payload.warnings.forEach { warning ->
        SelectRow(
            label = t(StringKey.MeetingAcceptWarning, warning),
            selected = acknowledged[warning] == true,
            multi = true,
            onClick = { acknowledged[warning] = acknowledged[warning] != true },
        )
    }

    val normalizedSubject = subject.trim()
    val timesComplete = startMillis != null && endMillis != null && endMillis!! > startMillis!!
    val dirty = normalizedSubject != payload.subject.orEmpty().trim() ||
        startMillis != meetingEpoch(payload.start_time) || endMillis != meetingEpoch(payload.end_time)
    val needsCheck = dirty || payload.missing_fields.isNotEmpty() || payload.validation_errors.isNotEmpty()
    val warningsAccepted = payload.warnings.all { acknowledged[it] == true }
    if (needsCheck) {
        Spacer(Modifier.height(8.dp))
        PillButton(
            text = t(StringKey.MeetingSaveCheck),
            onClick = {
                onUpdate(
                    normalizedSubject,
                    Instant.ofEpochMilli(startMillis!!).toString(),
                    Instant.ofEpochMilli(endMillis!!).toString(),
                )
            },
            enabled = !busy && normalizedSubject.isNotBlank() && timesComplete,
            compact = true,
        )
    }

    val targetMillis = if (pickerTarget == "end") endMillis else startMillis
    if (pickerTarget != null && pendingDate == null) {
        val initial = targetMillis ?: nextWholeHourMillis()
        val localDate = Instant.ofEpochMilli(initial).atZone(ZoneId.systemDefault()).toLocalDate()
        val initialDateMillis = localDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
        val picker = rememberDatePickerState(initialSelectedDateMillis = initialDateMillis)
        DatePickerDialog(
            onDismissRequest = { pickerTarget = null },
            confirmButton = {
                TextButton(onClick = {
                    pendingDate = picker.selectedDateMillis?.let {
                        Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()
                    } ?: localDate
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { pickerTarget = null }) { Text(t(StringKey.Cancel)) }
            },
        ) { DatePicker(state = picker) }
    }
    pendingDate?.let { date ->
        val initial = Instant.ofEpochMilli(targetMillis ?: nextWholeHourMillis())
            .atZone(ZoneId.systemDefault())
        val picker = rememberTimePickerState(initialHour = initial.hour, initialMinute = initial.minute)
        AlertDialog(
            onDismissRequest = { pickerTarget = null; pendingDate = null },
            confirmButton = {
                TextButton(onClick = {
                    val selected = date.atTime(picker.hour, picker.minute)
                        .atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
                    if (pickerTarget == "end") endMillis = selected else startMillis = selected
                    pickerTarget = null
                    pendingDate = null
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { pickerTarget = null; pendingDate = null }) {
                    Text(t(StringKey.Cancel))
                }
            },
            text = { TimePicker(state = picker) },
        )
    }

    return !needsCheck && timesComplete && warningsAccepted
}

private fun meetingEpoch(value: String?): Long? {
    val source = value?.trim()?.takeIf(String::isNotEmpty) ?: return null
    return runCatching { Instant.parse(source).toEpochMilli() }
        .recoverCatching { OffsetDateTime.parse(source).toInstant().toEpochMilli() }
        .recoverCatching {
            LocalDateTime.parse(source).atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        }
        .getOrNull()
}

private fun meetingTimeLabel(value: Long?): String = value?.let {
    Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault())
        .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm", Locale.ROOT))
} ?: "—"

private fun nextWholeHourMillis(): Long {
    val now = java.time.ZonedDateTime.now(ZoneId.systemDefault())
    return now.plusHours(1).withMinute(0).withSecond(0).withNano(0).toInstant().toEpochMilli()
}

@Composable
private fun ImageActionBody(
    action: WorkspaceAction,
    busy: Boolean,
    onEditImage: (String) -> Unit,
    onSaveImage: () -> Unit,
    savingImage: Boolean,
) {
    action.payload.prompt?.let {
        Spacer(Modifier.height(6.dp))
        Text(
            t(StringKey.ImagePrompt, it),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    if (action.status != "succeeded") return

    val result = action.result ?: return
    fun url(vararg keys: String): String? = keys.firstNotNullOfOrNull { key ->
        (result[key] as? kotlinx.serialization.json.JsonPrimitive)?.content?.takeIf { it.isNotEmpty() }
    }

    val current = url("image_url", "url", "current_url")
    val previous = url("previous_url", "reference_url", "base_url")

    if (previous != null && current != null) {
        // 图片工坊：左右对比（网页端同款）
        Spacer(Modifier.height(8.dp))
        var showNew by remember(action.id) { mutableStateOf(true) }
        Column {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CompareImage(
                    url = previous,
                    label = t(StringKey.ImageOriginal),
                    highlighted = !showNew,
                    modifier = Modifier.weight(1f),
                    onClick = { showNew = false },
                )
                CompareImage(
                    url = current,
                    label = t(StringKey.ImageUpdated),
                    highlighted = showNew,
                    modifier = Modifier.weight(1f),
                    onClick = { showNew = true },
                )
            }
            Spacer(Modifier.height(8.dp))
            AsyncImage(
                model = if (showNew) current else previous,
                contentDescription = action.payload.prompt,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1.1f)
                    .clip(RoundedCornerShape(14.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
            )
        }
    } else if (current != null) {
        Spacer(Modifier.height(8.dp))
        AsyncImage(
            model = current,
            contentDescription = action.payload.prompt,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1.15f)
                .clip(RoundedCornerShape(14.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
        )
    }

    if (current != null) {
        var editPrompt by remember(action.id) { mutableStateOf("") }
        Spacer(Modifier.height(10.dp))
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(14.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .padding(start = 12.dp, end = 5.dp, top = 5.dp, bottom = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier.weight(1f).heightIn(min = 38.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                if (editPrompt.isBlank()) {
                    Text(
                        t(StringKey.ImageEditHint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                BasicTextField(
                    value = editPrompt,
                    onValueChange = { editPrompt = it },
                    textStyle = MaterialTheme.typography.bodySmall.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                    ),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.width(6.dp))
            PillButton(
                text = if (busy) t(StringKey.Loading) else t(StringKey.ImageEditAction),
                onClick = {
                    val value = editPrompt.trim()
                    if (value.isNotEmpty()) {
                        onEditImage(value)
                        editPrompt = ""
                    }
                },
                enabled = !busy && editPrompt.isNotBlank(),
                compact = true,
            )
        }
        Spacer(Modifier.height(8.dp))
        PillButton(
            text = if (savingImage) t(StringKey.Loading) else t(StringKey.ImageSaveToGallery),
            onClick = onSaveImage,
            style = PillStyle.Tonal,
            enabled = !busy && !savingImage,
            compact = true,
        )
    }
}

@Composable
private fun CompareImage(
    url: String,
    label: String,
    highlighted: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Column(
        modifier = modifier.pressable(onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        AsyncImage(
            model = url,
            contentDescription = label,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
        )
        Spacer(Modifier.height(5.dp))
        StatusChip(
            label,
            if (highlighted) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

// ---------- Clarification form ----------

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ClarificationForm(
    clarification: Clarification,
    submitting: Boolean,
    onSubmit: (Map<String, Any>) -> Unit,
    modifier: Modifier = Modifier,
) {
    val answers = remember(clarification.id) { mutableStateMapOf<String, Any>() }
    val customInputs = remember(clarification.id) { mutableStateMapOf<String, Boolean>() }
    var datePickerFor by remember { mutableStateOf<String?>(null) }
    var timePickerFor by remember { mutableStateOf<String?>(null) }

    FlorisCard(modifier = modifier.padding(top = 8.dp)) {
        Column(Modifier.padding(14.dp)) {
            Text(clarification.title, style = MaterialTheme.typography.titleMedium)
            if (clarification.prompt.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    clarification.prompt,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(10.dp))
            clarification.fields.forEach { field ->
                Text(field.label, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 6.dp))
                when (field.type) {
                    "single" -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        field.options.forEach { option ->
                            val value = field.option_values[option] ?: option
                            SelectRow(
                                label = option,
                                selected = customInputs[field.id] != true && answers[field.id] == value,
                                multi = false,
                                onClick = {
                                    customInputs[field.id] = false
                                    answers[field.id] = value
                                },
                            )
                        }
                        if (field.allow_custom_input) {
                            SelectRow(
                                label = t(StringKey.ClarificationCustomPlace),
                                selected = customInputs[field.id] == true,
                                multi = false,
                                onClick = {
                                    customInputs[field.id] = true
                                    answers[field.id] = ""
                                },
                            )
                        }
                        if (customInputs[field.id] == true) {
                            var custom by remember(clarification.id + field.id + "-custom") {
                                mutableStateOf(answers[field.id] as? String ?: "")
                            }
                            Box(
                                Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                                    .padding(horizontal = 12.dp, vertical = 11.dp),
                            ) {
                                if (custom.isEmpty()) {
                                    Text(
                                        field.custom_placeholder
                                            ?: t(StringKey.ClarificationCustomPlaceholder),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                androidx.compose.foundation.text.BasicTextField(
                                    value = custom,
                                    onValueChange = { value ->
                                        custom = value
                                        answers[field.id] = value
                                    },
                                    textStyle = MaterialTheme.typography.bodySmall.copy(
                                        color = MaterialTheme.colorScheme.onSurface,
                                    ),
                                    cursorBrush = androidx.compose.ui.graphics.SolidColor(
                                        MaterialTheme.colorScheme.primary,
                                    ),
                                    modifier = Modifier.fillMaxWidth(),
                                )
                            }
                        }
                    }
                    "multi" -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        field.options.forEach { option ->
                            val value = field.option_values[option] ?: option
                            @Suppress("UNCHECKED_CAST")
                            val selected = (answers[field.id] as? List<String>).orEmpty()
                            SelectRow(
                                label = option,
                                selected = value in selected,
                                multi = true,
                                onClick = {
                                    answers[field.id] =
                                        if (value in selected) selected - value else selected + value
                                },
                            )
                        }
                    }
                    "boolean" -> Row(verticalAlignment = Alignment.CenterVertically) {
                        FlorisSwitch(
                            checked = answers[field.id] as? Boolean ?: false,
                            onCheckedChange = { answers[field.id] = it },
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            if (answers[field.id] as? Boolean == true) {
                                t(StringKey.Yes)
                            } else t(StringKey.No),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    "date", "time", "datetime" -> {
                        PillButton(
                            text = answers[field.id] as? String
                                ?: t(StringKey.SelectValue, field.label),
                            onClick = {
                                if (field.type == "time") timePickerFor = field.id
                                else datePickerFor = field.id
                            },
                            style = PillStyle.Tonal,
                            compact = true,
                        )
                    }
                    else -> {
                        var text by remember(clarification.id + field.id) {
                            mutableStateOf(answers[field.id] as? String ?: "")
                        }
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                                .padding(horizontal = 12.dp, vertical = 11.dp),
                        ) {
                            if (text.isEmpty()) {
                                Text(
                                    field.placeholder ?: t(StringKey.InputPlaceholder),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            androidx.compose.foundation.text.BasicTextField(
                                value = text,
                                onValueChange = { text = it; answers[field.id] = it },
                                textStyle = MaterialTheme.typography.bodySmall.copy(
                                    color = MaterialTheme.colorScheme.onSurface,
                                ),
                                cursorBrush = androidx.compose.ui.graphics.SolidColor(
                                    MaterialTheme.colorScheme.primary,
                                ),
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                PillButton(
                    text = if (submitting) t(StringKey.ClarificationSubmitting)
                    else t(StringKey.ClarificationSubmit),
                    onClick = { onSubmit(answers.toMap()) },
                    enabled = !submitting &&
                        clarification.fields.all { field ->
                            if (!field.required) true else when (val value = answers[field.id]) {
                                is String -> value.isNotBlank()
                                is List<*> -> value.isNotEmpty()
                                null -> false
                                else -> true
                            }
                        },
                    compact = true,
                )
            }
        }
    }

    datePickerFor?.let { fieldId ->
        val state = rememberDatePickerState()
        DatePickerDialog(
            onDismissRequest = { datePickerFor = null },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let {
                        answers[fieldId] = SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(Date(it))
                    }
                    datePickerFor = null
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { datePickerFor = null }) { Text(t(StringKey.Cancel)) }
            },
        ) { DatePicker(state = state) }
    }
    timePickerFor?.let { fieldId ->
        val state = rememberTimePickerState()
        AlertDialog(
            onDismissRequest = { timePickerFor = null },
            confirmButton = {
                TextButton(onClick = {
                    answers[fieldId] = String.format(Locale.ROOT, "%02d:%02d", state.hour, state.minute)
                    timePickerFor = null
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { timePickerFor = null }) { Text(t(StringKey.Cancel)) }
            },
            text = { TimePicker(state = state) },
        )
    }
}

/** 网页端澄清卡同款选择行（radio / checkbox）。 */
@Composable
private fun SelectRow(
    label: String,
    selected: Boolean,
    multi: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(
                if (selected) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
            )
            .pressable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(18.dp)
                .clip(if (multi) RoundedCornerShape(5.dp) else CircleShape)
                .background(
                    if (selected) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.outline,
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) {
                Icon(
                    Icons.Default.Check, contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.size(12.dp),
                )
            }
        }
        Spacer(Modifier.width(10.dp))
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

// ---------- Follow-ups ----------

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FollowUpChips(items: List<String>, onClick: (String) -> Unit, modifier: Modifier = Modifier) {
    if (items.isEmpty()) return
    FlowRow(
        modifier = modifier.fillMaxWidth().padding(top = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        // 必须显式给出垂直间距：FlowRow 默认行间距为 0，
        // 一旦换行两行 chips 会直接贴死重叠在一起。
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items.take(4).forEach { item ->
            val chipShape = RoundedCornerShape(999.dp)
            Box(
                Modifier
                    // 单条最宽不超过容器的八成，避免过长文字把整行挤爆。
                    .widthIn(max = 280.dp)
                    .shadow(4.dp, chipShape, ambientColor = panelShadowColor(), spotColor = panelShadowColor())
                    .clip(chipShape)
                    .background(MaterialTheme.colorScheme.surface)
                    .border(1.dp, panelBorderColor(), chipShape)
                    .pressable { onClick(item) }
                    .padding(horizontal = 14.dp, vertical = 8.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        item,
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    Spacer(Modifier.width(4.dp))
                    // 与快捷输入一致：图标表示"填入输入框"而非直接发送。
                    Icon(
                        Icons.Outlined.NorthEast,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(13.dp),
                    )
                }
            }
        }
    }
}

// ---------- Experience hints ----------

/** 网页端同款“经验提示”：回答后展示时效/技能来源，不包含模型思维链。 */
@Composable
fun ExperienceHints(
    hints: List<ExperienceHintItem>,
    isGuest: Boolean,
    modifier: Modifier = Modifier,
) {
    if (hints.isEmpty()) return
    Column(modifier.fillMaxWidth().padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        hints.forEach { hint ->
            val names = hint.skill_ids.joinToString("、")
            val text = when (hint.kind) {
                "freshness" -> t(
                    if (hint.login_required == true && isGuest) {
                        StringKey.HintFreshnessLogin
                    } else StringKey.HintFreshness,
                )
                "skill" -> t(
                    if (hint.login_required == true && isGuest) {
                        StringKey.HintSkillLogin
                    } else StringKey.HintSkill,
                    names,
                )
                else -> return@forEach
            }
            Text(
                text,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// ---------- In-chat proactive ----------

/** 会话内展示的主动提醒：前 3 条、非 dismissed（与网页端一致）。 */
fun chatProactiveNotifications(state: ProactiveState?): List<ProactiveNotification> =
    state?.notifications.orEmpty()
        .filter { it.status != "dismissed" }
        .take(3)

fun chatAwaitingWorkflows(state: ProactiveState?): List<ProactiveWorkflow> =
    state?.workflows.orEmpty()
        .filter { it.status == "awaiting_confirmation" }

fun chatActiveWorkflows(state: ProactiveState?): List<ProactiveWorkflow> =
    state?.workflows.orEmpty()
        .filter { it.status == "active" }

/** 工作流当前待处理步骤（completed/skipped/compensated 之外的第一个）。 */
fun chatActiveWorkflowStep(workflow: ProactiveWorkflow): ProactiveWorkflowStep? =
    workflow.steps.firstOrNull {
        it.status !in setOf("completed", "skipped", "compensated")
    }

fun chatProactiveHasItems(state: ProactiveState?): Boolean =
    chatProactiveNotifications(state).isNotEmpty() ||
        chatAwaitingWorkflows(state).isNotEmpty() ||
        chatActiveWorkflows(state).isNotEmpty()

/**
 * 会话内主动提醒卡（与网页端 ProactiveRenderer 对应）：
 * 通知（帮我处理 / 一小时后提醒 / 忽略）与长期计划（确认 / 拒绝 / 步骤操作 / 结束）。
 * Maker 负责状态机，客户端只把用户决定原样转发。
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProactiveChatCard(
    state: ProactiveState?,
    busyKey: String?,
    onHandle: (ProactiveNotification) -> Unit,
    onSnooze: (String) -> Unit,
    onDismiss: (String) -> Unit,
    onConfirmWorkflow: (ProactiveWorkflow) -> Unit,
    onRejectWorkflow: (ProactiveWorkflow) -> Unit,
    onCancelWorkflow: (ProactiveWorkflow) -> Unit,
    onStep: (ProactiveWorkflow, ProactiveWorkflowStep, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val notifications = chatProactiveNotifications(state)
    val awaitingWorkflows = chatAwaitingWorkflows(state)
    val activeWorkflows = chatActiveWorkflows(state)
    if (!chatProactiveHasItems(state)) return

    FlorisCard(modifier = modifier.padding(top = 8.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            notifications.forEach { item ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(item.title, style = MaterialTheme.typography.labelLarge)
                    item.body?.takeIf { it.isNotBlank() }?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        PillButton(
                            text = if (busyKey == "read:${item.id}") t(StringKey.Loading)
                            else t(StringKey.ChatProactiveHandle),
                            onClick = { onHandle(item) },
                            compact = true,
                            enabled = busyKey == null || busyKey == "read:${item.id}",
                        )
                        PillButton(
                            text = if (busyKey == "snooze:${item.id}") t(StringKey.Loading)
                            else t(StringKey.ChatProactiveSnooze),
                            onClick = { onSnooze(item.id) },
                            style = PillStyle.Ghost,
                            compact = true,
                            enabled = busyKey == null || busyKey == "snooze:${item.id}",
                        )
                        PillButton(
                            text = if (busyKey == "dismiss:${item.id}") t(StringKey.Loading)
                            else t(StringKey.Ignore),
                            onClick = { onDismiss(item.id) },
                            style = PillStyle.Ghost,
                            compact = true,
                            enabled = busyKey == null || busyKey == "dismiss:${item.id}",
                        )
                    }
                }
            }

            awaitingWorkflows.forEach { workflow ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        t(StringKey.ChatProactiveAwaiting, workflow.title),
                        style = MaterialTheme.typography.labelLarge,
                    )
                    workflow.reason.takeIf { it.isNotBlank() }?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        PillButton(
                            text = if (busyKey == "workflow:${workflow.id}") t(StringKey.Loading)
                            else t(StringKey.WorkflowConfirm),
                            onClick = { onConfirmWorkflow(workflow) },
                            compact = true,
                            enabled = busyKey == null || busyKey == "workflow:${workflow.id}",
                        )
                        PillButton(
                            text = if (busyKey == "reject:${workflow.id}") t(StringKey.Loading)
                            else t(StringKey.WorkflowReject),
                            onClick = { onRejectWorkflow(workflow) },
                            style = PillStyle.Ghost,
                            compact = true,
                            enabled = busyKey == null || busyKey == "reject:${workflow.id}",
                        )
                    }
                }
            }

            activeWorkflows.forEach { workflow ->
                val step = chatActiveWorkflowStep(workflow)
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        t(StringKey.ChatProactiveOngoing, workflow.title),
                        style = MaterialTheme.typography.labelLarge,
                    )
                    Text(
                        step?.let { t(StringKey.ChatProactiveCurrentStep, it.title) }
                            ?: t(StringKey.ChatProactiveSyncing),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        if (step != null) {
                            when (step.status) {
                                "pending", "notified" -> {
                                    PillButton(
                                        text = if (busyKey == "complete_workflow_step:${step.id}")
                                            t(StringKey.Loading) else t(StringKey.WorkflowCompleteStep),
                                        onClick = { onStep(workflow, step, "complete_workflow_step") },
                                        compact = true,
                                        enabled = busyKey == null ||
                                            busyKey == "complete_workflow_step:${step.id}",
                                    )
                                    PillButton(
                                        text = if (busyKey == "skip_workflow_step:${step.id}")
                                            t(StringKey.Loading) else t(StringKey.WorkflowSkipStep),
                                        onClick = { onStep(workflow, step, "skip_workflow_step") },
                                        style = PillStyle.Ghost,
                                        compact = true,
                                        enabled = busyKey == null ||
                                            busyKey == "skip_workflow_step:${step.id}",
                                    )
                                    PillButton(
                                        text = if (busyKey == "fail_workflow_step:${step.id}")
                                            t(StringKey.Loading) else t(StringKey.WorkflowMarkFailed),
                                        onClick = { onStep(workflow, step, "fail_workflow_step") },
                                        style = PillStyle.Ghost,
                                        compact = true,
                                        enabled = busyKey == null ||
                                            busyKey == "fail_workflow_step:${step.id}",
                                    )
                                }
                                "compensating" -> PillButton(
                                    text = if (busyKey == "compensate_workflow_step:${step.id}")
                                        t(StringKey.Loading) else t(StringKey.WorkflowCompensationComplete),
                                    onClick = { onStep(workflow, step, "compensate_workflow_step") },
                                    compact = true,
                                    enabled = busyKey == null ||
                                        busyKey == "compensate_workflow_step:${step.id}",
                                )
                                "failed", "attention_required" -> PillButton(
                                    text = if (busyKey == "retry_workflow_step:${step.id}")
                                        t(StringKey.Loading) else t(StringKey.Retry),
                                    onClick = { onStep(workflow, step, "retry_workflow_step") },
                                    style = PillStyle.Ghost,
                                    compact = true,
                                    enabled = busyKey == null ||
                                        busyKey == "retry_workflow_step:${step.id}",
                                )
                            }
                        }
                        PillButton(
                            text = if (busyKey == "cancel:${workflow.id}") t(StringKey.Loading)
                            else t(StringKey.WorkflowCancel),
                            onClick = { onCancelWorkflow(workflow) },
                            style = PillStyle.Ghost,
                            compact = true,
                            enabled = busyKey == null || busyKey == "cancel:${workflow.id}",
                        )
                    }
                }
            }
        }
    }
}
