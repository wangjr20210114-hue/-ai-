package com.floris.android.ui.chat

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AddCircleOutline
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SaveAlt
import androidx.compose.material.icons.outlined.AddCircle
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.NorthEast
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.PermissionChecker
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.core.chat.ChatMessageUi
import com.floris.android.core.share.ImageSaver
import com.floris.android.core.share.MarkdownPlainText
import com.floris.android.ui.chatViewModelFactory
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.ClarificationForm
import com.floris.android.ui.components.FollowUpChips
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.MediaGrid
import com.floris.android.ui.components.PaperListCard
import com.floris.android.ui.components.PrimaryIconButton
import com.floris.android.ui.components.QuotePill
import com.floris.android.ui.components.ImageCreationProgress
import com.floris.android.ui.components.SearchCompleteMeta
import com.floris.android.ui.components.SearchProgress
import com.floris.android.ui.components.SearchSourcesRow
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.WorkspaceActionCard
import com.floris.android.ui.components.pressable
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import com.floris.android.ui.theme.LocalDarkTheme
import com.floris.android.ui.theme.userBubbleBrush
import kotlinx.coroutines.launch

@Composable
fun ChatScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onOpenHistory: () -> Unit,
    onOpenMap: () -> Unit,
) {
    val viewModel: ChatViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "chat",
        factory = container.chatViewModelFactory(),
    )
    val state by viewModel.state.collectAsState()
    val listState = rememberLazyListState()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var draft by remember { mutableStateOf("") }
    var images by remember { mutableStateOf<List<String>>(emptyList()) }

    val pickImages = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(3),
    ) { uris ->
        uris.take(3).forEach { uri ->
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
    // 从主动提醒"去处理"跳转过来时，把话术填进输入框（不自动发送）。
    val pendingDraft by container.repository.pendingDraftFlow.collectAsState()
    LaunchedEffect(pendingDraft) {
        pendingDraft?.let {
            draft = it
            container.repository.pendingDraftFlow.value = null
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
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = viewModel::dismissLocationRequest) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    val dark = LocalDarkTheme.current

    Box(Modifier.fillMaxSize()) {
        // 网页端同款橘猫皮肤 + 暖色柔光遮罩
        Image(
            painter = painterResource(
                if (dark) R.drawable.floris_chat_dark else R.drawable.floris_chat_light,
            ),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(if (dark) Color(0xD1100C1D) else Color(0xD6FFFDF9)),
        )

        Scaffold(
            containerColor = Color.Transparent,
            snackbarHost = { SnackbarHost(snackbar) },
            // 自己用 statusBarsPadding 处理状态栏，若再叠加 Scaffold 的
            // innerPadding 会把状态栏高度算两遍，顶部凭空多出一大块空白。
            contentWindowInsets = WindowInsets(0),
        ) { padding ->
            Column(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .statusBarsPadding()
                    .imePadding(),
            ) {
                ChatTopBar(
                    onNewChat = viewModel::newConversation,
                    onOpenHistory = onOpenHistory,
                )

                Box(Modifier.weight(1f).fillMaxWidth()) {
                    when {
                        state.bootstrapping -> CircularProgressIndicator(
                            Modifier.align(Alignment.Center).size(22.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.primary,
                        )

                        state.messages.isEmpty() -> ChatEmptyState(
                            // 不再用 align(Center)：内容比容器高时会被上下裁掉，
                            // 表现为最后一条快捷输入被压扁。改为可滚动的完整布局。
                            modifier = Modifier.fillMaxSize(),
                            // 快捷输入只填进输入框，由用户决定何时发送。
                            onSuggestion = { draft = it },
                        )

                        else -> LazyColumn(
                            state = listState,
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 12.dp),
                            verticalArrangement = Arrangement.spacedBy(18.dp),
                        ) {
                            itemsIndexed(state.messages, key = { _, m -> m.id }) { index, message ->
                                AnimateIn(index) {
                                    when (message.role) {
                                        ChatMessageUi.Role.USER -> UserRow(message)
                                        ChatMessageUi.Role.AI -> AssistantRow(
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
                                            // 追问同样只填进输入框，用户可以先改再发。
                                            onFollowUp = { draft = it },
                                            onRetry = viewModel::retryLast,
                                            onNotify = { text ->
                                                scope.launch { snackbar.showSnackbar(text) }
                                            },
                                        )
                                    }
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
}

@Composable
private fun ChatTopBar(onNewChat: () -> Unit, onOpenHistory: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            // logo 紧贴状态栏，不再留额外上边距。
            .padding(start = 16.dp, end = 8.dp, top = 0.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CatAvatar(size = 32.dp)
        Spacer(Modifier.width(9.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "FLORIS",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Text(
                t(StringKey.AppTagline),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
            )
        }
        IconPill(
            icon = Icons.Default.History,
            contentDescription = t(StringKey.ChatHistory),
            onClick = onOpenHistory,
            modifier = Modifier.onboardingTarget(TourStepKey.HISTORY),
        )
        IconPill(
            icon = Icons.Outlined.AddCircle,
            contentDescription = t(StringKey.ChatNew),
            onClick = onNewChat,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.onboardingTarget(TourStepKey.NEW_CONVERSATION),
        )
    }
}

@Composable
private fun ChatEmptyState(modifier: Modifier, onSuggestion: (String) -> Unit) {
    val suggestions = listOf(
        t(StringKey.SuggestNews),
        t(StringKey.SuggestBooks),
        t(StringKey.SuggestPlace),
        t(StringKey.SuggestCode),
    )
    Column(
        modifier = modifier
            .fillMaxWidth()
            // 可滚动 + 垂直居中：屏幕够高时保持居中，不够高时可以滑动，
            // 任何一条快捷输入都不会被裁切压扁。
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 28.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        QuotePill()
        Spacer(Modifier.height(22.dp))
        CatAvatar(size = 68.dp)
        Spacer(Modifier.height(14.dp))
        Text(
            "FLORIS",
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            t(StringKey.AppTagline),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.primary,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(10.dp))
        Text(
            t(StringKey.ChatIntro),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(20.dp))
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            suggestions.forEach { suggestion ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(999.dp))
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.94f))
                        .pressable(scaleDown = 0.98f) { onSuggestion(suggestion) }
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        suggestion,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    // 箭头改为"填入"语义的图标：点了是进输入框，不是直接发送。
                    Icon(
                        Icons.Outlined.NorthEast,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(14.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun UserRow(message: ChatMessageUi) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.End,
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier
                .widthIn(max = 292.dp)
                .clip(RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp, bottomStart = 18.dp, bottomEnd = 6.dp))
                .background(userBubbleBrush())
                .padding(horizontal = 15.dp, vertical = 11.dp),
        ) {
            Text(
                message.content,
                style = MaterialTheme.typography.bodySmall,
                color = Color.White,
            )
        }
    }
}

@Composable
private fun AssistantRow(
    message: ChatMessageUi,
    busyActionId: String?,
    submittingClarification: Boolean,
    onConfirm: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onCancel: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onShowMap: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onClarificationSubmit: (com.floris.android.core.model.Clarification, Map<String, Any>) -> Unit,
    onFollowUp: (String) -> Unit,
    onRetry: () -> Unit,
    onNotify: (String) -> Unit,
) {
    val graphicsLayer = rememberGraphicsLayer()
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var saving by remember { mutableStateOf(false) }

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        CatAvatar(size = 28.dp)
        Spacer(Modifier.width(9.dp))
        Column(Modifier.weight(1f)) {
            // 回答框：柔和底衬 + 细描边，让每一轮回答有清晰边界。
            // 用 graphicsLayer 录制这块内容，"保存图片"即导出它。
            Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(16.dp))
                    .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.92f))
                    .border(
                        1.dp,
                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.12f),
                        RoundedCornerShape(16.dp),
                    )
                    .drawWithContent {
                        graphicsLayer.record { this@drawWithContent.drawContent() }
                        drawLayer(graphicsLayer)
                    }
                    .padding(horizontal = 14.dp, vertical = 12.dp),
            ) {
                // 流式期间展示过程动画：生图走画布节奏，其余走搜索阶段时间线。
                if (message.streaming) {
                    if (message.isImageIntent) ImageCreationProgress(message)
                    else SearchProgress(message)
                }
                if (message.content.isNotBlank() || message.streaming) {
                    MarkdownText(
                        markdown = message.content,
                        streaming = message.streaming && message.content.isNotBlank(),
                    )
                }
                if (!message.streaming) {
                    SearchCompleteMeta(message)
                }
                message.searchResults?.let { meta ->
                    if (meta.results.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        SearchSourcesRow(meta)
                    }
                    if (meta.media.isNotEmpty()) MediaGrid(meta.media)
                }
                PaperListCard(message.papers)
            }

            // 操作栏：复制纯文字 / 保存图片到相册（对齐网页端）。
            if (!message.streaming && message.content.isNotBlank()) {
                // 文案先取好：t() 是 @Composable，不能在点击回调里调用。
                val copiedText = t(StringKey.CopiedToClipboard)
                val saveFailedText = t(StringKey.SaveImageFailed)
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    GhostAction(
                        icon = Icons.Default.ContentCopy,
                        label = t(StringKey.CopyPlainText),
                        onClick = {
                            clipboard.setText(
                                AnnotatedString(MarkdownPlainText.convert(message.content)),
                            )
                            onNotify(copiedText)
                        },
                    )
                    Spacer(Modifier.width(4.dp))
                    GhostAction(
                        icon = Icons.Default.SaveAlt,
                        label = if (saving) t(StringKey.Saving) else t(StringKey.SaveAsImage),
                        enabled = !saving,
                        onClick = {
                            saving = true
                            scope.launch {
                                val result = runCatching { graphicsLayer.toImageBitmap() }
                                    .fold(
                                        onSuccess = { ImageSaver.saveToGallery(context, it) },
                                        onFailure = { Result.failure(it) },
                                    )
                                onNotify(result.getOrElse { saveFailedText })
                                saving = false
                            }
                        },
                    )
                }
            }

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
                Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(message.error ?: t(StringKey.Failed), MaterialTheme.colorScheme.error)
                    Spacer(Modifier.width(8.dp))
                    Row(
                        Modifier
                            .clip(RoundedCornerShape(999.dp))
                            .pressable(onClick = onRetry)
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        androidx.compose.material3.Icon(
                            Icons.Default.Refresh, contentDescription = t(StringKey.Retry),
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(14.dp),
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(
                            t(StringKey.Retry),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }
            if (!message.streaming) {
                FollowUpChips(message.followUps, onClick = onFollowUp)
            }
        }
    }
}

/** 回答下方的低调操作按钮：小图标 + 文字，按下有细微缩放。 */
@Composable
private fun GhostAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .pressable(enabled = enabled, scaleDown = 0.94f, onClick = onClick)
            .padding(horizontal = 9.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        androidx.compose.material3.Icon(
            icon, contentDescription = label,
            tint = MaterialTheme.colorScheme.onSurfaceVariant
                .copy(alpha = if (enabled) 0.85f else 0.4f),
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(5.dp))
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
                .copy(alpha = if (enabled) 0.85f else 0.4f),
        )
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
    Column(
        Modifier
            .fillMaxWidth()
            // 贴到底部 Tab 栏：只留 4dp 呼吸，不再有多余留白。
            .padding(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 0.dp),
    ) {
        AnimatedVisibility(visible = imageCount > 0, enter = fadeIn(), exit = fadeOut()) {
            Row(
                Modifier.padding(start = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusChip("已附 $imageCount 张图片", MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(6.dp))
                Text(
                    t(StringKey.Close),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.pressable(onClick = onClearImages).padding(4.dp),
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(24.dp))
                .background(MaterialTheme.colorScheme.surface)
                .onboardingTarget(TourStepKey.INPUT)
                .padding(4.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            IconPill(
                icon = Icons.Outlined.Image,
                contentDescription = "添加图片",
                onClick = onPickImages,
                size = 40.dp,
                iconSize = 19.dp,
            )
            Box(
                Modifier
                    .weight(1f)
                    .heightIn(min = 40.dp)
                    .padding(vertical = 10.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                if (draft.isEmpty()) {
                    Text(
                        t(StringKey.ChatInputHint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                BasicTextField(
                    value = draft,
                    onValueChange = onDraftChange,
                    textStyle = MaterialTheme.typography.bodySmall.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                    ),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Sentences,
                        imeAction = ImeAction.Default,
                    ),
                    maxLines = 5,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.width(4.dp))
            PrimaryIconButton(
                icon = if (streaming) Icons.Default.Close else Icons.AutoMirrored.Filled.Send,
                contentDescription = if (streaming) t(StringKey.ChatStop) else "发送",
                onClick = { if (streaming) onStop() else if (draft.isNotBlank()) onSend() },
                enabled = streaming || draft.isNotBlank(),
                danger = streaming,
            )
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
