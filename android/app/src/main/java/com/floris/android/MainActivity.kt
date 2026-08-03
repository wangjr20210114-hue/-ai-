package com.floris.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import com.floris.android.core.auth.AuthState
import com.floris.android.ui.navigation.FlorisNavHost
import com.floris.android.ui.theme.FlorisTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as FlorisApp
        lifecycleScope.launch { app.container.authManager.restore() }
        setContent {
            FlorisTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val authState by app.container.authManager.state.collectAsState()
                    FlorisNavHost(
                        container = app.container,
                        signedIn = authState is AuthState.SignedIn,
                        authLoading = authState is AuthState.Loading,
                    )
                }
            }
        }
    }
}
