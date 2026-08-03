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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.floris.android.AppContainer
import com.floris.android.BuildConfig
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.Identity
import com.floris.android.core.model.Profile
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.profileViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ProfileViewModel(
    private val repository: FlorisRepository,
    private val authManager: AuthManager,
) : ViewModel() {

    val authState = authManager.state

    private val _profile = MutableStateFlow<Profile?>(null)
    val profile = _profile.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            runCatching { repository.getProfile() }.onSuccess { _profile.value = it }
        }
    }

    fun signOut() {
        viewModelScope.launch { authManager.signOut() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(
    container: AppContainer,
    onOpenSettings: () -> Unit,
    onOpenPapers: () -> Unit,
    onOpenMap: () -> Unit,
) {
    val viewModel: ProfileViewModel = viewModel(factory = container.profileViewModelFactory())
    val authState by viewModel.authState.collectAsState()
    val profile by viewModel.profile.collectAsState()
    val identity = (authState as? AuthState.SignedIn)?.identity ?: Identity()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text("我的") },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = "header") {
                FlorisCard {
                    Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                        val avatarUrl = profile?.avatar_url ?: identity.avatar_url
                        if (!avatarUrl.isNullOrEmpty()) {
                            AsyncImage(
                                model = absoluteUrl(avatarUrl),
                                contentDescription = "头像",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.size(56.dp).clip(CircleShape),
                            )
                        } else {
                            Box(
                                Modifier.size(56.dp).clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.primaryContainer),
                                contentAlignment = Alignment.Center,
                            ) {
                                Icon(
                                    Icons.Default.Person, null,
                                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                        }
                        Spacer(Modifier.padding(6.dp))
                        Column {
                            Text(
                                profile?.display_name ?: identity.display_name ?: "Floris 用户",
                                style = MaterialTheme.typography.headlineSmall,
                            )
                            Spacer(Modifier.height(4.dp))
                            StatusChip(
                                membershipLabel(identity.membership),
                                MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }

            item(key = "workspace-header") { SectionHeader("工作区") }
            item(key = "papers") {
                EntryRow(Icons.Default.DateRange, "论文库", "已保存的学术记录", onOpenPapers)
            }
            item(key = "map") {
                EntryRow(Icons.Default.Place, "地图工作区", "地点与路线", onOpenMap)
            }

            item(key = "account-header") { SectionHeader("账号") }
            item(key = "settings") {
                EntryRow(Icons.Default.Settings, "设置", "偏好、用量与数据", onOpenSettings)
            }
            item(key = "about") {
                EntryRow(Icons.Default.Info, "关于", "Floris Android · 契约 v1") {}
            }

            item(key = "signout") {
                FlorisCard(onClick = viewModel::signOut) {
                    Box(Modifier.fillMaxWidth().padding(14.dp), contentAlignment = Alignment.Center) {
                        Text("退出登录", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.titleMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun EntryRow(icon: ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    FlorisCard(onClick = onClick) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.padding(6.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(
                    subtitle,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowRight, null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun membershipLabel(membership: String) = when (membership) {
    "plus" -> "Plus 会员"
    "pro" -> "Pro 会员"
    "free" -> "免费版"
    else -> "游客"
}

private fun absoluteUrl(url: String): String =
    if (url.startsWith("http")) url else BuildConfig.FLORIS_BASE_URL.trimEnd('/') + url
