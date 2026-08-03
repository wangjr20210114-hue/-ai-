package com.floris.android.ui.chat

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.PermissionChecker
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.AuroraOrb
import com.floris.android.ui.components.ClarificationForm
import com.floris.android.ui.components.FollowUpChips
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.MediaGrid
import com.floris.android.ui.components.PaperListCard
import com.floris.android.ui.components.ProgressBar
import com.floris.android.ui.components.SearchSourcesRow
import com.floris.android.ui.components.WorkspaceActionCard
import com.floris.android.ui.components.pressable
import com.floris.android.ui.chatViewModelFactory
import kotlinx.coroutines.launch

private val suggestions = listOf(
    "今天有哪些值得关注的 AI 新闻？",
    "帮我规划一条北京两日游路线",
    "检索 Transformer 相关的最新论文",
    "明天上午 10 点提醒我开项目会",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    container: AppContainer,
    onOpenHistory: () -> Unit,
    onOpenMap: () -> Unit,
) {
    val viewModel: ChatViewModel = viewModel(factory = container.chatViewModelFactory())
    val state by viewModel.state.collectAsState()
    val listState = rememberLazyListState()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = androidx.compose.runtime.rememberCoroutineScope()

    var draft by remember { mutableStateOf("") }
    var images by remember { mutableStateOf<List<String>>(emptyList()) }

    val pickImages = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(3),
    ) { uris ->
        uris.take(3).forEach { uri ->
            // Compression happens off the main thread inside the repository.
            scope.launch {
                container.repository.imageToDataUrl(uri)?.let { dataUrl ->
                    images = (images + dataUrl).take(3)
                }
            }
        }
    }

    val locationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants ->
        if (grants.values.any { it }) {
            lastKnownLocation(context)?.let { (lat, lng) -> viewModel.provideLocation(lat, lng) }
                ?: viewModel.dismissLocationRequest()
        } else {
            viewModel.dismissLocationRequest()
        }
    }

    LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.content?.length) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.size - 1)
        }
    }
    LaunchedEffect(state.transientError) {
        state.transientError?.let { snackbar.showSnackbar(it); viewModel.consumeError() }
    }
    LaunchedEffect(state.locationRequestReason) {
        if (state.locationRequestReason != null && hasLocationPermission(context)) {
            lastKnownLocation(context)?.let { (lat, lng) -> viewModel.provideLocation(lat, lng) }
        }
    }

    if (state.locationRequestReason != null && !hasLocationPermission(context)) {
        AlertDialog(
            onDismissRequest = viewModel::dismissLocationRequest,
            title = { Text("需要你的位置") },
            text = { Text(state.locationRequestReason ?: "Floris 希望使用当前位置来提供更准确的结果。") },
            confirmButton = {
                TextButton(onClick = {
                    locationPermission.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                        ),
                    )
                }) { Text("允许") }
            },
            dismissButton = { TextButton(onClick = viewModel::dismissLocationRequest) { Text("暂不") } },
        )
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            LargeTopAppBar(
                title = { Text("Floris") },
                actions = {
                    IconButton(onClick = onOpenHistory) { Icon(Icons.Default.List, contentDescription = "历史记录") }
                    IconButton(onClick = viewModel::newConversation) { Icon(Icons.Default.AddCircle, contentDescription = "新对话") }
                },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding(),
        ) {
            if (state.bootstrapping) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                }
            } else if (state.messages.isEmpty()) {
                ChatEmptyState(
                    modifier = Modifier.weight(1f),
                    onSuggestion = { draft = it },
                )
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    itemsIndexed(state.messages, key = { _, m -> m.id }) { index, message ->
                        AnimateIn(index) {
                            when (message.role) {
                                ChatMessageUi.Role.USER -> UserBubble(message)
                                ChatMessageUi.Role.AI -> AssistantMessage(
                                    message = message,
                                    busyActionId = state.busyActionId,
                                    submittingClarification = state.submittingClarification,
                                    onConfirm = viewModel::confirmAction,
                                    onCancel = viewModel::cancelAction,
                                    onShowMap = { action ->
                                        viewModel.activateMap(action)
                                        onOpenMap()
                                    },
                                    onClarificationSubmit = { clarification, answers ->
                                        viewModel.submitClarification(clarification, answers)
                                    },
                                    onFollowUp = { viewModel.send(it) },
                                    onRetry = viewModel::retryLast,
                                )
                            }
                        }
                    }
                }
            }

            InputBar(
                draft = draft,
                onDraftChange = { draft = it },
                imageCount = images.size,
                streaming = state.streaming,
                onPickImages = {
                    pickImages.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                    )
                },
                onClearImages = { images = emptyList() },
                onSend = {
                    viewModel.send(draft, images)
                    draft = ""
                    images = emptyList()
                },
                onStop = viewModel::stop,
            )
        }
    }
}

@Composable
private fun ChatEmptyState(modifier: Modifier, onSuggestion: (String) -> Unit) {
    Column(
        modifier = modifier.fillMaxWidth().padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        AuroraOrb(size = 88.dp)
        Spacer(Modifier.height(24.dp))
        Text("你好，我是 Floris", style = MaterialTheme.typography.headlineLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            "搜索、路线、日程、论文，一站式搞定",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(32.dp))
        suggestions.forEach { suggestion ->
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(MaterialTheme.colorScheme.surface)
                    .pressable { onSuggestion(suggestion) }
                    .padding(horizontal = 16.dp, vertical = 13.dp),
            ) {
                Text(suggestion, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun UserBubble(message: ChatMessageUi) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Box(
            Modifier
                .widthIn(max = 300.dp)
                .clip(
                    RoundedCornerShape(
                        topStart = 20.dp, topEnd = 20.dp,
                        bottomStart = 20.dp, bottomEnd = 6.dp,
                    ),
                )
                .background(MaterialTheme.colorScheme.primary)
                .padding(horizontal = 16.dp, vertical = 11.dp),
        ) {
            Text(
                message.content,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

@Composable
private fun AssistantMessage(
    message: ChatMessageUi,
    busyActionId: String?,
    submittingClarification: Boolean,
    onConfirm: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onCancel: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onShowMap: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onClarificationSubmit: (com.floris.android.core.model.Clarification, Map<String, Any>) -> Unit,
    onFollowUp: (String) -> Unit,
    onRetry: () -> Unit,
) {
    Column(Modifier.fillMaxWidth()) {
        message.progress?.let { progress ->
            if (message.streaming || progress.status != "active") {
                ProgressBar(progress)
            }
        }
        if (message.streaming && message.content.isBlank() && message.progress == null) {
            ProgressBar(
                com.floris.android.core.model.ProgressComponent(activity = "general"),
            )
        }
        if (message.content.isNotBlank() || message.streaming) {
            MarkdownText(
                markdown = message.content,
                streaming = message.streaming && message.content.isNotBlank(),
            )
        }
        message.searchResults?.let { meta ->
            if (meta.results.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                SearchSourcesRow(meta)
            }
            if (meta.media.isNotEmpty()) MediaGrid(meta.media)
        }
        PaperListCard(message.papers)
        message.actions.forEach { action ->
            WorkspaceActionCard(
                action = action,
                busy = busyActionId == action.id,
                onConfirm = { onConfirm(action) },
                onCancel = { onCancel(action) },
                onShowMap = { onShowMap(action) },
            )
        }
        message.clarification?.let { clarification ->
            ClarificationForm(
                clarification = clarification,
                submitting = submittingClarification,
                onSubmit = { answers -> onClarificationSubmit(clarification, answers) },
            )
        }
        if (message.failed) {
            Row(
                Modifier.padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    message.error ?: "出错了",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.error,
                )
                Spacer(Modifier.width(8.dp))
                Row(Modifier.pressable(onClick = onRetry), verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.Refresh, contentDescription = "重试",
                        tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp),
                    )
                    Text("重试", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                }
            }
        }
        if (!message.streaming) {
            FollowUpChips(message.followUps, onClick = onFollowUp)
        }
    }
}

@Composable
private fun InputBar(
    draft: String,
    onDraftChange: (String) -> Unit,
    imageCount: Int,
    streaming: Boolean,
    onPickImages: () -> Unit,
    onClearImages: () -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Box(
            Modifier
                .size(38.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surface)
                .pressable(onClick = onPickImages),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Default.Add, contentDescription = "添加图片", tint = MaterialTheme.colorScheme.primary)
        }
        Spacer(Modifier.width(8.dp))
        TextField(
            value = draft,
            onValueChange = onDraftChange,
            placeholder = {
                Text(
                    if (imageCount > 0) "已附 $imageCount 张图片，说点什么…（长按取消）" else "问问 Floris…",
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Start,
                )
            },
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.Sentences,
                imeAction = ImeAction.Default,
            ),
            maxLines = 5,
            shape = RoundedCornerShape(22.dp),
            colors = TextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surface,
                unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
            ),
            modifier = Modifier.weight(1f),
        )
        Spacer(Modifier.width(8.dp))
        Box(
            Modifier
                .size(38.dp)
                .clip(CircleShape)
                .background(
                    if (streaming) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary,
                )
                .pressable { if (streaming) onStop() else if (draft.isNotBlank()) onSend() },
            contentAlignment = Alignment.Center,
        ) {
            if (streaming) {
                Icon(Icons.Default.Close, contentDescription = "停止", tint = MaterialTheme.colorScheme.onPrimary)
            } else {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "发送", tint = MaterialTheme.colorScheme.onPrimary)
            }
        }
    }
}

private fun hasLocationPermission(context: Context): Boolean =
    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
        PermissionChecker.PERMISSION_GRANTED ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
        PermissionChecker.PERMISSION_GRANTED

@SuppressLint("MissingPermission")
private fun lastKnownLocation(context: Context): Pair<Double, Double>? {
    if (!hasLocationPermission(context)) return null
    val manager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
    val location = manager.getProviders(true)
        .mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
        .maxByOrNull { it.time }
    return location?.let { it.latitude to it.longitude }
}
