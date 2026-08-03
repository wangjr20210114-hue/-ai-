package com.floris.android.ui.navigation

import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.TransformOrigin
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.floris.android.AppContainer
import com.floris.android.ui.auth.LoginScreen
import com.floris.android.ui.calendar.CalendarScreen
import com.floris.android.ui.chat.ChatScreen
import com.floris.android.ui.history.HistoryScreen
import com.floris.android.ui.maps.MapScreen
import com.floris.android.ui.papers.PapersScreen
import com.floris.android.ui.profile.ProfileScreen
import com.floris.android.ui.search.SearchScreen
import com.floris.android.ui.settings.SettingsScreen
import com.floris.android.ui.skills.SkillsScreen
import com.floris.android.ui.components.AuroraOrb
import androidx.compose.ui.unit.dp

object Routes {
    const val LOGIN = "login"
    const val CHAT = "chat"
    const val SEARCH = "search"
    const val SKILLS = "skills"
    const val CALENDAR = "calendar"
    const val PROFILE = "profile"
    const val HISTORY = "history"
    const val MAP = "map"
    const val PAPERS = "papers"
    const val SETTINGS = "settings"
}

private data class Tab(val route: String, val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val tabs = listOf(
    Tab(Routes.CHAT, "聊天", Icons.Default.Email),
    Tab(Routes.SEARCH, "搜索", Icons.Default.Search),
    Tab(Routes.SKILLS, "技能", Icons.Default.Star),
    Tab(Routes.CALENDAR, "日程", Icons.Default.DateRange),
    Tab(Routes.PROFILE, "我的", Icons.Default.AccountCircle),
)

@Composable
fun FlorisNavHost(container: AppContainer, signedIn: Boolean, authLoading: Boolean) {
    val navController = rememberNavController()

    when {
        authLoading -> Splash()
        !signedIn -> LoginScreen(container = container)
        else -> {
            val backStack by navController.currentBackStackEntryAsState()
            val currentRoute = backStack?.destination?.route
            val showTabBar = currentRoute in tabs.map { it.route }

            Scaffold(
                bottomBar = {
                    if (showTabBar) {
                        NavigationBar(tonalElevation = 0.dp) {
                            tabs.forEach { tab ->
                                NavigationBarItem(
                                    selected = currentRoute == tab.route,
                                    onClick = {
                                        navController.navigate(tab.route) {
                                            popUpTo(navController.graph.findStartDestination().id) {
                                                saveState = true
                                            }
                                            launchSingleTop = true
                                            restoreState = true
                                        }
                                    },
                                    icon = { Icon(tab.icon, contentDescription = tab.label) },
                                    label = { Text(tab.label) },
                                    colors = NavigationBarItemDefaults.colors(
                                        indicatorColor = androidx.compose.material3.MaterialTheme.colorScheme.primaryContainer,
                                    ),
                                )
                            }
                        }
                    }
                },
            ) { padding ->
                NavHost(
                    navController = navController,
                    startDestination = Routes.CHAT,
                    modifier = Modifier.padding(padding),
                    enterTransition = { fadeIn() + scaleIn(initialScale = 0.98f, transformOrigin = TransformOrigin.Center) },
                    exitTransition = { fadeOut() + scaleOut(targetScale = 0.98f) },
                    popEnterTransition = { fadeIn() },
                    popExitTransition = { fadeOut() },
                ) {
                    composable(Routes.CHAT) {
                        ChatScreen(
                            container = container,
                            onOpenHistory = { navController.navigate(Routes.HISTORY) },
                            onOpenMap = { navController.navigate(Routes.MAP) },
                        )
                    }
                    composable(Routes.SEARCH) { SearchScreen(container = container) }
                    composable(Routes.SKILLS) { SkillsScreen(container = container) }
                    composable(Routes.CALENDAR) { CalendarScreen(container = container) }
                    composable(Routes.PROFILE) {
                        ProfileScreen(
                            container = container,
                            onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                            onOpenPapers = { navController.navigate(Routes.PAPERS) },
                            onOpenMap = { navController.navigate(Routes.MAP) },
                        )
                    }
                    composable(Routes.HISTORY) {
                        HistoryScreen(
                            container = container,
                            onBack = { navController.popBackStack() },
                            onOpenConversation = { navController.navigate(Routes.CHAT) { popUpTo(Routes.CHAT) { inclusive = true } } },
                        )
                    }
                    composable(Routes.MAP) { MapScreen(container = container, onBack = { navController.popBackStack() }) }
                    composable(Routes.PAPERS) { PapersScreen(container = container, onBack = { navController.popBackStack() }) }
                    composable(Routes.SETTINGS) { SettingsScreen(container = container, onBack = { navController.popBackStack() }) }
                }
            }
        }
    }
}

@Composable
private fun Splash() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        AuroraOrb(size = 88.dp)
    }
}
