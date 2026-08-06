package com.floris.android.ui.profile

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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.components.CatIconPill
import com.floris.android.BuildConfig
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.Identity
import com.floris.android.core.model.ProactiveNotification
import com.floris.android.core.model.ProactiveState
import com.floris.android.core.model.Profile
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.GuestNotice
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.SettingRow
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.UserAvatar
import com.floris.android.ui.components.pressable
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.t
import com.floris.android.ui.profileViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private const val FEATURE_DOC_URL =
    "https://github.com/wangjr20210114-hue/-ai-/blob/main/README.md"

class ProfileViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
    private val strings: StringResolver,
    /**
     * 系统通知推送钩子。由界面层注入（需要 Context），
     * 单测里传 null 即可完全绕开 Android 框架。
     */
    private val notifier: ((List<ProactiveNotification>) -> Unit)? = null,
) : ViewModel() {

    data class UiState(
        val profile: Profile? = null,
        val notifications: List<ProactiveNotification> = emptyList(),
        val refreshing: Boolean = false,
        val mutatingId: String? = null,
        val error: String? = null,
        val loaded: Boolean = false,
    )

    val authState = authManager.state
    val isGuest: Boolean get() = authManager.isGuest

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init {
        viewModelScope.launch {
            repository.proactiveStateFlow.collect { projection ->
                projection?.let(::applyProactive)
            }
        }
        refresh()
    }

    fun refresh() {
        if (_state.value.refreshing) return
        _state.update { it.copy(refreshing = true) }
        viewModelScope.launch {
            // 后端 /profile 对游客返回 403（Login required），不必发这次请求。
            if (!authManager.isGuest) {
                repository.loadCachedAvatar()
                runCatching { repository.getProfile() }
                    .onSuccess { profile -> _state.update { it.copy(profile = profile) } }
            }

            // 主动提醒由后端 /proactive 生成，客户端只展示与转发用户决定。
            loadProactive("refresh")
            _state.update { it.copy(refreshing = false, loaded = true) }
        }
    }

    /** 已读并把建议带回聊天（对应网页端"去处理"）。 */
    fun markRead(id: String) = mutate(id, "mark_read", buildJsonObject {
        put("notification_id", id)
    })

    /** 稍后提醒：默认推迟 1 小时，与网页端一致。 */
    fun snooze(id: String) = mutate(id, "snooze", buildJsonObject {
        put("notification_id", id)
        put("until", System.currentTimeMillis() / 1000 + 3600)
    })

    fun dismiss(id: String) = mutate(id, "dismiss", buildJsonObject {
        put("notification_id", id)
    })

    private fun mutate(id: String, operation: String, input: JsonObject) {
        _state.update { it.copy(mutatingId = id) }
        viewModelScope.launch {
            runCatching {
                repository.proactive(repository.activeConversationId(), operation, input)
            }.onSuccess { response ->
                applyProactive(response)
            }.onFailure {
                _state.update { s -> s.copy(error = strings.get(StringKey.OperationFailed)) }
            }
            _state.update { it.copy(mutatingId = null) }
        }
    }

    private suspend fun loadProactive(operation: String) {
        runCatching {
            repository.proactive(repository.activeConversationId(), operation)
        }.onSuccess(::applyProactive)
    }

    private fun applyProactive(response: JsonObject) {
        val active = activeNotifications(repository.parseProactiveNotifications(response))
        _state.update { it.copy(notifications = active) }
        pushToStatusBar(active)
    }

    private fun applyProactive(projection: ProactiveState) {
        val active = activeNotifications(projection.notifications)
        _state.update { it.copy(notifications = active) }
        pushToStatusBar(active)
    }

    /**
     * 把新出现的未读提醒推到系统通知栏（移动端独有）。
     * 只推没推过的，避免每次刷新都重复轰炸。
     */
    private fun pushToStatusBar(items: List<ProactiveNotification>) {
        val notifier = notifier ?: return
        val fresh = items.filter { it.status == "unread" && notifiedIds.add(it.id) }
        if (fresh.isNotEmpty()) notifier(fresh)
    }

    /** 已推送过通知的提醒 id，防重复。 */
    private val notifiedIds = mutableSetOf<String>()

    fun consumeError() = _state.update { it.copy(error = null) }

    fun signOut() {
        viewModelScope.launch { authManager.signOut() }
    }
}

/** 只保留未读与仍在推迟窗口内的提醒，规则同网页端 activeProactiveNotifications。 */
internal fun activeNotifications(
    items: List<ProactiveNotification>,
    now: Long = System.currentTimeMillis() / 1000,
): List<ProactiveNotification> = items.filter { item ->
    item.status == "unread" || (item.status == "snoozed" && (item.snoozedUntil ?: 0) > now)
}.take(10)

@Composable
fun ProfileScreen(
    container: AppContainer,
    owner: ViewModelStoreOwner? = null,
    onOpenSettings: () -> Unit,
    onOpenReading: () -> Unit,
    onOpenMap: () -> Unit,
    /** 返回聊天（底部导航移除后由侧边栏进入本页）。 */
    onBack: () -> Unit = {},
    /** 点头像进入个人信息（游客不跳转）。 */
    onOpenAccount: () -> Unit = {},
    /** 点"去处理"：把后端给的话术带回聊天输入框。 */
    onHandleReminder: (String) -> Unit = {},
) {
    val viewModel: ProfileViewModel = viewModel(
        viewModelStoreOwner = owner ?: checkNotNull(LocalViewModelStoreOwner.current),
        key = "profile",
        factory = container.profileViewModelFactory(),
    )
    val authState by viewModel.authState.collectAsState()
    val state by viewModel.state.collectAsState()
    val localAvatar by container.repository.localAvatarFlow.collectAsState()
    val identity = (authState as? AuthState.SignedIn)?.identity ?: Identity()
    val uriHandler = LocalUriHandler.current
    // 以后端下发的身份为准判断游客态。
    val isGuest = identity.auth_type == "guest"

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Row(
            Modifier.padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CatIconPill(
                resId = R.drawable.ic_back,
                contentDescription = t(StringKey.Back),
                onClick = onBack,
            )
            Spacer(Modifier.width(4.dp))
            Text(
                t(StringKey.ProfileTitle),
                style = MaterialTheme.typography.headlineMedium,
            )
        }

        LazyColumn(
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // 游客提示条：置顶提醒登录才能解锁全部能力与云端保存。
            if (isGuest) {
                item(key = "guest-notice") {
                    GuestNotice(
                        text = t(StringKey.GuestProfileNotice),
                        actionText = t(StringKey.GuestSignInCta),
                        onAction = viewModel::signOut,
                    )
                }
            }
            // 身份卡（品牌渐变描边 + 橘猫头像）
            item(key = "identity") {
                FlorisCard(corner = 20.dp, modifier = Modifier.onboardingTarget(TourStepKey.PROFILE)) {
                    Row(
                        Modifier.padding(18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        val avatarUrl = localAvatar ?: state.profile?.avatar_url ?: identity.avatar_url
                        Box(
                            Modifier
                                .size(62.dp)
                                .clip(CircleShape)
                                .background(
                                    Brush.linearGradient(
                                        listOf(
                                            MaterialTheme.colorScheme.primary,
                                            MaterialTheme.colorScheme.secondary,
                                        ),
                                    ),
                                )
                                // 点头像进入个人信息；游客没有个人信息可看，不跳转。
                                .pressable(enabled = !isGuest, scaleDown = 0.94f) { onOpenAccount() }
                                .padding(2.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            if (!avatarUrl.isNullOrEmpty()) {
                                AsyncImage(
                                    model = if (avatarUrl == localAvatar) avatarUrl else absoluteUrl(avatarUrl),
                                    contentDescription = t(StringKey.Self),
                                    contentScale = ContentScale.Crop,
                                    modifier = Modifier.fillMaxSize().clip(CircleShape),
                                )
                            } else {
                                Box(
                                    Modifier
                                        .fillMaxSize()
                                        .clip(CircleShape)
                                        .background(MaterialTheme.colorScheme.surface),
                                    contentAlignment = Alignment.Center,
                                ) {
                                    // 用户默认头像是木偶铃铛猫，橘猫只代表 Floris 自己。
                                    UserAvatar(size = 58.dp)
                                }
                            }
                        }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (isGuest) t(StringKey.GuestBadge)
                                else state.profile?.display_name
                                    ?: identity.display_name
                                    ?: t(StringKey.ProfileDefaultUser),
                                style = MaterialTheme.typography.headlineSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Spacer(Modifier.height(6.dp))
                            StatusChip(
                                membershipLabel(identity.membership),
                                MaterialTheme.colorScheme.primary,
                            )
                            // 游客会话只在本机保留，提示用户登录以长期保存。
                            if (identity.auth_type == "guest") {
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    t(StringKey.GuestUpgradeHint),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.75f),
                                )
                            }
                        }
                    }
                }
            }

            // 主动提醒：放在身份卡正下方，进入"我的"就能第一眼看到。
            item(key = "briefs-header") {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .onboardingTarget(TourStepKey.REMINDERS),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(Modifier.weight(1f)) { SectionHeader(t(StringKey.Reminders)) }
                    if (state.notifications.isNotEmpty()) {
                        StatusChip("${state.notifications.size}", MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(6.dp))
                    }
                    IconPill(
                        icon = Icons.Default.Refresh,
                        contentDescription = t(StringKey.RefreshReminders),
                        onClick = viewModel::refresh,
                        size = 30.dp,
                        iconSize = 15.dp,
                        enabled = !state.refreshing,
                    )
                }
            }
            if (state.notifications.isEmpty()) {
                item(key = "briefs-empty") {
                    FlorisCard {
                        Text(
                            if (state.refreshing) t(StringKey.Loading) else t(StringKey.NoReminders),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(14.dp),
                        )
                    }
                }
            } else {
                items(state.notifications.size, key = { state.notifications[it].id }) { index ->
                    val item = state.notifications[index]
                    ProactiveCard(
                        item = item,
                        busy = state.mutatingId == item.id,
                        onHandle = {
                            onHandleReminder(item.actionPrompt ?: item.title)
                            viewModel.markRead(item.id)
                        },
                        onSnooze = { viewModel.snooze(item.id) },
                        onDismiss = { viewModel.dismiss(item.id) },
                    )
                }
            }

            // 工作区
            item(key = "workspace-header") { SectionHeader(t(StringKey.ProfileWorkspace)) }
            item(key = "reading") {
                SettingRow(
                    title = t(StringKey.ProfileReading),
                    subtitle = t(StringKey.ProfileReadingDesc),
                    icon = Icons.AutoMirrored.Filled.MenuBook,
                    onClick = onOpenReading,
                    modifier = Modifier.onboardingTarget(TourStepKey.READING),
                    trailing = { Chevron() },
                )
            }
            item(key = "map") {
                SettingRow(
                    title = t(StringKey.ProfileMap),
                    subtitle = t(StringKey.ProfileMapDesc),
                    icon = Icons.Default.Place,
                    onClick = onOpenMap,
                    modifier = Modifier.onboardingTarget(TourStepKey.MAP),
                    trailing = { Chevron() },
                )
            }

            // 账号
            item(key = "account-header") { SectionHeader(t(StringKey.ProfileAccount)) }
            item(key = "settings") {
                SettingRow(
                    title = t(StringKey.ProfileSettings),
                    subtitle = t(StringKey.ProfileSettingsDesc),
                    icon = Icons.Default.Settings,
                    onClick = onOpenSettings,
                    modifier = Modifier.onboardingTarget(TourStepKey.SETTINGS),
                    trailing = { Chevron() },
                )
            }
            item(key = "about") {
                SettingRow(
                    title = t(StringKey.ProfileAbout),
                    subtitle = t(StringKey.ProfileAboutDesc),
                    icon = Icons.Default.Info,
                    onClick = { runCatching { uriHandler.openUri(FEATURE_DOC_URL) } },
                    modifier = Modifier.onboardingTarget(TourStepKey.GITHUB),
                    trailing = { Chevron() },
                )
            }

            // 游客的登录入口已在顶部提示条里，底部不再重复放按钮；
            // 只有正式用户才需要"退出登录"。
            if (!isGuest) {
                item(key = "session-action") {
                    Box(
                        Modifier.fillMaxWidth().padding(top = 12.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        PillButton(
                            text = t(StringKey.ProfileSignOut),
                            onClick = viewModel::signOut,
                            style = PillStyle.Danger,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Chevron() {
    Icon(
        Icons.AutoMirrored.Filled.KeyboardArrowRight, null,
        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        modifier = Modifier.size(18.dp),
    )
}

/** 单条主动提醒：标题 + 正文 + 三个决定按钮，状态全部由后端回执驱动。 */
@Composable
private fun ProactiveCard(
    item: ProactiveNotification,
    busy: Boolean,
    onHandle: () -> Unit,
    onSnooze: () -> Unit,
    onDismiss: () -> Unit,
) {
    FlorisCard {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Box(
                    Modifier
                        .size(32.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(MaterialTheme.colorScheme.secondaryContainer),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.Default.AutoAwesome, null,
                        tint = MaterialTheme.colorScheme.onSecondaryContainer,
                        modifier = Modifier.size(16.dp),
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(item.title, style = MaterialTheme.typography.titleMedium)
                    item.body?.takeIf { it.isNotBlank() }?.let {
                        Spacer(Modifier.height(3.dp))
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (item.status == "snoozed" && item.snoozedUntil != null) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            t(StringKey.RemindLaterAt, clockLabel(item.snoozedUntil)),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                        )
                    }
                }
                if (item.priority == "high") {
                    StatusChip(t(StringKey.Important), MaterialTheme.colorScheme.error)
                }
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                PillButton(
                    text = t(StringKey.HandleSuggestion),
                    onClick = onHandle,
                    enabled = !busy,
                    compact = true,
                )
                PillButton(
                    text = t(StringKey.Later),
                    onClick = onSnooze,
                    style = PillStyle.Tonal,
                    enabled = !busy,
                    compact = true,
                )
                PillButton(
                    text = t(StringKey.Ignore),
                    onClick = onDismiss,
                    style = PillStyle.Ghost,
                    enabled = !busy,
                    compact = true,
                )
            }
        }
    }
}

private fun clockLabel(epochSeconds: Long): String =
    SimpleDateFormat("M/d HH:mm", Locale.getDefault()).format(Date(epochSeconds * 1000))

@Composable
private fun membershipLabel(membership: String) = when (membership) {
    "plus" -> t(StringKey.MembershipPlus)
    "pro" -> t(StringKey.MembershipPro)
    "free" -> t(StringKey.MembershipFree)
    else -> t(StringKey.MembershipGuest)
}

private fun absoluteUrl(url: String): String =
    if (url.startsWith("http")) url else BuildConfig.FLORIS_BASE_URL.trimEnd('/') + url
