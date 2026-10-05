package dev.jinsfoni.photobook.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.data.remote.ApiErrors
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore(name = "photobook")

/**
 * 会话与服务器档案持久化(DataStore Preferences)。
 * M3 起支持多服务器档案:profiles 存 JSON 数组,activeProfileId 指向活动档案;
 * 旧单值键(base_url/token/username)在首次读取时迁移为首个档案。
 */
@Singleton
class SessionStore @Inject constructor(@ApplicationContext private val context: Context) :
    SessionStoreApi {

    private val json = ApiErrors.json

    private val tokenKey = stringPreferencesKey("token")
    private val usernameKey = stringPreferencesKey("username")
    private val baseUrlKey = stringPreferencesKey("base_url")
    private val profilesKey = stringPreferencesKey("profiles")
    private val activeProfileKey = stringPreferencesKey("active_profile")
    private val themeKey = stringPreferencesKey("theme")
    private val liquidGlassKey = booleanPreferencesKey("liquid_glass")
    private val loadOriginalKey = booleanPreferencesKey("load_original")
    private val localeKey = stringPreferencesKey("locale")

    override val token: Flow<String?> = context.dataStore.data.map { prefs ->
        activeProfile(prefs)?.token?.takeIf { it.isNotBlank() } ?: prefs[tokenKey]
    }

    override val username: Flow<String?> = context.dataStore.data.map { prefs ->
        activeProfile(prefs)?.username?.takeIf { it.isNotBlank() } ?: prefs[usernameKey]
    }

    /** 活动 profile 的 base URL(含 /api/mobile 前缀之前的 host 根)。 */
    override val baseUrl: Flow<String> = context.dataStore.data.map { prefs ->
        activeProfile(prefs)?.baseUrl ?: prefs[baseUrlKey] ?: DEFAULT_BASE_URL
    }

    override val profiles: Flow<List<ServerProfile>> = context.dataStore.data.map { prefs ->
        loadProfiles(prefs)
    }

    override val activeProfileId: Flow<String?> = context.dataStore.data.map { prefs ->
        prefs[activeProfileKey] ?: loadProfiles(prefs).firstOrNull()?.id
    }

    override val theme: Flow<ThemeMode> = context.dataStore.data.map { prefs ->
        when (prefs[themeKey]) {
            "DARK" -> ThemeMode.DARK
            "BLUR" -> ThemeMode.BLUR
            "LIGHT" -> ThemeMode.LIGHT
            else -> ThemeMode.LIGHT
        }
    }

    override val liquidGlass: Flow<Boolean> =
        context.dataStore.data.map { prefs -> prefs[liquidGlassKey] ?: false }

    override val loadOriginal: Flow<Boolean> =
        context.dataStore.data.map { prefs -> prefs[loadOriginalKey] ?: false }

    override val locale: Flow<String> =
        context.dataStore.data.map { it[localeKey] ?: "" }

    override suspend fun currentBaseUrl(): String = baseUrl.first()

    override suspend fun currentToken(): String = token.first().orEmpty()

    override suspend fun saveSession(token: String, username: String) {
        context.dataStore.edit { prefs ->
            prefs[tokenKey] = token
            prefs[usernameKey] = username
            // 同步进活动档案(多档案下 token 随档案走)
            val list = loadProfiles(prefs).toMutableList()
            val activeId = prefs[activeProfileKey] ?: list.firstOrNull()?.id
            val idx = list.indexOfFirst { it.id == activeId }
            if (idx >= 0) list[idx] = list[idx].copy(token = token, username = username)
            prefs[profilesKey] = json.encodeToString(list)
        }
    }

    override suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(tokenKey)
            prefs.remove(usernameKey)
            val list = loadProfiles(prefs).toMutableList()
            val activeId = prefs[activeProfileKey] ?: list.firstOrNull()?.id
            val idx = list.indexOfFirst { it.id == activeId }
            if (idx >= 0) list[idx] = list[idx].copy(token = "", username = "")
            prefs[profilesKey] = json.encodeToString(list)
        }
    }

    override suspend fun saveBaseUrl(url: String) {
        val trimmed = url.trimEnd('/')
        context.dataStore.edit { prefs ->
            prefs[baseUrlKey] = trimmed
            // 已有档案时更新档案地址(无档案则等 addProfile 落档)
            val list = loadProfiles(prefs).toMutableList()
            val activeId = prefs[activeProfileKey] ?: list.firstOrNull()?.id
            val idx = list.indexOfFirst { it.id == activeId }
            if (idx >= 0) list[idx] = list[idx].copy(baseUrl = trimmed)
            prefs[profilesKey] = json.encodeToString(list)
        }
    }

    override suspend fun addProfile(
        baseUrl: String,
        token: String,
        username: String,
    ): ServerProfile {
        val normalized = baseUrl.trimEnd('/')
        var created = ServerProfile(id = UUID.randomUUID().toString(), baseUrl = normalized)
        context.dataStore.edit { prefs ->
            val list = loadProfiles(prefs).toMutableList()
            // 同地址去重:覆盖旧档案(刷新 token/username)
            val existing = list.indexOfFirst { it.baseUrl == normalized }
            val profile = if (existing >= 0) {
                list[existing] = list[existing].copy(token = token, username = username)
                list[existing]
            } else {
                ServerProfile(
                    id = UUID.randomUUID().toString(),
                    baseUrl = normalized,
                    username = username,
                    token = token,
                ).also { list.add(it) }
            }
            created = profile
            prefs[profilesKey] = json.encodeToString(list)
            prefs[activeProfileKey] = profile.id
        }
        return created
    }

    override suspend fun setActiveProfile(id: String) {
        context.dataStore.edit { prefs ->
            val list = loadProfiles(prefs)
            if (list.any { it.id == id }) {
                prefs[activeProfileKey] = id
                // 兼容旧键读取路径(token/baseUrl),保持双写
                list.firstOrNull { it.id == id }?.let { active ->
                    prefs[baseUrlKey] = active.baseUrl
                    if (active.token.isNotBlank()) prefs[tokenKey] = active.token
                    if (active.username.isNotBlank()) prefs[usernameKey] = active.username
                }
            }
        }
    }

    override suspend fun removeProfile(id: String) {
        context.dataStore.edit { prefs ->
            val list = loadProfiles(prefs).toMutableList()
            list.removeAll { it.id == id }
            prefs[profilesKey] = json.encodeToString(list)
            val stillActive = prefs[activeProfileKey] == id
            if (stillActive || prefs[activeProfileKey] == null) {
                val next = list.firstOrNull()
                if (next != null) {
                    prefs[activeProfileKey] = next.id
                    prefs[baseUrlKey] = next.baseUrl
                } else {
                    prefs.remove(activeProfileKey)
                    // 删光档案 = 登出态:活动地址回默认
                    prefs.remove(baseUrlKey)
                    prefs.remove(tokenKey)
                    prefs.remove(usernameKey)
                }
            }
        }
    }

    override suspend fun saveTheme(mode: ThemeMode) {
        context.dataStore.edit { it[themeKey] = mode.name }
    }

    override suspend fun saveLiquidGlass(enabled: Boolean) {
        context.dataStore.edit { it[liquidGlassKey] = enabled }
    }

    override suspend fun saveLoadOriginal(enabled: Boolean) {
        context.dataStore.edit { it[loadOriginalKey] = enabled }
    }

    override suspend fun saveLocale(tag: String) {
        context.dataStore.edit { it[localeKey] = tag }
    }

    /**
     * 档案列表:profiles 键优先;旧键(base_url/token/username)迁移为首个档案。
     * 自动愈合:M2 时代从不写 base_url(地址为编译期常量),早期版本可能把空列表
     * 固化成 "[]"——只要旧 token 仍在,按未迁移处理,用默认地址重建 legacy 档案。
     */
    internal fun loadProfiles(prefs: Preferences): List<ServerProfile> {
        val raw = prefs[profilesKey]
        if (!raw.isNullOrBlank()) {
            val parsed = runCatching {
                json.decodeFromString<List<ServerProfile>>(raw)
            }.getOrDefault(emptyList())
            if (parsed.isNotEmpty()) return parsed
        }
        val legacyToken = prefs[tokenKey]
        val url = prefs[baseUrlKey]
            ?: DEFAULT_BASE_URL.takeIf { !legacyToken.isNullOrBlank() }
            ?: return emptyList()
        return listOf(
            ServerProfile(
                id = "legacy",
                baseUrl = url,
                username = prefs[usernameKey].orEmpty(),
                token = legacyToken.orEmpty(),
            ),
        )
    }

    private fun activeProfile(prefs: Preferences): ServerProfile? {
        val list = loadProfiles(prefs)
        val activeId = prefs[activeProfileKey]
        return list.firstOrNull { it.id == activeId } ?: list.firstOrNull()
    }

    companion object {
        /** 模拟器宿主回环;真机改局域网 IP(S9 设置页可改)。 */
        // baseUrl 约定含 API 前缀(如 http://host:8000/api/mobile/),Retrofit 相对路径直接拼在后面
        const val DEFAULT_BASE_URL = "http://192.168.0.102:8000/api/mobile/"
    }
}
