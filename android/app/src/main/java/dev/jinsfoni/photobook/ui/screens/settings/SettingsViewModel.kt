package dev.jinsfoni.photobook.ui.screens.settings

import android.app.LocaleManager
import android.content.Context
import android.os.Build
import android.os.LocaleList
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.jinsfoni.photobook.data.prefs.ServerProfile
import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SettingsUiState(
    val profiles: List<ServerProfile> = emptyList(),
    val activeProfileId: String? = null,
    val theme: ThemeMode = ThemeMode.LIGHT,
    /** 当前语言标签("" = 跟随系统);API 33+ 以 LocaleManager 为准。 */
    val locale: String = "",
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val session: SessionStoreApi,
    @ApplicationContext private val appContext: Context,
) : ViewModel() {

    val state = combine(session.profiles, session.activeProfileId, session.theme, session.locale) {
            profiles, activeId, theme, locale ->
        SettingsUiState(
            profiles = profiles,
            activeProfileId = activeId ?: profiles.firstOrNull()?.id,
            theme = theme,
            locale = if (Build.VERSION.SDK_INT >= 33) {
                val lm = appContext.getSystemService(LocaleManager::class.java)
                lm?.applicationLocales?.toLanguageTags().orEmpty().ifBlank { locale }
            } else locale,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SettingsUiState())

    /** 切换活动服务器档案。 */
    fun activateProfile(id: String) {
        viewModelScope.launch { session.setActiveProfile(id) }
    }

    /** 删除档案;删活动档案时若删光则回登录页(由 Screen 监听 loggedIn 处理)。 */
    fun removeProfile(id: String) {
        viewModelScope.launch { session.removeProfile(id) }
    }

    fun setTheme(mode: ThemeMode) {
        ThemeState.mode = mode
        viewModelScope.launch { session.saveTheme(mode) }
    }

    /** 语言切换:33+ 走系统 per-app locale(自动重建);31/32 存档 + recreate。 */
    fun setLocale(tag: String, recreate: () -> Unit) {
        if (Build.VERSION.SDK_INT >= 33) {
            val lm = appContext.getSystemService(LocaleManager::class.java)
            lm?.applicationLocales = if (tag.isBlank()) LocaleList.getEmptyLocaleList()
            else LocaleList.forLanguageTags(tag)
        } else {
            viewModelScope.launch { session.saveLocale(tag) }
            recreate()
        }
    }
}
