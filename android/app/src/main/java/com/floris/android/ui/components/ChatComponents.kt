package com.floris.android.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.floris.android.core.model.Clarification
import com.floris.android.core.model.MediaItem
import com.floris.android.core.model.Paper
import com.floris.android.core.model.ProgressComponent
import com.floris.android.core.model.SearchMeta
import com.floris.android.core.model.WorkspaceAction
import java.net.URI
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ---------- Progress ----------

private val stageLabels = mapOf(
    "planning" to "正在规划",
    "retrieval" to "正在检索",
    "verification" to "正在核实",
    "synthesis" to "正在整合",
    "finalizing" to "正在完成",
    "complete" to "已完成",
)

private val activityLabels = mapOf(
    "general" to "思考",
    "web_search" to "联网搜索",
    "paper_search" to "论文检索",
    "place_search" to "地点查询",
    "route_planning" to "路线规划",
    "calendar_preparation" to "日程准备",
    "meeting_preparation" to "会议准备",
    "image_generation" to "图片生成",
    "image_review" to "图片审核",
    "component_action" to "组件操作",
)

@Composable
fun ProgressBar(progress: ProgressComponent, modifier: Modifier = Modifier) {
    val label = stageLabels[progress.stage] ?: progress.stage
    val activity = activityLabels[progress.activity] ?: progress.activity
    Row(
        modifier = modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (progress.status == "active") {
            ShimmerBox(Modifier.size(16.dp), corner = 8.dp)
        } else {
            Box(
                Modifier.size(16.dp).clip(CircleShape)
                    .background(MaterialTheme.colorScheme.tertiary.copy(alpha = 0.2f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Default.Check, contentDescription = null,
                    tint = MaterialTheme.colorScheme.tertiary, modifier = Modifier.size(11.dp),
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        AnimatedContent(
            targetState = "$label · $activity",
            transitionSpec = { fadeIn() togetherWith fadeOut() },
            label = "stage",
        ) { text ->
            Text(text, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ---------- Search results ----------

@Composable
fun SearchSourcesRow(meta: SearchMeta, modifier: Modifier = Modifier) {
    if (meta.results.isEmpty()) return
    val uriHandler = LocalUriHandler.current
    Column(modifier) {
        Text(
            "来源 · ${meta.total.coerceAtLeast(meta.results.size)}",
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
                            paper.citations?.let { "被引 $it" },
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
    modifier: Modifier = Modifier,
) {
    if (!action.isKnownKind) {
        // Unknown action kind: degrade to text + upgrade hint (contract rule).
        FlorisCard(modifier = modifier.padding(top = 8.dp)) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Info, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                Text(
                    action.payload.title ?: "收到新版组件，请升级客户端查看",
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
        "ready" -> "待处理"
        "active" -> "进行中"
        "awaiting_confirmation" -> "待确认"
        "executing" -> "执行中"
        "succeeded" -> "已完成"
        "failed" -> "失败"
        "cancelled" -> "已取消"
        "reconciliation_required" -> "需要核对"
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

            when (action.kind) {
                "map_recommendation" -> MapActionBody(action)
                "calendar_changes" -> CalendarActionBody(action)
                "meeting_create" -> MeetingActionBody(action)
                "image_generate" -> ImageActionBody(action)
            }

            action.error?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
            }
            action.payload.warnings.forEach {
                Text("⚠ $it", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary)
            }

            // Only awaiting_confirmation actions offer decisions, and success
            // is rendered exclusively from the backend-confirmed status.
            AnimatedVisibility(visible = action.status == "awaiting_confirmation") {
                Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (action.kind == "map_recommendation") {
                        OutlinedButton(
                            onClick = onShowMap,
                            enabled = !busy,
                            modifier = Modifier.weight(1f),
                        ) { Text(action.payload.action_text ?: "在地图显示") }
                    }
                    Button(
                        onClick = onConfirm,
                        enabled = !busy,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                    ) { Text(if (busy) "处理中…" else "确认") }
                    OutlinedButton(onClick = onCancel, enabled = !busy) { Text("取消") }
                }
            }
        }
    }
}

private fun kindLabel(kind: String) = when (kind) {
    "map_recommendation" -> "地图推荐"
    "calendar_changes" -> "日程变更"
    "meeting_create" -> "会议"
    "image_generate" -> "图片生成"
    else -> "工作区操作"
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
            "路线方式：" + routeModeLabel(it),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

fun routeModeLabel(mode: String) = when (mode) {
    "driving" -> "驾车"
    "transit" -> "公交"
    "walking" -> "步行"
    "bicycling" -> "骑行"
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
            ?: "日程变更"
        val operation = change["operation"]?.toString()?.trim('"') ?: "create"
        Row(Modifier.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            val (label, color) = when (operation) {
                "delete" -> "删除" to MaterialTheme.colorScheme.error
                "update" -> "更新" to MaterialTheme.colorScheme.secondary
                else -> "新增" to MaterialTheme.colorScheme.tertiary
            }
            StatusChip(label, color)
            Spacer(Modifier.width(8.dp))
            Text(title, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun MeetingActionBody(action: WorkspaceAction) {
    val payload = action.payload
    if (payload.subject == null && payload.start_time == null) return
    Spacer(Modifier.height(8.dp))
    payload.subject?.let { Text("主题：$it", style = MaterialTheme.typography.labelLarge) }
    if (payload.start_time != null) {
        Text(
            "时间：${payload.start_time} ~ ${payload.end_time ?: "未定"}",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ImageActionBody(action: WorkspaceAction) {
    action.payload.prompt?.let {
        Spacer(Modifier.height(6.dp))
        Text("提示词：$it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    val imageUrl = action.result?.get("image_url")?.toString()?.trim('"')
        ?: action.result?.get("url")?.toString()?.trim('"')
    if (action.status == "succeeded" && !imageUrl.isNullOrEmpty()) {
        Spacer(Modifier.height(8.dp))
        AsyncImage(
            model = imageUrl,
            contentDescription = action.payload.prompt,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxWidth().aspectRatio(1.2f).clip(RoundedCornerShape(12.dp)),
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
                    "single" -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        field.options.forEach { option ->
                            val value = field.option_values[option] ?: option
                            FilterChip(
                                selected = answers[field.id] == value,
                                onClick = { answers[field.id] = value },
                                label = { Text(option) },
                            )
                        }
                    }
                    "multi" -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        field.options.forEach { option ->
                            val value = field.option_values[option] ?: option
                            @Suppress("UNCHECKED_CAST")
                            val selected = (answers[field.id] as? List<String>).orEmpty()
                            FilterChip(
                                selected = value in selected,
                                onClick = {
                                    answers[field.id] =
                                        if (value in selected) selected - value else selected + value
                                },
                                label = { Text(option) },
                            )
                        }
                    }
                    "boolean" -> Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(
                            checked = answers[field.id] as? Boolean ?: false,
                            onCheckedChange = { answers[field.id] = it },
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (answers[field.id] as? Boolean == true) "是" else "否",
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                    "date", "time", "datetime" -> {
                        OutlinedButton(onClick = {
                            if (field.type == "time") timePickerFor = field.id else datePickerFor = field.id
                        }) {
                            Text(answers[field.id] as? String ?: "选择" + field.label)
                        }
                    }
                    else -> {
                        var text by remember(clarification.id + field.id) {
                            mutableStateOf(answers[field.id] as? String ?: "")
                        }
                        OutlinedTextField(
                            value = text,
                            onValueChange = { text = it; answers[field.id] = it },
                            placeholder = { field.placeholder?.let { Text(it) } },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                        )
                    }
                }
                Spacer(Modifier.height(10.dp))
            }
            Button(
                onClick = { onSubmit(answers.toMap()) },
                enabled = !submitting && clarification.fields.all { !it.required || answers.containsKey(it.id) },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (submitting) "提交中…" else "提交") }
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
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { datePickerFor = null }) { Text("取消") } },
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
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { timePickerFor = null }) { Text("取消") } },
            text = { TimePicker(state = state) },
        )
    }
}

// ---------- Follow-ups ----------

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FollowUpChips(items: List<String>, onClick: (String) -> Unit, modifier: Modifier = Modifier) {
    if (items.isEmpty()) return
    FlowRow(
        modifier = modifier.padding(top = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items.take(4).forEach { item ->
            Box(
                Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer)
                    .pressable { onClick(item) }
                    .padding(horizontal = 14.dp, vertical = 8.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        item,
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowForward,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.size(14.dp).padding(start = 2.dp),
                    )
                }
            }
        }
    }
}

// ---------- List entrance animation ----------

@Composable
fun AnimateIn(index: Int, content: @Composable () -> Unit) {
    AnimatedVisibility(
        visible = true,
        enter = fadeIn() + slideInVertically(initialOffsetY = { it / 6 }),
    ) { content() }
}
