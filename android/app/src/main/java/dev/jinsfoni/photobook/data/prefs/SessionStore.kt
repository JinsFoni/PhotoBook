package dev.jinsfoni.photobook.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore(name = "photobook")

/**
 * 会话与服务器地址持久化(DataStore Preferences;Proto 插件与 AGP9 DSL 不兼容,见计划)。
 * token 供 AuthInterceptor 注入 Bearer;baseUrl 默认指向模拟器宿主。
 */
@Singleton
class SessionStore @Inject constructor(@ApplicationContext private val context: Context) :
    SessionStoreApi {

    private val tokenKey = stringPreferencesKey("token")
    private val usernameKey = stringPreferencesKey("username")
    private val baseUrlKey = stringPreferencesKey("base_url")

    override val token: Flow<String?> = context.dataStore.data.map { it[tokenKey] }
    override val username: Flow<String?> = context.dataStore.data.map { it[usernameKey] }

    /** 活动 profile 的 base URL(含 /api/mobile 前缀之前的 host 根)。 */
    override val baseUrl: Flow<String> =
        context.dataStore.data.map { it[baseUrlKey] ?: DEFAULT_BASE_URL }

    override suspend fun currentBaseUrl(): String = baseUrl.first()

    override suspend fun saveSession(token: String, username: String) {
        context.dataStore.edit {
            it[tokenKey] = token
            it[usernameKey] = username
        }
    }

    override suspend fun clearSession() {
        context.dataStore.edit {
            it.remove(tokenKey)
            it.remove(usernameKey)
        }
    }

    override suspend fun saveBaseUrl(url: String) {
        context.dataStore.edit { it[baseUrlKey] = url.trimEnd('/') }
    }

    companion object {
        /** 模拟器宿主回环;真机改局域网 IP(S9 做设置 UI)。 */
        // baseUrl 约定含 API 前缀(如 http://host:8000/api/mobile/),Retrofit 相对路径直接拼在后面
        const val DEFAULT_BASE_URL = "http://192.168.0.102:8000/api/mobile/"
    }
}
