package com.floris.android.ui.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
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

/** 客户端本地偏好：主题、语言、新手介绍、富搜索数量。 */
class AppPreferences(private val context: Context, scope: CoroutineScope) {

    private object Keys {
        val THEME = stringPreferencesKey("theme_mode")
        val LANGUAGE = stringPreferencesKey("language")
        val ONBOARDING_DONE = booleanPreferencesKey("onboarding_done")
        val WEB_RESULTS = intPreferencesKey("web_results")
        val IMAGE_CANDIDATES = intPreferencesKey("image_candidates")
    }

    private val _theme = MutableStateFlow(ThemeMode.SYSTEM)
    val theme: StateFlow<ThemeMode> = _theme.asStateFlow()

    private val _language = MutableStateFlow(Language.ZH_CN)
    val language: StateFlow<Language> = _language.asStateFlow()

    private val _onboardingDone = MutableStateFlow(true)
    val onboardingDone: StateFlow<Boolean> = _onboardingDone.asStateFlow()

    private val _webResults = MutableStateFlow(6)
    val webResults: StateFlow<Int> = _webResults.asStateFlow()

    private val _imageCandidates = MutableStateFlow(4)
    val imageCandidates: StateFlow<Int> = _imageCandidates.asStateFlow()

    init {
        scope.launch {
            val prefs = context.uiDataStore.data.first()
            _theme.value = prefs[Keys.THEME]?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() }
                ?: ThemeMode.SYSTEM
            _language.value = prefs[Keys.LANGUAGE]?.let { Language.fromTag(it) } ?: Language.ZH_CN
            _onboardingDone.value = prefs[Keys.ONBOARDING_DONE] ?: false
            _webResults.value = prefs[Keys.WEB_RESULTS] ?: 6
            _imageCandidates.value = prefs[Keys.IMAGE_CANDIDATES] ?: 4
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

    suspend fun setWebResults(value: Int) {
        val clamped = value.coerceIn(3, 12)
        _webResults.value = clamped
        context.uiDataStore.edit { it[Keys.WEB_RESULTS] = clamped }
    }

    suspend fun setImageCandidates(value: Int) {
        val clamped = value.coerceIn(0, 8)
        _imageCandidates.value = clamped
        context.uiDataStore.edit { it[Keys.IMAGE_CANDIDATES] = clamped }
    }
}
