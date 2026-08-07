package com.floris.android.ui.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private val Context.uiDataStore by preferencesDataStore(name = "floris_ui_prefs")

enum class ThemeMode { SYSTEM, LIGHT, DARK }

/** 纯客户端偏好：主题、语言与新手介绍。业务偏好始终由 dev 后端持久化。 */
class AppPreferences(private val context: Context, scope: CoroutineScope) {

    private object Keys {
        val THEME = stringPreferencesKey("theme_mode")
        val LANGUAGE = stringPreferencesKey("language")
        val ONBOARDING_DONE = booleanPreferencesKey("onboarding_done")
    }

    private val _theme = MutableStateFlow(ThemeMode.SYSTEM)
    val theme: StateFlow<ThemeMode> = _theme.asStateFlow()

    private val _language = MutableStateFlow(Language.ZH_CN)
    val language: StateFlow<Language> = _language.asStateFlow()

    private val _onboardingDone = MutableStateFlow(true)
    val onboardingDone: StateFlow<Boolean> = _onboardingDone.asStateFlow()

    init {
        scope.launch {
            val prefs = context.uiDataStore.data.first()
            _theme.value = prefs[Keys.THEME]?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() }
                ?: ThemeMode.SYSTEM
            _language.value = prefs[Keys.LANGUAGE]?.let { Language.fromTag(it) } ?: Language.ZH_CN
            _onboardingDone.value = prefs[Keys.ONBOARDING_DONE] ?: false
        }
    }

    suspend fun setTheme(mode: ThemeMode) {
        _theme.value = mode
        context.uiDataStore.edit { it[Keys.THEME] = mode.name }
    }

    /**
     * 顶栏一键切换白天 / 黑夜。传入当前是否深色（可能来自系统），
     * 切换后固定为显式的 LIGHT / DARK，不再跟随系统。
     */
    suspend fun toggleTheme(currentlyDark: Boolean) {
        setTheme(if (currentlyDark) ThemeMode.LIGHT else ThemeMode.DARK)
    }

    suspend fun setLanguage(language: Language) {
        _language.value = language
        context.uiDataStore.edit { it[Keys.LANGUAGE] = language.tag }
    }

    suspend fun setOnboardingDone(done: Boolean) {
        _onboardingDone.value = done
        context.uiDataStore.edit { it[Keys.ONBOARDING_DONE] = done }
    }

}
