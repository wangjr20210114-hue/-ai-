package com.floris.android.ui.navigation

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.DateRange
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.floris.android.AppContainer
import com.floris.android.ui.auth.LoginScreen
import com.floris.android.ui.calendar.CalendarScreen
import com.floris.android.ui.chat.ChatScreen
import com.floris.android.ui.components.AuroraOrb
import com.floris.android.ui.components.pressable
import com.floris.android.ui.history.HistoryScreen
import com.floris.android.ui.maps.MapScreen
import com.floris.android.ui.onboarding.LocalOnboardingTargets
import com.floris.android.ui.onboarding.OnboardingOverlay
import com.floris.android.ui.onboarding.OnboardingTargets
import com.floris.android.ui.onboarding.TourStepKey
import com.floris.android.ui.onboarding.TourTarget
import com.floris.android.ui.onboarding.onboardingTarget
import com.floris.android.ui.papers.ReadingScreen
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import com.floris.android.ui.profile.ProfileScreen
import com.floris.android.ui.settings.SettingsScreen
import com.floris.android.ui.skills.SkillsScreen
import kotlinx.coroutines.launch

object Routes {
    const val CHAT = "chat"
    const val SKILLS = "skills"
    const val CALENDAR = "calendar"
    const val READING = "reading"
    const val PROFILE = "profile"
    const val HISTORY = "history"
    const val MAP = "map"
    const val SETTINGS = "settings"
}

private data class Tab(
    val route: String,
    val label: StringKey,
    val icon: ImageVector,
    val activeIcon: ImageVector,
    /** 新手引导聚光灯锚点。 */
    val tourKey: String,
)

private val tabs = listOf(
    Tab(Routes.CHAT, StringKey.TabChat, Icons.Outlined.ChatBubbleOutline, Icons.Filled.ChatBubble, TourStepKey.NEW_CONVERSATION),
    Tab(Routes.SKILLS, StringKey.TabSkills, Icons.Outlined.StarOutline, Icons.Filled.Star, TourStepKey.SKILLS),
    Tab(Routes.CALENDAR, StringKey.TabCalendar, Icons.Outlined.DateRange, Icons.Filled.DateRange, TourStepKey.CALENDAR),
    Tab(Routes.READING, StringKey.TabReading, Icons.Outlined.MenuBook, Icons.Filled.MenuBook, TourStepKey.READING),
    Tab(Routes.PROFILE, StringKey.TabProfile, Icons.Outlined.Person, Icons.Filled.Person, TourStepKey.PROFILE),
)

@Composable
fun FlorisNavHost(container: AppContainer, signedIn: Boolean, authLoading: Boolean) {
    val navController = rememberNavController()
    val scope = rememberCoroutineScope()
    val onboardingDone by container.preferences.onboardingDone.collectAsState()
    val onboardingTargets = remember { OnboardingTargets() }

    CompositionLocalProvider(LocalOnboardingTargets provides onboardingTargets) {
        when {
            authLoading -> Splash()
            !signedIn -> LoginScreen(container = container)
            else -> Box(Modifier.fillMaxSize()) {
                MainShell(container, navController)

                if (!onboardingDone) {
                    OnboardingOverlay(
                        onNavigate = { target ->
                            val route = when (target) {
                                TourTarget.CHAT -> Routes.CHAT
                                TourTarget.SKILLS -> Routes.SKILLS
                                TourTarget.CALENDAR -> Routes.CALENDAR
                                TourTarget.READING -> Routes.READING
                                TourTarget.PROFILE -> Routes.PROFILE
                            }
                            navController.switchTab(route)
                        },
                        onFinish = { scope.launch { container.preferences.setOnboardingDone(true) } },
                    )
                }
            }
        }
    }
}

@Composable
private fun MainShell(container: AppContainer, navController: NavHostController) {
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showTabBar = currentRoute in tabs.map { it.route }

    // 五个底部 Tab 共用 Activity 级 ViewModelStore：切页不销毁、不重复拉数据，
    // 回到旧页时数据与滚动位置立即就在，不再有"等一下界面才出来"。
    val tabOwner = LocalViewModelStoreOwner.current

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f)) {
            NavHost(
                navController = navController,
                startDestination = Routes.CHAT,
                // 底部 Tab 之间只做极短淡入：切换即时出现，不等动画放完。
                enterTransition = { fadeIn(tween(90)) },
                exitTransition = { fadeOut(tween(90)) },
                popEnterTransition = { fadeIn(tween(90)) },
                popExitTransition = { fadeOut(tween(90)) },
            ) {
                composable(Routes.CHAT) {
                    ChatScreen(
                        container = container,
                        owner = tabOwner,
                        onOpenHistory = { navController.navigate(Routes.HISTORY) },
                        onOpenMap = { navController.navigate(Routes.MAP) },
                    )
                }
                composable(Routes.SKILLS) { SkillsScreen(container = container, owner = tabOwner) }
                composable(Routes.CALENDAR) { CalendarScreen(container = container, owner = tabOwner) }
                composable(Routes.READING) { ReadingScreen(container = container, owner = tabOwner) }
                composable(Routes.PROFILE) {
                    ProfileScreen(
                        container = container,
                        owner = tabOwner,
                        onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                        onOpenReading = { navController.switchTab(Routes.READING) },
                        onOpenMap = { navController.navigate(Routes.MAP) },
                        onHandleReminder = { prompt ->
                            // 把后端给的处理话术带到聊天输入框，由用户自己决定是否发送。
                            container.repository.pendingDraftFlow.value = prompt
                            navController.switchTab(Routes.CHAT)
                        },
                    )
                }
                composable(Routes.HISTORY) {
                    HistoryScreen(
                        container = container,
                        onBack = { navController.popBackStack() },
                        onOpenConversation = {
                            navController.navigate(Routes.CHAT) {
                                popUpTo(Routes.CHAT) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.MAP) {
                    MapScreen(container = container, onBack = { navController.popBackStack() })
                }
                composable(Routes.SETTINGS) {
                    SettingsScreen(container = container, onBack = { navController.popBackStack() })
                }
            }
        }
        if (showTabBar) {
            FlorisTabBar(
                currentRoute = currentRoute,
                onSelect = { navController.switchTab(it) },
            )
        }
    }
}

private fun NavHostController.switchTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** 自绘底栏：无 Material 容器阴影，选中项图标弹起 + 药丸底衬。 */
@Composable
private fun FlorisTabBar(currentRoute: String?, onSelect: (String) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .navigationBarsPadding()
            .padding(horizontal = 6.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        tabs.forEach { tab ->
            val selected = currentRoute == tab.route
            val tint by animateColorAsState(
                if (selected) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.75f),
                animationSpec = tween(220),
                label = "tabTint",
            )
            val lift by animateFloatAsState(
                if (selected) -2f else 0f,
                animationSpec = spring(stiffness = Spring.StiffnessMediumLow, dampingRatio = 0.6f),
                label = "tabLift",
            )
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clip(androidx.compose.foundation.shape.RoundedCornerShape(16.dp))
                    .onboardingTarget(tab.tourKey)
                    .pressable(scaleDown = 0.94f) { onSelect(tab.route) }
                    .padding(vertical = 6.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (selected) {
                        Box(
                            Modifier
                                .size(width = 34.dp, height = 26.dp)
                                .clip(androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
                                .background(MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.55f)),
                        )
                    }
                    Icon(
                        if (selected) tab.activeIcon else tab.icon,
                        contentDescription = null,
                        tint = tint,
                        modifier = Modifier
                            .size(20.dp)
                            .graphicsLayer { translationY = lift },
                    )
                }
                Spacer(Modifier.height(3.dp))
                Text(
                    t(tab.label),
                    style = MaterialTheme.typography.labelSmall,
                    color = tint,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun Splash() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        AuroraOrb(size = 84.dp)
    }
}
