package com.floris.android.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.floris.android.AppContainer
import com.floris.android.ui.auth.LoginViewModel
import com.floris.android.ui.calendar.CalendarViewModel
import com.floris.android.ui.chat.ChatViewModel
import com.floris.android.ui.history.HistoryViewModel
import com.floris.android.ui.maps.MapViewModel
import com.floris.android.ui.papers.PapersViewModel
import com.floris.android.ui.profile.ProfileViewModel
import com.floris.android.ui.search.SearchViewModel
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
fun AppContainer.searchViewModelFactory() = factory { SearchViewModel(repository, json) }
fun AppContainer.skillsViewModelFactory() = factory { SkillsViewModel(repository) }
fun AppContainer.calendarViewModelFactory() = factory { CalendarViewModel(repository) }
fun AppContainer.mapViewModelFactory() = factory { MapViewModel(repository) }
fun AppContainer.papersViewModelFactory() = factory { PapersViewModel(repository) }
fun AppContainer.profileViewModelFactory() = factory { ProfileViewModel(repository, authManager) }
fun AppContainer.settingsViewModelFactory() = factory { SettingsViewModel(repository, authManager) }
