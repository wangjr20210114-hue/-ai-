package com.floris.android.ui.navigation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.ConversationSummary
import com.floris.android.core.model.Profile
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** 侧边栏：会话列表 + 登录信息，均来自 Maker，客户端只做展示与转发。 */
class SidebarViewModel(
    private val repository: FlorisRepository,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val conversations: List<ConversationSummary> = emptyList(),
        val profile: Profile? = null,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init { refresh() }

    /**
     * @param force true 时总是请求后台；false 时优先使用本地缓存（游客侧边栏用）。
     */
    fun refresh(force: Boolean = true) {
        val fromCache = !force && repository.conversationCache.value != null
        if (!fromCache) _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            val conversations = runCatching {
                if (force) repository.listConversations()
                else repository.listConversationsCached()
            }
            val profile = runCatching { repository.getProfile() }
            _state.value = UiState(
                loading = false,
                conversations = conversations.getOrElse { _state.value.conversations },
                profile = profile.getOrNull(),
                error = conversations.exceptionOrNull()?.let {
                    strings.get(StringKey.HistoryLoadFailed)
                },
            )
        }
    }

    suspend fun open(id: String) = repository.setActiveConversationId(id)
}
