package com.floris.android

import android.app.Application
import android.content.Context
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.CloudBaseAuthApi
import com.floris.android.core.auth.TokenStore
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.network.FlorisClient
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class FlorisApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}

/** Manual DI container — single owner of network, auth and repositories. */
class AppContainer(private val context: Context) {

    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private val tokenStore = TokenStore(context, json)

    private val cloudBaseApi = CloudBaseAuthApi.create(BuildConfig.CLOUDBASE_AUTH_BASE_URL, json)

    val authManager: AuthManager = AuthManager(
        cloudBaseApi = cloudBaseApi,
        publishableKey = BuildConfig.CLOUDBASE_PUBLISHABLE_KEY,
        tokenStore = tokenStore,
        json = json,
        exchange = { accessToken ->
            florisClient.api.exchangeMobileSession(
                buildJsonObject { put("access_token", accessToken) },
            )
        },
    )

    val florisClient: FlorisClient by lazy { FlorisClient(authManager, json) }

    val repository: FlorisRepository by lazy {
        FlorisRepository(florisClient, tokenStore, json, context)
    }
}
