package com.floris.android.ui.navigation

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.Crossfade
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.Image
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
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.DateRange
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.account.AccountScreen
import com.floris.android.ui.auth.LoginScreen
import com.floris.android.ui.calendar.CalendarScreen
import com.floris.android.ui.chat.ChatScreen
import com.floris.android.ui.chat.ChatViewModel
import com.floris.android.ui.chatViewModelFactory
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
import com.floris.android.ui.settings.PersonalizationScreen
import com.floris.android.ui.sidebarViewModelFactory
import com.floris.android.ui.skills.SkillsScreen
import com.floris.android.ui.theme.LocalDarkTheme
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
    const val PERSONALIZATION = "personalization"
    /** 个人信息：昵称、头像、会员与新手教程入口，点头像进入。 */
    const val ACCOUNT = "account"
}

@Composable
fun FlorisNavHost(
    container: AppContainer,
    signedIn: Boolean,
    authLoading: Boolean,
    sessionKey: String,
) {
    val navController = rememberNavController()
    val scope = rememberCoroutineScope()
    var sidebarOpen by remember { mutableStateOf(false) }
    val onboardingDone by container.preferences.onboardingDone.collectAsState()
    val onboardingTargets = remember { OnboardingTargets() }

    CompositionLocalProvider(LocalOnboardingTargets provides onboardingTargets) {
        when {
            authLoading -> Splash()
            !signedIn -> LoginScreen(container = container)
            else -> Box(Modifier.fillMaxSize()) {
                MainShell(
                    container = container,
                    navController = navController,
                    sessionKey = sessionKey,
                    sidebarOpen = sidebarOpen,
                    onSidebarOpenChange = { sidebarOpen = it },
                )

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
                            navController.navigate(route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        onFinish = { scope.launch { container.preferences.setOnboardingDone(true) } },
                        onRevealSidebar = { sidebarOpen = true },
                    )
                }
            }
        }
    }
}

@Composable
private fun MainShell(
    container: AppContainer,
    navController: NavHostController,
    sessionKey: String,
    sidebarOpen: Boolean,
    onSidebarOpenChange: (Boolean) -> Unit,
) {
    // 所有页面共用会话级 ViewModelStore：切页不销毁、不重复拉数据，
    // 回到旧页时数据与滚动位置立即就在。
    val tabOwner = rememberSessionViewModelStoreOwner(sessionKey)
    val dark = LocalDarkTheme.current
    val scope = rememberCoroutineScope()
    val requestLogin = {
        scope.launch { container.authManager.signOut() }
        Unit
    }

    // 聊天与侧边栏共用同一个 ViewModel，新对话/切对话由侧边栏直接驱动。
    val chatViewModel: ChatViewModel = viewModel(
        viewModelStoreOwner = tabOwner,
        key = "chat",
        factory = container.chatViewModelFactory(),
    )
    val sidebarViewModel: SidebarViewModel = viewModel(
        viewModelStoreOwner = tabOwner,
        key = "sidebar",
        factory = container.sidebarViewModelFactory(),
    )
    val sidebarState by sidebarViewModel.state.collectAsState()

    val openSection: (String) -> Unit = { route ->
        navController.navigate(route) {
            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    // Warm Maker's shared entitlement projection without blocking chat startup.
    // Calendar, maps and reading then consume the same server-owned decision.
    LaunchedEffect(sessionKey) {
        val conversationId = container.repository.activeConversationId()
        launch {
            runCatching { container.repository.ensureSkillAccess(conversationId) }
        }
        launch {
            runCatching { container.repository.proactive(conversationId, "page_open") }
        }
        launch {
            runCatching { container.repository.proactive(conversationId, "memory_refresh") }
        }
    }

    // 背景铺在最外层：之前画在聊天页内部，Tab 栏与状态栏区域露白，
    // 现在整屏（含底栏后面）都是同一张皮肤，滚动时也不会出现割裂。
    Box(Modifier.fillMaxSize()) {
        // 皮肤随主题交叉淡入淡出，与配色插值同步，切换白天/黑夜时不跳变。
        Crossfade(
            targetState = dark,
            animationSpec = tween(420, easing = FastOutSlowInEasing),
            label = "skin",
        ) { isDark ->
            Box(Modifier.fillMaxSize()) {
                Image(
                    painter = painterResource(
                        if (isDark) R.drawable.floris_chat_dark else R.drawable.floris_chat_light,
                    ),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(if (isDark) Color(0xD1100C1D) else Color(0xD6FFFDF9)),
                )
            }
        }

        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f)) {
                NavHost(
                    navController = navController,
                    startDestination = Routes.CHAT,
                    enterTransition = { tabEnter(this) },
                    exitTransition = { tabExit(this) },
                    popEnterTransition = { tabPopEnter(this) },
                    popExitTransition = { tabPopExit(this) },
                ) {
                    composable(Routes.CHAT) {
                        ChatScreen(
                            container = container,
                            owner = tabOwner,
                            onOpenSidebar = { onSidebarOpenChange(true) },
                            onOpenMap = { navController.navigate(Routes.MAP) },
                        )
                    }
                    composable(Routes.SKILLS) {
                        SkillsScreen(
                            container = container,
                            owner = tabOwner,
                            onBack = { navController.popBackStack() },
                        )
                    }
                    composable(Routes.CALENDAR) {
                        CalendarScreen(
                            container = container,
                            owner = tabOwner,
                            onBack = { navController.popBackStack() },
                            onRequestLogin = requestLogin,
                            onOpenSkills = { openSection(Routes.SKILLS) },
                        )
                    }
                    composable(Routes.READING) {
                        ReadingScreen(
                            container = container,
                            owner = tabOwner,
                            onBack = { navController.popBackStack() },
                            onRequestLogin = requestLogin,
                            onOpenSkills = { openSection(Routes.SKILLS) },
                        )
                    }
                    composable(Routes.PROFILE) {
                        ProfileScreen(
                            container = container,
                            owner = tabOwner,
                            onBack = { navController.popBackStack() },
                            onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                            onOpenReading = { openSection(Routes.READING) },
                            onOpenMap = { navController.navigate(Routes.MAP) },
                            // 游客点头像不跳转，由 ProfileScreen 自己判断后再回调。
                            onOpenAccount = { navController.navigate(Routes.ACCOUNT) },
                            onHandleReminder = { prompt ->
                                // 把后端给的处理话术带到聊天输入框，由用户自己决定是否发送。
                                container.repository.pendingDraftFlow.value = prompt
                                navController.navigate(Routes.CHAT) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                        )
                    }
                    composable(Routes.ACCOUNT) {
                        AccountScreen(
                            container = container,
                            onBack = { navController.popBackStack() },
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
                        MapScreen(
                            container = container,
                            onBack = { navController.popBackStack() },
                            onRequestLogin = requestLogin,
                            onOpenSkills = { openSection(Routes.SKILLS) },
                        )
                    }
                    composable(Routes.SETTINGS) {
                        SettingsScreen(
                            container = container,
                            onBack = { navController.popBackStack() },
                            onOpenPersonalization = { navController.navigate(Routes.PERSONALIZATION) },
                        )
                    }
                    composable(Routes.PERSONALIZATION) {
                        PersonalizationScreen(
                            container = container,
                            onBack = { navController.popBackStack() },
                        )
                    }
                }
            }
        }

        // 左侧滑出式侧边栏覆盖层（含 5/6 抽屉 + 1/6 压暗遮罩）。
        FlorisSidebar(
            open = sidebarOpen,
            onClose = { onSidebarOpenChange(false) },
            state = sidebarState,
            onNewChat = {
                onSidebarOpenChange(false)
                chatViewModel.newConversation()
            },
            onOpenConversation = { id ->
                onSidebarOpenChange(false)
                scope.launch { chatViewModel.openConversation(id) }
            },
            onOpenPlace = {
                onSidebarOpenChange(false)
                navController.navigate(Routes.MAP)
            },
            onOpenCalendar = {
                onSidebarOpenChange(false)
                openSection(Routes.CALENDAR)
            },
            onOpenReading = {
                onSidebarOpenChange(false)
                openSection(Routes.READING)
            },
            onOpenAccount = {
                onSidebarOpenChange(false)
                navController.navigate(Routes.ACCOUNT)
            },
            onOpenSkills = {
                onSidebarOpenChange(false)
                openSection(Routes.SKILLS)
            },
            onOpenReminders = {
                onSidebarOpenChange(false)
                openSection(Routes.PROFILE)
            },
            onOpenSettings = {
                onSidebarOpenChange(false)
                navController.navigate(Routes.SETTINGS)
            },
        )
    }
}

@Composable
private fun rememberSessionViewModelStoreOwner(sessionKey: String): ViewModelStoreOwner {
    val store = remember(sessionKey) { ViewModelStore() }
    val owner = remember(store) { object : ViewModelStoreOwner {
        override val viewModelStore: ViewModelStore = store
    } }
    DisposableEffect(store) {
        onDispose { store.clear() }
    }
    return owner
}

/**
 * 页面转场动画。
 *
 * 底部 Tab 之间：160ms 淡入淡出 + 极轻微放大，够短不拖沓，
 * 又比硬切有明显的丝滑感（从技能/阅读/日程/我的回聊天也走这条）。
 * 二级页面（历史/地图/设置/个人信息）：从右侧滑入、返回滑回右侧。
 */
private const val TAB_FADE_MS = 160
private val SECONDARY_ROUTES = setOf(
    Routes.HISTORY, Routes.MAP, Routes.SETTINGS, Routes.PERSONALIZATION, Routes.ACCOUNT,
)

private fun AnimatedContentTransitionScope<NavBackStackEntry>.isSecondary(): Boolean =
    targetState.destination.route in SECONDARY_ROUTES ||
        initialState.destination.route in SECONDARY_ROUTES

private fun tabEnter(scope: AnimatedContentTransitionScope<NavBackStackEntry>): EnterTransition =
    if (scope.isSecondary()) {
        slideInHorizontally(tween(280, easing = FastOutSlowInEasing)) { it } + fadeIn(tween(200))
    } else {
        fadeIn(tween(TAB_FADE_MS)) + scaleIn(tween(TAB_FADE_MS), initialScale = 0.985f)
    }

private fun tabExit(scope: AnimatedContentTransitionScope<NavBackStackEntry>): ExitTransition =
    if (scope.isSecondary()) {
        // 一级页轻微左移并淡出，形成层次感而不是硬切。
        slideOutHorizontally(tween(280, easing = FastOutSlowInEasing)) { -it / 6 } + fadeOut(tween(220))
    } else {
        fadeOut(tween(TAB_FADE_MS)) + scaleOut(tween(TAB_FADE_MS), targetScale = 0.985f)
    }

private fun tabPopEnter(scope: AnimatedContentTransitionScope<NavBackStackEntry>): EnterTransition =
    if (scope.isSecondary()) {
        slideInHorizontally(tween(280, easing = FastOutSlowInEasing)) { -it / 6 } + fadeIn(tween(200))
    } else {
        fadeIn(tween(TAB_FADE_MS)) + scaleIn(tween(TAB_FADE_MS), initialScale = 0.985f)
    }

private fun tabPopExit(scope: AnimatedContentTransitionScope<NavBackStackEntry>): ExitTransition =
    if (scope.isSecondary()) {
        // 返回键：二级页顺着来的方向滑回右侧，自然收起。
        slideOutHorizontally(tween(280, easing = FastOutSlowInEasing)) { it } + fadeOut(tween(240))
    } else {
        fadeOut(tween(TAB_FADE_MS)) + scaleOut(tween(TAB_FADE_MS), targetScale = 0.985f)
    }

@Composable
private fun Splash() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        AuroraOrb(size = 84.dp)
    }
}
