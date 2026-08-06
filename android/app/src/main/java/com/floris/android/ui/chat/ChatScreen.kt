package com.floris.android.ui.chat

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.BitmapFactory
import android.location.LocationManager
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AddCircleOutline
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.outlined.Menu
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SaveAlt
import androidx.compose.material.icons.outlined.AddCircle
import androidx.compose.material.icons.outlined.DarkMode
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.LightMode
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
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
import com.floris.android.core.chat.PendingChatTurn
import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.ProactiveWorkflow
import com.floris.android.core.model.ProactiveWorkflowStep
import com.floris.android.core.share.ImageSaver
import com.floris.android.core.share.MarkdownPlainText
import com.floris.android.ui.chatViewModelFactory
import com.floris.android.ui.components.AnimateIn
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.CatIconPill
import com.floris.android.ui.components.ClarificationForm
import com.floris.android.ui.components.ExperienceHints
import com.floris.android.ui.components.FollowUpChips
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.ImageCreationProgress
import com.floris.android.ui.components.MarkdownText
import com.floris.android.ui.components.MediaGrid
import com.floris.android.ui.components.PaperListCard
import com.floris.android.ui.components.ProactiveChatCard
import com.floris.android.ui.components.PrimaryIconButton
import com.floris.android.ui.components.PrimaryIconButtonImage
import com.floris.android.ui.components.QuotePill
import com.floris.android.ui.components.SearchCompleteMeta
import com.floris.android.ui.components.SearchProgress
import com.floris.android.ui.components.SearchSourcesRow
import com.floris.android.ui.components.SourceBoundAnswer
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.WorkspaceActionCard
import com.floris.android.ui.components.panelBorderColor
import com.floris.android.ui.components.panelShadowColor
import com.floris.android.ui.components.pressable
import com.floris.android.ui.layout.Responsive
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.LocalLanguage
import com.floris.android.ui.prefs.t
import com.floris.android.ui.theme.LocalDarkTheme
import com.floris.android.ui.theme.userBubbleBrush
import kotlinx.coroutines.launch
import java.io.File

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChatScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onOpenSidebar: () -> Unit,
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
    val imeVisible = WindowInsets.isImeVisible

    var draft by remember { mutableStateOf("") }
    var images by remember { mutableStateOf<List<String>>(emptyList()) }
    var voiceListening by remember { mutableStateOf(false) }
    var voicePrefix by remember { mutableStateOf("") }
    val language = LocalLanguage.current
    val voiceUnavailableText = t(StringKey.ChatVoiceUnavailable)
    val voiceController = remember(context, voiceUnavailableText) {
        VoiceInputController(
            context = context,
            onText = { recognized ->
                draft = if (voicePrefix.isBlank()) recognized else "$voicePrefix $recognized"
            },
            onListeningChanged = { voiceListening = it },
            onUnavailable = { scope.launch { snackbar.showSnackbar(voiceUnavailableText) } },
        )
    }
    DisposableEffect(voiceController) {
        onDispose { voiceController.release() }
    }

    val voicePermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) voiceController.start(language.speechTag)
        else scope.launch { snackbar.showSnackbar(voiceUnavailableText) }
    }

    // 相机：拍照后作为参考图加入本轮（最多 3 张）。
    var cameraPhotoUri by remember { mutableStateOf<android.net.Uri?>(null) }
    val takeCameraPhoto = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture(),
    ) { success ->
        if (success) {
            cameraPhotoUri?.let { uri ->
                scope.launch {
                    container.repository.imageToDataUrl(uri)?.let { dataUrl ->
                        images = (images + dataUrl).take(3)
                    }
                }
            }
        }
    }
    val launchCamera: () -> Unit = {
        val photo = File.createTempFile("floris-camera-", ".jpg", context.cacheDir)
        cameraPhotoUri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.files",
            photo,
        )
        cameraPhotoUri?.let(takeCameraPhoto::launch)
        Unit
    }

    // 加号：相册图片与文件（PDF 等）合并在同一个系统选择器里，由用户选择。
    val pickDocument = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri?.let { picked ->
            val mime = context.contentResolver.getType(picked).orEmpty()
            val name = runCatching {
                context.contentResolver.query(
                    picked,
                    arrayOf(OpenableColumns.DISPLAY_NAME),
                    null,
                    null,
                    null,
                )?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        cursor.getString(0)
                    } else null
                }
            }.getOrNull()?.takeIf { it.isNotBlank() } ?: "document.pdf"
            if (mime.startsWith("image/")) {
                scope.launch {
                    container.repository.imageToDataUrl(picked)?.let { dataUrl ->
                        images = (images + dataUrl).take(3)
                    }
                }
            } else {
                viewModel.uploadDocument(picked, name)
            }
        }
    }

    // 生图卡片“保存到相册”的忙碌状态（按 action id 区分）。
    var savingGeneratedImageId by remember { mutableStateOf<String?>(null) }
    val generatedSavedText = t(StringKey.SavedToGallery)
    val generatedSaveFailedText = t(StringKey.SaveImageFailed)
    val saveGeneratedImage: (com.floris.android.core.model.WorkspaceAction) -> Unit = { action ->
        val url = action.result?.let { result ->
            listOf("image_url", "url", "current_url").firstNotNullOfOrNull { key ->
                (result[key] as? kotlinx.serialization.json.JsonPrimitive)
                    ?.content?.takeIf { it.isNotBlank() }
            }
        }
        if (url != null && savingGeneratedImageId == null) {
            savingGeneratedImageId = action.id
            scope.launch {
                val result = runCatching {
                    val bytes = container.repository.fetchImageBytes(url)
                    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        ?: error("图片解码失败")
                    ImageSaver.saveToGallery(context, bitmap.asImageBitmap())
                }.fold(onSuccess = { it }, onFailure = { Result.failure(it) })
                snackbar.showSnackbar(
                    if (result.isSuccess) generatedSavedText else generatedSaveFailedText,
                )
                savingGeneratedImageId = null
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

    // ---- 流式跟随滚动 ----
    // 旧实现每次内容变化都 animateScrollToItem，动画会和用户的手势抢夺
    // 滚动权，表现为"滑不动"；而动画本身又跟不上出字速度，于是需要手动下滑。
    // 现在改成：用户在底部附近时用 scrollBy 无动画贴住底部（不打断手势），
    // 一旦用户主动向上翻阅就停止跟随，直到他自己滑回底部。
    var followTail by remember { mutableStateOf(true) }
    val atBottom by remember {
        derivedStateOf {
            val info = listState.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull() ?: return@derivedStateOf true
            last.index >= info.totalItemsCount - 1 &&
                last.offset + last.size <= info.viewportEndOffset + 96
        }
    }
    // 用户上滑离开底部就交还控制权，滑回底部立刻恢复跟随。
    LaunchedEffect(atBottom) { followTail = atBottom }

    val lastMessage = state.messages.lastOrNull()
    LaunchedEffect(lastMessage?.id, lastMessage?.content?.length, state.streaming) {
        if (state.messages.isEmpty() || !followTail) return@LaunchedEffect
        // 先定位到最后一条，再把它的底部推到视口底部。
        // scrollToItem/scrollBy 都是即时的，不会与拖拽手势抢夺滚动权。
        listState.scrollToItem(state.messages.lastIndex)
        val info = listState.layoutInfo
        info.visibleItemsInfo.lastOrNull()?.let { item ->
            val overflow = item.offset + item.size - info.viewportEndOffset
            if (overflow > 0) listState.scrollBy(overflow.toFloat())
        }
    }
    // 新消息（自己发出的那条）始终滚到底，无论此前是否在翻阅历史。
    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) {
            followTail = true
            listState.scrollToItem(state.messages.lastIndex)
        }
    }
    // 键盘弹起、可视区变矮时，若正在贴底跟随则重新滚到底，
    // 让最新消息始终显示在输入框上方（“正文被整体顶起”的视觉效果）。
    LaunchedEffect(imeVisible) {
        if (imeVisible && followTail && state.messages.isNotEmpty()) {
            withFrameNanos { }
            listState.scrollToItem(state.messages.lastIndex)
            val info = listState.layoutInfo
            info.visibleItemsInfo.lastOrNull()?.let { item ->
                val overflow = item.offset + item.size - info.viewportEndOffset
                if (overflow > 0) listState.scrollBy(overflow.toFloat())
            }
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
            title = { Text(t(StringKey.LocationPermissionTitle)) },
            text = {
                Text(state.locationRequestReason ?: t(StringKey.LocationPermissionBody))
            },
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
    val queueFullText = t(StringKey.ChatQueueFull)

    // 背景已由 MainShell 铺满整屏（含底栏区域），这里不再重复绘制。
    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding(),
        ) {
            ChatTopBar(
                title = state.conversationTitle,
                onOpenSidebar = onOpenSidebar,
                onToggleTheme = {
                    scope.launch { container.preferences.toggleTheme(dark) }
                },
            )

            // header 固定不动；键盘弹起时 body（消息区 + 输入框）整体让出键盘高度并紧贴键盘。
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .imePadding(),
            ) {
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
                                            isLastAi = index == state.messages.lastIndex,
                                            proactive = state.proactive,
                                            busyProactiveKey = state.busyProactiveKey,
                                            isGuest = container.authManager.isGuest,
                                            busyActionId = state.busyActionId,
                                            submittingClarification = state.submittingClarification,
                                            onConfirm = viewModel::confirmAction,
                                            onCancel = viewModel::cancelAction,
                                            onShowMap = { action ->
                                                viewModel.activateMap(action)
                                                onOpenMap()
                                            },
                                            onEditImage = viewModel::editImage,
                                            onUpdateMeeting = viewModel::updateMeetingAction,
                                            onRouteCalendarProposal = viewModel::requestRouteCalendarProposal,
                                            onSaveGeneratedImage = saveGeneratedImage,
                                            savingGeneratedImageId = savingGeneratedImageId,
                                            onHandleProactive = viewModel::applyProactiveSuggestion,
                                            onSnoozeProactive = viewModel::snoozeNotification,
                                            onDismissProactive = viewModel::dismissNotification,
                                            onConfirmWorkflow = viewModel::confirmWorkflow,
                                            onRejectWorkflow = viewModel::rejectWorkflow,
                                            onCancelWorkflow = viewModel::cancelWorkflow,
                                            onProactiveStep = viewModel::workflowStep,
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

                TurnQueueDrawer(
                    turns = state.queuedTurns,
                    onUpdate = viewModel::updateQueuedTurn,
                    onDelete = viewModel::removeQueuedTurn,
                    onRunNow = viewModel::interruptWithQueuedTurn,
                )
                InputBar(
                    draft = draft,
                    onDraftChange = { draft = it },
                    imageCount = images.size,
                    streaming = state.streaming,
                    uploadingDocument = state.uploadingDocument,
                    onPickCamera = launchCamera,
                    onPickMixed = {
                        pickDocument.launch(arrayOf("image/*", "application/pdf"))
                    },
                    onClearImages = { images = emptyList() },
                    voiceListening = voiceListening,
                    onVoice = {
                        if (voiceListening) {
                            voiceController.stop()
                        } else if (!voiceController.available) {
                            scope.launch { snackbar.showSnackbar(voiceUnavailableText) }
                        } else {
                            voicePrefix = draft.trimEnd()
                            if (ContextCompat.checkSelfPermission(
                                    context,
                                    Manifest.permission.RECORD_AUDIO,
                                ) == PermissionChecker.PERMISSION_GRANTED
                            ) voiceController.start(language.speechTag)
                            else voicePermission.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    onSend = {
                        voiceController.stop()
                        when (viewModel.send(draft, images)) {
                            ChatSendDisposition.STARTED,
                            ChatSendDisposition.QUEUED -> {
                                draft = ""
                                images = emptyList()
                            }
                            ChatSendDisposition.QUEUE_FULL -> {
                                scope.launch { snackbar.showSnackbar(queueFullText) }
                            }
                            ChatSendDisposition.IGNORED -> Unit
                        }
                    },
                    onStop = viewModel::stop,
                )
                // 键盘收起时补固定留白 + 导航栏内边距，输入框不会贴到屏幕最底边。
                if (!imeVisible) {
                    Spacer(
                        Modifier
                            .height(20.dp)
                            .navigationBarsPadding(),
                    )
                }
            }
        }
        SnackbarHost(
            hostState = snackbar,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .then(
                    if (WindowInsets.isImeVisible) Modifier.imePadding()
                    else Modifier.navigationBarsPadding(),
                ),
        )
    }
}

/** Compact Codex-style drawer for turns waiting behind the active Maker run. */
@Composable
private fun TurnQueueDrawer(
    turns: List<PendingChatTurn>,
    onUpdate: (String, String) -> Unit,
    onDelete: (String) -> Unit,
    onRunNow: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    AnimatedVisibility(
        visible = turns.isNotEmpty(),
        enter = expandVertically() + fadeIn(),
        exit = shrinkVertically() + fadeOut(),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 2.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.94f))
                .border(1.dp, panelBorderColor(), RoundedCornerShape(16.dp)),
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .pressable { expanded = !expanded }
                    .padding(start = 14.dp, end = 6.dp, top = 8.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    t(StringKey.ChatQueueTitle, turns.size),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f),
                )
                IconPill(
                    icon = if (expanded) Icons.Default.KeyboardArrowDown else Icons.Default.KeyboardArrowUp,
                    contentDescription = null,
                    onClick = { expanded = !expanded },
                    size = 30.dp,
                    iconSize = 18.dp,
                )
            }
            AnimatedVisibility(
                visible = expanded,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut(),
            ) {
                Column(Modifier.padding(start = 10.dp, end = 10.dp, bottom = 10.dp)) {
                    turns.forEach { turn ->
                        QueueTurnRow(turn, onUpdate, onDelete, onRunNow)
                        if (turn != turns.last()) Spacer(Modifier.height(6.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun QueueTurnRow(
    turn: PendingChatTurn,
    onUpdate: (String, String) -> Unit,
    onDelete: (String) -> Unit,
    onRunNow: (String) -> Unit,
) {
    var editing by remember(turn.id) { mutableStateOf(false) }
    var value by remember(turn.id, turn.text) { mutableStateOf(turn.text) }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f))
            .padding(start = 12.dp, end = 4.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (editing) {
            BasicTextField(
                value = value,
                onValueChange = { value = it },
                textStyle = MaterialTheme.typography.bodySmall.copy(
                    color = MaterialTheme.colorScheme.onSurface,
                ),
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                modifier = Modifier.weight(1f),
            )
        } else {
            Text(
                turn.text,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
        }
        IconPill(
            icon = Icons.Default.Edit,
            contentDescription = t(StringKey.ChatQueueEdit),
            onClick = {
                if (editing) onUpdate(turn.id, value)
                editing = !editing
            },
            size = 30.dp,
            iconSize = 15.dp,
        )
        IconPill(
            icon = Icons.Default.DeleteOutline,
            contentDescription = t(StringKey.ChatQueueDelete),
            onClick = { onDelete(turn.id) },
            size = 30.dp,
            iconSize = 15.dp,
        )
        IconPill(
            icon = Icons.Default.PlayArrow,
            contentDescription = t(StringKey.ChatQueueRunNow),
            onClick = { onRunNow(turn.id) },
            size = 30.dp,
            iconSize = 17.dp,
            tint = MaterialTheme.colorScheme.primary,
        )
    }
}

@Composable
private fun ChatTopBar(
    title: String,
    onOpenSidebar: () -> Unit,
    onToggleTheme: () -> Unit,
) {
    val dark = LocalDarkTheme.current
    Box(
        Modifier
            .fillMaxWidth()
            .padding(start = 8.dp, end = 8.dp, top = 0.dp, bottom = 2.dp),
    ) {
        // 左侧：三横杠打开侧边栏。
        CatIconPill(
            resId = R.drawable.ic_menu,
            contentDescription = t(StringKey.SidebarOpen),
            onClick = onOpenSidebar,
            size = 40.dp,
            iconSize = 26.dp,
            modifier = Modifier.align(Alignment.CenterStart),
        )
        // 中间：对话名 + AI 提示小字（品牌与 logo 已移除）。
        Column(
            Modifier
                .align(Alignment.Center)
                .fillMaxWidth(0.62f),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                title.ifBlank { t(StringKey.ChatNew) },
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onBackground,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                t(StringKey.AiDisclaimer),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
            )
        }
        // 右侧：白天 / 黑夜切换。
        CatIconPill(
            resId = if (dark) R.drawable.ic_theme_sun else R.drawable.ic_theme_moon,
            contentDescription = t(StringKey.SettingsTheme),
            onClick = onToggleTheme,
            size = 40.dp,
            iconSize = 26.dp,
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .onboardingTarget(TourStepKey.THEME),
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
            .padding(horizontal = Responsive.horizontalPadding + 12.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        QuotePill()
        Spacer(Modifier.height(Responsive.gap(22.dp)))
        // 横屏收小头像与间距，四条快捷输入仍能完整显示。
        CatAvatar(size = Responsive.brandAvatar)
        Spacer(Modifier.height(Responsive.gap(14.dp)))
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
        Spacer(Modifier.height(Responsive.gap(10.dp)))
        Text(
            t(StringKey.ChatIntro),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(Responsive.gap(20.dp)))
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            suggestions.forEach { suggestion ->
                val pillShape = RoundedCornerShape(999.dp)
                Row(
                    Modifier
                        .fillMaxWidth()
                        // 白底压在浅色背景图上几乎看不出边界，
                        // 补上描边与投影（对齐网页端 --app-border / --app-shadow）。
                        .shadow(4.dp, pillShape, ambientColor = panelShadowColor(), spotColor = panelShadowColor())
                        .clip(pillShape)
                        .background(MaterialTheme.colorScheme.surface)
                        .border(1.dp, panelBorderColor(), pillShape)
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
    isLastAi: Boolean,
    proactive: ProactiveState?,
    busyProactiveKey: String?,
    isGuest: Boolean,
    busyActionId: String?,
    submittingClarification: Boolean,
    onConfirm: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onCancel: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onShowMap: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onEditImage: (com.floris.android.core.model.WorkspaceAction, String) -> Unit,
    onUpdateMeeting: (
        com.floris.android.core.model.WorkspaceAction,
        String,
        String,
        String,
    ) -> Unit,
    onRouteCalendarProposal: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    onSaveGeneratedImage: (com.floris.android.core.model.WorkspaceAction) -> Unit,
    savingGeneratedImageId: String?,
    onHandleProactive: (ProactiveNotification) -> Unit,
    onSnoozeProactive: (String) -> Unit,
    onDismissProactive: (String) -> Unit,
    onConfirmWorkflow: (ProactiveWorkflow) -> Unit,
    onRejectWorkflow: (ProactiveWorkflow) -> Unit,
    onCancelWorkflow: (ProactiveWorkflow) -> Unit,
    onProactiveStep: (ProactiveWorkflow, ProactiveWorkflowStep, String) -> Unit,
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

    // 去掉头像列：整行让给内容，对话可视宽度多出约 37dp。
    Column(Modifier.fillMaxWidth()) {
        // 回答框：柔和底衬 + 描边 + 投影，让每一轮回答有清晰边界。
        // 用 graphicsLayer 录制这块内容，"保存图片"即导出它。
        val answerShape = RoundedCornerShape(16.dp)
        Column(
            Modifier
                .fillMaxWidth()
                .shadow(6.dp, answerShape, ambientColor = panelShadowColor(), spotColor = panelShadowColor())
                .clip(answerShape)
                .background(MaterialTheme.colorScheme.surface)
                .border(1.dp, panelBorderColor(), answerShape)
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
                SourceBoundAnswer(
                    content = message.content,
                    searchMeta = message.searchResults,
                    streaming = message.streaming && message.content.isNotBlank(),
                )
            }
            if (!message.streaming) {
                SearchCompleteMeta(message)
            }
            if (!message.streaming) {
                ExperienceHints(message.hints, isGuest)
            }
            message.searchResults?.let { meta ->
                if (meta.results.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    SearchSourcesRow(meta)
                }
            }
            PaperListCard(message.papers)
            }

        // 操作栏：复制纯文字 / 保存图片到相册（对齐网页端）。
        if (!message.streaming && message.content.isNotBlank()) {
            // 文案先取好：t() 是 @Composable，不能在点击回调里调用。
            val copiedText = t(StringKey.CopiedToClipboard)
            val saveFailedText = t(StringKey.SaveImageFailed)
            val savedText = t(StringKey.SavedToGallery)
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
                            onNotify(if (result.isSuccess) savedText else saveFailedText)
                            saving = false
                        }
                    },
                )
            }
        }

        if (!message.streaming) {
            message.actions.forEach { action ->
                WorkspaceActionCard(
                    action = action,
                    busy = busyActionId == action.id,
                    onConfirm = { onConfirm(action) },
                    onCancel = { onCancel(action) },
                    onShowMap = { onShowMap(action) },
                    onEditImage = { prompt -> onEditImage(action, prompt) },
                    onUpdateMeeting = { subject, start, end ->
                        onUpdateMeeting(action, subject, start, end)
                    },
                    onRouteCalendarProposal = { onRouteCalendarProposal(action) },
                    hasCalendarProposal = message.actions.any { it.kind == "calendar_changes" },
                    onSaveImage = { onSaveGeneratedImage(action) },
                    savingImage = savingGeneratedImageId == action.id,
                )
            }
        }
        message.clarification?.let { clarification ->
            ClarificationForm(
                clarification = clarification,
                submitting = submittingClarification,
                onSubmit = { answers -> onClarificationSubmit(clarification, answers) },
            )
        }
        // 已提交的澄清只留一条只读记录，卡片已被销毁，无法再改选。
        message.clarificationAnswered?.let { summary ->
            Spacer(Modifier.height(6.dp))
            Text(
                t(StringKey.ClarificationAnswered, summary),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
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
        if (isLastAi) {
            ProactiveChatCard(
                state = proactive,
                busyKey = busyProactiveKey,
                onHandle = onHandleProactive,
                onSnooze = onSnoozeProactive,
                onDismiss = onDismissProactive,
                onConfirmWorkflow = onConfirmWorkflow,
                onRejectWorkflow = onRejectWorkflow,
                onCancelWorkflow = onCancelWorkflow,
                onStep = onProactiveStep,
            )
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
    uploadingDocument: Boolean,
    onPickCamera: () -> Unit,
    onPickMixed: () -> Unit,
    onClearImages: () -> Unit,
    voiceListening: Boolean,
    onVoice: () -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 8.dp),
    ) {
        AnimatedVisibility(visible = imageCount > 0, enter = fadeIn(), exit = fadeOut()) {
            Row(
                Modifier.padding(start = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusChip(
                    t(StringKey.AttachedImageCount, imageCount),
                    MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    t(StringKey.Close),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.pressable(onClick = onClearImages).padding(4.dp),
                )
            }
        }
        // 圆角矩形 + 柔和阴影（高级感），与网页端 composer 同风格。
        val inputShape = RoundedCornerShape(26.dp)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .shadow(10.dp, inputShape, ambientColor = panelShadowColor(), spotColor = panelShadowColor())
                .clip(inputShape)
                .background(MaterialTheme.colorScheme.surface)
                .border(1.dp, panelBorderColor(), inputShape)
                .onboardingTarget(TourStepKey.INPUT)
                .padding(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 最左侧：相机（拍照作为参考图）。
            CatIconPill(
                resId = R.drawable.ic_camera,
                contentDescription = t(StringKey.ChatCamera),
                onClick = onPickCamera,
                size = 40.dp,
                iconSize = 26.dp,
            )
            // 输入框本体：提示“发消息”。
            Box(
                Modifier
                    .weight(1f)
                    .heightIn(min = 42.dp)
                    .padding(horizontal = 2.dp, vertical = 11.dp),
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
            // 麦克风：语音输入。
            CatIconPill(
                resId = R.drawable.ic_microphone,
                contentDescription = t(
                    if (voiceListening) StringKey.ChatVoiceStop else StringKey.ChatVoiceStart,
                ),
                onClick = onVoice,
                size = 40.dp,
                iconSize = 26.dp,
                tint = if (voiceListening) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            // 加号：相册 + 文件选择器（PDF 等），上传时置灰防重复。
            CatIconPill(
                resId = R.drawable.ic_add_chat,
                contentDescription = t(StringKey.ChatAddDocument),
                onClick = {
                    if (!uploadingDocument) onPickMixed()
                },
                size = 40.dp,
                iconSize = 26.dp,
                tint = if (uploadingDocument) MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f)
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (streaming) {
                PrimaryIconButton(
                    icon = Icons.Default.Close,
                    contentDescription = t(StringKey.ChatStop),
                    onClick = onStop,
                    danger = true,
                    size = 38.dp,
                )
                Spacer(Modifier.width(4.dp))
            }
            PrimaryIconButtonImage(
                resId = R.drawable.ic_send,
                contentDescription = t(StringKey.Send),
                onClick = { if (draft.isNotBlank()) onSend() },
                enabled = draft.isNotBlank(),
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
