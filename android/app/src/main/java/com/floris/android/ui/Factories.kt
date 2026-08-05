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
import com.floris.android.ui.settings.PersonalizationViewModel
import com.floris.android.ui.skills.SkillsViewModel

private inline fun <reified VM : ViewModel> factory(crossinline create: () -> VM) =
    object : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = create() as T
    }

fun AppContainer.loginViewModelFactory() = factory { LoginViewModel(authManager, strings) }
fun AppContainer.chatViewModelFactory() = factory {
    ChatViewModel(repository, chatRuntimeStore, json, strings)
}
fun AppContainer.historyViewModelFactory() = factory { HistoryViewModel(repository, strings) }
fun AppContainer.skillsViewModelFactory() = factory {
    SkillsViewModel(repository, authManager, strings)
}
fun AppContainer.calendarViewModelFactory() = factory { CalendarViewModel(repository, strings) }
fun AppContainer.mapViewModelFactory() = factory { MapViewModel(repository, strings) }
fun AppContainer.readingViewModelFactory() = factory { ReadingViewModel(repository, strings) }
fun AppContainer.profileViewModelFactory() = factory {
    ProfileViewModel(
        repository = repository,
        authManager = authManager,
        strings = strings,
        // 主动提醒同时推到系统通知栏——移动端相对网页端的优势。
        notifier = { items -> ProactiveNotifier.notifyAll(appContext, items) },
    )
}
fun AppContainer.settingsViewModelFactory() =
    factory { SettingsViewModel(repository, preferences, strings) }
fun AppContainer.personalizationViewModelFactory() =
    factory { PersonalizationViewModel(repository) }
fun AppContainer.accountViewModelFactory() =
    factory { AccountViewModel(repository, authManager, preferences, strings) }
