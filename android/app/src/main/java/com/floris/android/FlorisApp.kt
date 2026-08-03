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

    /** 供需要 Context 的边缘能力使用（通知栏、相册写入）。 */
    val appContext: Context get() = context.applicationContext

    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private val tokenStore = TokenStore(context, json)

    private val cloudBaseApi = CloudBaseAuthApi.create(
        baseUrl = BuildConfig.CLOUDBASE_AUTH_BASE_URL,
        envId = BuildConfig.CLOUDBASE_ENV_ID,
        publishableKey = BuildConfig.CLOUDBASE_PUBLISHABLE_KEY,
        json = json,
    )

    val authManager: AuthManager = AuthManager(
        cloudBaseApi = cloudBaseApi,
        envId = BuildConfig.CLOUDBASE_ENV_ID,
        tokenStore = tokenStore,
        json = json,
        exchange = { accessToken ->
            florisClient.api.exchangeMobileSession(
                buildJsonObject { put("access_token", accessToken) },
            )
        },
        guestExchange = { florisClient.obtainGuestSession() },
    )

    val florisClient: FlorisClient by lazy { FlorisClient(authManager, json) }

    val repository: FlorisRepository by lazy {
        FlorisRepository(florisClient, tokenStore, json, context)
    }

    /** 客户端本地偏好（主题、语言、新手介绍、富搜索数量）。 */
    val preferences: com.floris.android.ui.prefs.AppPreferences by lazy {
        com.floris.android.ui.prefs.AppPreferences(
            context,
            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Main),
        )
    }
}
