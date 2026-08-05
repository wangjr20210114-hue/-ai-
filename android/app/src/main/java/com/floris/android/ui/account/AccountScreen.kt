package com.floris.android.ui.account

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Badge
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.WorkspacePremium
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.data.num
import com.floris.android.core.data.obj
import com.floris.android.core.model.Identity
import com.floris.android.core.model.Profile
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.SettingRow
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.UserAvatar
import com.floris.android.ui.components.IconPill
import com.floris.android.ui.components.pressable
import com.floris.android.ui.prefs.AppPreferences
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.t
import com.floris.android.ui.accountViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import coil.compose.AsyncImage

private const val FEATURE_DOC_URL =
    "https://github.com/wangjr20210114-hue/-ai-/blob/main/README.md"

/**
 * 个人信息页。承载原先散落在设置里的账号相关内容：
 * 昵称、会员、用量，以及新手教程重播入口。
 * 入口是「我的」页的头像，游客不可进入（后端 /profile 对游客 403）。
 */
class AccountViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
    val preferences: AppPreferences,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val profile: Profile? = null,
        val dailyTokens: Long = 0,
        val monthlyTokens: Long = 0,
        val loading: Boolean = true,
        val message: String? = null,
        val updatingProfile: Boolean = false,
    )

    val authState = authManager.state

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            repository.loadCachedAvatar()
            val conversationId = repository.activeConversationId()
            runCatching { repository.getProfile() }
                .onSuccess { profile -> _state.update { it.copy(profile = profile) } }
            runCatching { repository.providerUsage(conversationId) }.onSuccess { usage ->
                val bucket = usage.obj("usage")
                _state.update {
                    it.copy(
                        dailyTokens = bucket?.num("daily_tokens") ?: 0,
                        monthlyTokens = bucket?.num("monthly_tokens") ?: 0,
                    )
                }
            }
            _state.update { it.copy(loading = false) }
        }
    }

    fun updateDisplayName(name: String) {
        val trimmed = name.trim()
        if (trimmed.isBlank()) return
        viewModelScope.launch {
            runCatching { repository.updateProfile(trimmed, null) }
                .onSuccess { profile ->
                    // 以后端回执为准再更新界面。
                    _state.update {
                        it.copy(
                            profile = profile,
                            message = strings.get(StringKey.ProfileNameUpdated),
                        )
                    }
                }
                .onFailure {
                    _state.update { s ->
                        s.copy(message = strings.get(StringKey.ProfileUpdateFailed))
                    }
                }
        }
    }

    fun updateAvatar(uri: Uri) {
        val displayName = _state.value.profile?.display_name
            ?: (authManager.state.value as? AuthState.SignedIn)?.identity?.display_name
            ?: strings.get(StringKey.ProfileDefaultDisplayName)
        _state.update { it.copy(updatingProfile = true) }
        viewModelScope.launch {
            runCatching { repository.updateProfile(displayName, uri) }
                .onSuccess { profile ->
                    _state.update {
                        it.copy(
                            profile = profile,
                            updatingProfile = false,
                            message = strings.get(StringKey.ProfileAvatarUpdated),
                        )
                    }
                }
                .onFailure {
                    _state.update {
                        it.copy(
                            updatingProfile = false,
                            message = strings.get(StringKey.ProfileAvatarUpdateFailed),
                        )
                    }
                }
        }
    }

    fun replayOnboarding() = viewModelScope.launch { preferences.setOnboardingDone(false) }

    fun consumeMessage() = _state.update { it.copy(message = null) }
}

@Composable
fun AccountScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: AccountViewModel = viewModel(factory = container.accountViewModelFactory())
    val state by viewModel.state.collectAsState()
    val authState by viewModel.authState.collectAsState()
    val identity = (authState as? AuthState.SignedIn)?.identity ?: Identity()
    val uriHandler = LocalUriHandler.current
    val snackbar = remember { SnackbarHostState() }
    val localAvatar by container.repository.localAvatarFlow.collectAsState()
    val pickAvatar = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent(),
    ) { uri -> uri?.let(viewModel::updateAvatar) }

    var editingName by remember { mutableStateOf(false) }
    var nameDraft by remember { mutableStateOf("") }

    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() }
    }

    if (editingName) {
        AlertDialog(
            onDismissRequest = { editingName = false },
            title = { Text(t(StringKey.SettingsNickname)) },
            text = {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(horizontal = 14.dp, vertical = 12.dp),
                ) {
                    BasicTextField(
                        value = nameDraft,
                        onValueChange = { nameDraft = it },
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodySmall.copy(
                            color = MaterialTheme.colorScheme.onSurface,
                        ),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.updateDisplayName(nameDraft)
                    editingName = false
                }) { Text(t(StringKey.Confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { editingName = false }) { Text(t(StringKey.Cancel)) }
            },
        )
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconPill(
                icon = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = t(StringKey.Back),
                onClick = onBack,
            )
            Spacer(Modifier.width(4.dp))
            Text(t(StringKey.AccountTitle), style = MaterialTheme.typography.headlineMedium)
        }

        Box(Modifier.weight(1f)) {
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item(key = "identity") {
                    FlorisCard(corner = 20.dp) {
                        Row(
                            Modifier.padding(18.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            val avatarUrl = state.profile?.avatar_url ?: identity.avatar_url
                            val avatarModel = localAvatar ?: avatarUrl?.let(::accountAvatarUrl)
                            Box(
                                Modifier
                                    .size(58.dp)
                                    .clip(CircleShape)
                                    .pressable(enabled = !state.updatingProfile) {
                                        pickAvatar.launch("image/*")
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                if (avatarModel != null) {
                                    AsyncImage(
                                        model = avatarModel,
                                        contentDescription = t(StringKey.ProfileAvatar),
                                        contentScale = ContentScale.Crop,
                                        modifier = Modifier.fillMaxSize().clip(CircleShape),
                                    )
                                } else {
                                    UserAvatar(size = 58.dp)
                                }
                            }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    state.profile?.display_name
                                        ?: identity.display_name
                                        ?: t(StringKey.SettingsNotSet),
                                    style = MaterialTheme.typography.headlineSmall,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                // 展示后端下发的账号标识，没有就不占位。
                                state.profile?.email?.takeIf { it.isNotBlank() }?.let {
                                    Spacer(Modifier.height(3.dp))
                                    Text(
                                        it,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                        }
                    }
                }

                item { SectionHeader(t(StringKey.ProfileAccount)) }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsNickname),
                        subtitle = (state.profile?.display_name ?: identity.display_name)
                            ?.takeIf { it.isNotBlank() } ?: t(StringKey.SettingsNotSet),
                        icon = Icons.Default.Badge,
                        onClick = {
                            nameDraft = state.profile?.display_name
                                ?: identity.display_name.orEmpty()
                            editingName = true
                        },
                        trailing = { Chevron() },
                    )
                }
                item {
                    SettingRow(
                        title = t(StringKey.AccountMembership),
                        subtitle = identity.membership ?: "free",
                        icon = Icons.Default.WorkspacePremium,
                        trailing = {
                            StatusChip(
                                identity.membership ?: "free",
                                MaterialTheme.colorScheme.primary,
                            )
                        },
                    )
                }

                item { SectionHeader(t(StringKey.SettingsUsage)) }
                item {
                    FlorisCard {
                        Column(Modifier.padding(16.dp)) {
                            UsageRow(t(StringKey.SettingsDailyTokens), state.dailyTokens)
                            Spacer(Modifier.height(10.dp))
                            UsageRow(t(StringKey.SettingsMonthlyTokens), state.monthlyTokens)
                        }
                    }
                }

                // 新手教程从设置搬到这里
                item { SectionHeader(t(StringKey.AccountHelp)) }
                item {
                    SettingRow(
                        title = t(StringKey.SettingsReplayTour),
                        subtitle = t(StringKey.SettingsReplayTourDesc),
                        icon = Icons.Default.AutoAwesome,
                        onClick = {
                            viewModel.replayOnboarding()
                            onBack()
                        },
                        trailing = { Chevron() },
                    )
                }
                item {
                    SettingRow(
                        title = t(StringKey.ProfileAbout),
                        subtitle = t(StringKey.AccountAboutDesc),
                        icon = Icons.Default.Info,
                        onClick = { runCatching { uriHandler.openUri(FEATURE_DOC_URL) } },
                        trailing = { Chevron() },
                    )
                }
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter))
        }
    }
}

private fun accountAvatarUrl(value: String): String =
    if (value.startsWith("http://") || value.startsWith("https://")) value
    else com.floris.android.BuildConfig.FLORIS_BASE_URL.trimEnd('/') + "/" + value.trimStart('/')

@Composable
private fun Chevron() {
    Icon(
        Icons.AutoMirrored.Filled.KeyboardArrowRight, null,
        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        modifier = Modifier.size(18.dp),
    )
}

@Composable
private fun UsageRow(label: String, value: Long) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text("%,d".format(value), style = MaterialTheme.typography.titleMedium)
    }
}
