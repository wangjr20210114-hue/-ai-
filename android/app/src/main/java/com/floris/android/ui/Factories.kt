package com.floris.android.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.floris.android.AppContainer
import com.floris.android.core.notify.ProactiveNotifier
import com.floris.android.ui.account.AccountViewModel
import com.floris.android.ui.auth.LoginViewModel
import com.floris.android.ui.calendar.CalendarViewModel
import com.floris.android.ui.chat.ChatViewModel
import com.floris.android.ui.history.HistoryViewModel
import com.floris.android.ui.maps.MapViewModel
import com.floris.android.ui.papers.ReadingViewModel
import com.floris.android.ui.profile.ProfileViewModel
import com.floris.android.ui.settings.SettingsViewModel
import com.floris.android.ui.skills.SkillsViewModel

private inline fun <reified VM : ViewModel> factory(crossinline create: () -> VM) =
    object : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = create() as T
    }

fun AppContainer.loginViewModelFactory() = factory { LoginViewModel(authManager) }
fun AppContainer.chatViewModelFactory() = factory { ChatViewModel(repository, json) }
fun AppContainer.historyViewModelFactory() = factory { HistoryViewModel(repository) }
fun AppContainer.skillsViewModelFactory() = factory { SkillsViewModel(repository, authManager) }
fun AppContainer.calendarViewModelFactory() = factory { CalendarViewModel(repository) }
fun AppContainer.mapViewModelFactory() = factory { MapViewModel(repository) }
fun AppContainer.readingViewModelFactory() = factory { ReadingViewModel(repository) }
fun AppContainer.profileViewModelFactory() = factory {
    ProfileViewModel(
        repository = repository,
        authManager = authManager,
        // 主动提醒同时推到系统通知栏——移动端相对网页端的优势。
        notifier = { items -> ProactiveNotifier.notifyAll(appContext, items) },
    )
}
fun AppContainer.settingsViewModelFactory() =
    factory { SettingsViewModel(repository, authManager, preferences) }
fun AppContainer.accountViewModelFactory() =
    factory { AccountViewModel(repository, authManager, preferences) }
