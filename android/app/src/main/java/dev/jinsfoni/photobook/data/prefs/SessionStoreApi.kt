package dev.jinsfoni.photobook.data.prefs

import kotlinx.coroutines.flow.Flow

/** 会话/服务器存储抽象(生产 = DataStore;单测 = 内存桩)。 */
interface SessionStoreApi {
    val token: Flow<String?>
    val username: Flow<String?>
    val baseUrl: Flow<String>

    suspend fun currentBaseUrl(): String
    suspend fun saveSession(token: String, username: String)
    suspend fun clearSession()
    suspend fun saveBaseUrl(url: String)
}
