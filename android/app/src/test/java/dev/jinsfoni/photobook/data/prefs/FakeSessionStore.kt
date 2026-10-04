package dev.jinsfoni.photobook.data.prefs

import dev.jinsfoni.photobook.core.design.ThemeMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * 内存桩:替代 SessionStore(它需要 Android Context)。
 * 各 ViewModel 测试复用;档案/主题/语言 M3 起纳入。
 */
open class FakeSessionStore : SessionStoreApi {

    private companion object {
        const val DEFAULT = "http://localhost:8000"
    }

    var saved: Pair<String, String>? = null

    val tokenFlow = MutableStateFlow<String?>(null)
    val profilesFlow = MutableStateFlow<List<ServerProfile>>(emptyList())
    val activeIdFlow = MutableStateFlow<String?>(null)
    val themeFlow = MutableStateFlow(ThemeMode.LIGHT)
    val localeFlow = MutableStateFlow("")

    override val token: Flow<String?> = tokenFlow
    override val username: Flow<String?> = MutableStateFlow<String?>(null)
    override val baseUrl: Flow<String> = kotlinx.coroutines.flow.combine(profilesFlow, activeIdFlow) { ps, id ->
        (ps.firstOrNull { it.id == id } ?: ps.firstOrNull())?.baseUrl ?: DEFAULT
    }

    override val profiles: Flow<List<ServerProfile>> = profilesFlow
    override val activeProfileId: Flow<String?> = activeIdFlow
    override val theme: Flow<ThemeMode> = themeFlow
    override val locale: Flow<String> = localeFlow

    override suspend fun currentBaseUrl(): String =
        (profilesFlow.value.firstOrNull { it.id == activeIdFlow.value }
            ?: profilesFlow.value.firstOrNull())?.baseUrl ?: DEFAULT
    override suspend fun currentToken(): String = tokenFlow.value.orEmpty()

    override suspend fun saveSession(token: String, username: String) {
        saved = token to username
        tokenFlow.value = token
        // 同步活动档案(多档案语义)
        val id = activeIdFlow.value ?: profilesFlow.value.firstOrNull()?.id ?: return
        updateProfile(id) { it.copy(token = token, username = username) }
    }

    override suspend fun clearSession() {
        saved = null
        tokenFlow.value = null
        val id = activeIdFlow.value ?: profilesFlow.value.firstOrNull()?.id ?: return
        updateProfile(id) { it.copy(token = "", username = "") }
    }

    override suspend fun saveBaseUrl(url: String) {
        val id = activeIdFlow.value ?: profilesFlow.value.firstOrNull()?.id ?: return
        updateProfile(id) { it.copy(baseUrl = url.trimEnd('/')) }
    }

    override suspend fun addProfile(baseUrl: String, token: String, username: String): ServerProfile {
        val normalized = baseUrl.trimEnd('/')
        val existing = profilesFlow.value.firstOrNull { it.baseUrl == normalized }
        val profile = existing?.copy(token = token, username = username)
            ?: ServerProfile(
                id = "p-${profilesFlow.value.size + 1}",
                baseUrl = normalized,
                username = username,
                token = token,
            )
        profilesFlow.value = profilesFlow.value.filter { it.id != profile.id } + profile
        activeIdFlow.value = profile.id
        tokenFlow.value = token.ifBlank { null }
        return profile
    }

    override suspend fun setActiveProfile(id: String) {
        if (profilesFlow.value.any { it.id == id }) {
            activeIdFlow.value = id
            tokenFlow.value = profilesFlow.value.firstOrNull { it.id == id }
                ?.token?.takeIf { it.isNotBlank() }
        }
    }

    override suspend fun removeProfile(id: String) {
        val rest = profilesFlow.value.filter { it.id != id }
        profilesFlow.value = rest
        if (activeIdFlow.value == id) {
            val next = rest.firstOrNull()
            activeIdFlow.value = next?.id
            tokenFlow.value = next?.token?.takeIf { it.isNotBlank() }
        }
    }

    override suspend fun saveTheme(mode: ThemeMode) { themeFlow.value = mode }

    override suspend fun saveLocale(tag: String) { localeFlow.value = tag }

    private fun updateProfile(id: String, transform: (ServerProfile) -> ServerProfile) {
        profilesFlow.value = profilesFlow.value.map { if (it.id == id) transform(it) else it }
    }
}
