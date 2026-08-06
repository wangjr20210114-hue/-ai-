package com.floris.android.ui.navigation

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
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
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.outlined.DateRange
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.floris.android.BuildConfig
import com.floris.android.core.model.ConversationSummary
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.UserAvatar
import com.floris.android.ui.components.pressable
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 侧边栏历史搜索：按标题过滤（忽略大小写），空查询返回全部。 */
fun filterConversations(items: List<ConversationSummary>, query: String): List<ConversationSummary> {
    val q = query.trim()
    if (q.isEmpty()) return items
    return items.filter { it.title.contains(q, ignoreCase = true) }
}

/**
 * 左侧滑出式侧边栏：占屏宽 5/6，剩余 1/6 压暗且点击即关闭。
 * 从上到下：搜索框 / 新对话 / 地点 / 日程 / 阅读 / 历史列表 / 登录区。
 * 数据全部来自 Maker（会话列表与个人信息），客户端只做展示与跳转。
 */
@Composable
fun FlorisSidebar(
    open: Boolean,
    onClose: () -> Unit,
    state: SidebarViewModel.UiState,
    onNewChat: () -> Unit,
    onOpenConversation: (String) -> Unit,
    onOpenPlace: () -> Unit,
    onOpenCalendar: () -> Unit,
    onOpenReading: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenSkills: () -> Unit,
    onOpenReminders: () -> Unit,
    onOpenSettings: () -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = filterConversations(state.conversations, query)

    Box(Modifier.fillMaxSize()) {
        // 剩余 1/6 的压暗遮罩：点击回到主界面。
        AnimatedVisibility(
            visible = open,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
        ) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.45f))
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null,
                        onClick = onClose,
                    ),
            )
        }

        // 抽屉本体：从左向右滑入，占整屏宽度的 5/6。
        AnimatedVisibility(
            visible = open,
            enter = slideInHorizontally(tween(300)) { -it } + fadeIn(tween(300)),
            exit = slideOutHorizontally(tween(260)) { -it } + fadeOut(tween(220)),
            modifier = Modifier
                .fillMaxWidth(5f / 6f)
                .fillMaxHeight(),
        ) {
            Column(
                Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.surface)
                    .statusBarsPadding()
                    .navigationBarsPadding(),
            ) {
                // 1. 搜索框：放大镜 + “搜索”占位。
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 10.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                        .padding(horizontal = 12.dp, vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        Icons.Default.Search,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                        if (query.isEmpty()) {
                            Text(
                                t(StringKey.Search),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        BasicTextField(
                            value = query,
                            onValueChange = { query = it },
                            textStyle = MaterialTheme.typography.bodySmall.copy(
                                color = MaterialTheme.colorScheme.onSurface,
                            ),
                            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }

                // 2. 新对话入口。
                Row(
                    Modifier
                        .fillMaxWidth()
                        .pressable(scaleDown = 0.97f, onClick = onNewChat)
                        .onboardingTarget(TourStepKey.NEW_CONVERSATION)
                        .padding(horizontal = 18.dp, vertical = 13.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CatAvatar(size = 32.dp)
                    Spacer(Modifier.width(12.dp))
                    Text(
                        t(StringKey.SidebarNewChat),
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
                HorizontalDivider(Modifier.padding(horizontal = 12.dp))

                // 3. 地点 / 日程 / 阅读。
                SidebarNavRow(Icons.Outlined.Public, t(StringKey.SidebarPlace), onOpenPlace)
                SidebarNavRow(Icons.Outlined.DateRange, t(StringKey.CalendarTitle), onOpenCalendar)
                SidebarNavRow(Icons.AutoMirrored.Outlined.MenuBook, t(StringKey.ReadingTitle), onOpenReading)
                HorizontalDivider(Modifier.padding(horizontal = 12.dp))

                // 4. 历史对话列表（不显示标题，直接可滑动）。
                when {
                    state.loading && filtered.isEmpty() -> Box(
                        Modifier.weight(1f).fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) { InlineLoading() }

                    filtered.isEmpty() -> Box(
                        Modifier.weight(1f).fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            t(StringKey.ChatEmptyHistoryTitle),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    else -> LazyColumn(
                        Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .onboardingTarget(TourStepKey.HISTORY),
                        contentPadding = PaddingValues(vertical = 6.dp),
                    ) {
                        items(filtered, key = { it.id }) { conversation ->
                            ConversationSidebarRow(
                                conversation = conversation,
                                onClick = { onOpenConversation(conversation.id) },
                            )
                        }
                    }
                }
                HorizontalDivider(Modifier.padding(horizontal = 12.dp))

                // 5. 登录区：头像 + 用户名，右侧技能/提醒/设置。
                Row(
                    Modifier
                        .fillMaxWidth()
                        .pressable(scaleDown = 0.97f, onClick = onOpenAccount)
                        .padding(start = 14.dp, end = 6.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    val avatarUrl = state.profile?.avatar_url?.takeIf { it.isNotBlank() }
                    Box(
                        Modifier
                            .size(40.dp)
                            .clip(CircleShape)
                            .background(MaterialTheme.colorScheme.surfaceVariant),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (avatarUrl != null) {
                            AsyncImage(
                                model = if (avatarUrl.startsWith("http")) avatarUrl
                                else BuildConfig.FLORIS_BASE_URL.trimEnd('/') + avatarUrl,
                                contentDescription = null,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize().clip(CircleShape),
                            )
                        } else {
                            UserAvatar(size = 34.dp)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            state.profile?.display_name?.takeIf { it.isNotBlank() }
                                ?: t(StringKey.ProfileDefaultUser),
                            style = MaterialTheme.typography.labelLarge,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    IconPill(
                        icon = Icons.Outlined.Star,
                        contentDescription = t(StringKey.TabSkills),
                        onClick = onOpenSkills,
                        size = 34.dp,
                        iconSize = 17.dp,
                    )
                    IconPill(
                        icon = Icons.Filled.Notifications,
                        contentDescription = t(StringKey.Reminders),
                        onClick = onOpenReminders,
                        size = 34.dp,
                        iconSize = 17.dp,
                    )
                    IconPill(
                        icon = Icons.Outlined.Settings,
                        contentDescription = t(StringKey.SettingsTitle),
                        onClick = onOpenSettings,
                        size = 34.dp,
                        iconSize = 17.dp,
                    )
                }
            }
        }
    }
}

@Composable
private fun SidebarNavRow(
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .pressable(scaleDown = 0.97f, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(22.dp),
        )
        Spacer(Modifier.width(14.dp))
        Text(label, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun ConversationSidebarRow(
    conversation: ConversationSummary,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .pressable(scaleDown = 0.97f, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                conversation.title.ifBlank { t(StringKey.ChatNew) },
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                "${t(StringKey.ChatMessageCount, conversation.messageCount)} · ${sidebarRelativeTime(conversation.updatedAt)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun sidebarRelativeTime(timestamp: Long): String {
    val diff = System.currentTimeMillis() - timestamp
    val minute = 60_000L
    val hour = 60 * minute
    val day = 24 * hour
    return when {
        diff < minute -> t(StringKey.TimeJustNow)
        diff < hour -> t(StringKey.TimeMinutesAgo, diff / minute)
        diff < day -> t(StringKey.TimeHoursAgo, diff / hour)
        diff < 7 * day -> t(StringKey.TimeDaysAgo, diff / day)
        else -> SimpleDateFormat("yyyy/M/d", Locale.getDefault()).format(Date(timestamp))
    }
}
