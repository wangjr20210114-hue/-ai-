package com.floris.android

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.lifecycleScope
import com.floris.android.core.auth.AuthState
import com.floris.android.core.notify.ProactiveNotifier
import com.floris.android.ui.navigation.FlorisNavHost
import com.floris.android.ui.prefs.LocalLanguage
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.ThemeMode
import com.floris.android.ui.prefs.t
import com.floris.android.ui.theme.FlorisTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* 用户拒绝也不影响主流程，提醒仍会在"我的"页内展示 */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as FlorisApp
        lifecycleScope.launch { app.container.authManager.restore() }

        // 主动提醒要走系统通知栏，先建好渠道并按需申请权限。
        ProactiveNotifier.ensureChannel(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            !ProactiveNotifier.hasPermission(this)
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // 从通知点进来时，把后端给的处理话术填进聊天输入框。
        consumeNotificationIntent(app, intent)

        setContent {
            val themeMode by app.container.preferences.theme.collectAsState()
            val language by app.container.preferences.language.collectAsState()
            val systemDark = isSystemInDarkTheme()
            val dark = when (themeMode) {
                ThemeMode.SYSTEM -> systemDark
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
            }
            CompositionLocalProvider(LocalLanguage provides language) {
                FlorisTheme(darkTheme = dark) {
                    Surface(modifier = Modifier.fillMaxSize()) {
                        val authState by app.container.authManager.state.collectAsState()
                        FlorisNavHost(
                            container = app.container,
                            signedIn = authState is AuthState.SignedIn,
                            authLoading = authState is AuthState.Loading,
                        )
                        DoubleBackToExit(onExit = { finish() })
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        consumeNotificationIntent(application as FlorisApp, intent)
    }

    private fun consumeNotificationIntent(app: FlorisApp, intent: Intent?) {
        val prompt = intent?.getStringExtra(ProactiveNotifier.EXTRA_ACTION_PROMPT)
            ?: return
        if (prompt.isBlank()) return
        app.container.repository.pendingDraftFlow.value = prompt
        // 只消费一次，避免旋转屏幕后重复填充。
        intent.removeExtra(ProactiveNotifier.EXTRA_ACTION_PROMPT)
    }
}

/**
 * 误触保护：返回键需要在 2 秒内连按两次才真正退出，
 * 第一次只提示。放在最外层，任何页面的返回都先由内层消费。
 */
@Composable
private fun DoubleBackToExit(onExit: () -> Unit) {
    val context = LocalContext.current
    val hint = t(StringKey.ExitConfirmToast)
    var lastPressedAt by remember { mutableLongStateOf(0L) }
    BackHandler(enabled = true) {
        val now = System.currentTimeMillis()
        if (now - lastPressedAt <= EXIT_CONFIRM_WINDOW_MS) {
            onExit()
        } else {
            lastPressedAt = now
            Toast.makeText(context, hint, Toast.LENGTH_SHORT).show()
        }
    }
}

private const val EXIT_CONFIRM_WINDOW_MS = 2000L
