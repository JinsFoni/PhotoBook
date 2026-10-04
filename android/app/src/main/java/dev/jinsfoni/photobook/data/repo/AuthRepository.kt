package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.dto.LoginRequestDto
import dev.jinsfoni.photobook.data.remote.dto.MeDto
import dev.jinsfoni.photobook.data.remote.safeCall
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/** 登录 → token/username 入库;logout 清库;me 供会话校验。 */
@Singleton
class AuthRepository @Inject constructor(
    private val api: MobileApi,
    private val session: SessionStoreApi,
) {

    /** 成功:token 持久化;失败:抛 ApiException(invalid_credentials/…),不入库。 */
    suspend fun login(username: String, password: String): MeDto {
        val result = safeCall { api.login(LoginRequestDto(username, password)) }
        // 立即用 token 校验一次,顺带拿 username(登录响应只有 token/expires_at)
        val token = result.token
        session.saveSession(token, username)
        return try {
            safeCall { api.me() }
        } catch (e: ApiException) {
            // me 失败不回滚登录(token 有效期由服务端管;避免弱网下误清)
            MeDto(username = username, role = "user")
        }
    }

    suspend fun logout() = session.clearSession()

    /** S9 添加服务器:登录到新地址并落档激活;失败抛 ApiException。 */
    suspend fun addServer(baseUrl: String, username: String, password: String): MeDto {
        val token = safeCall { api.login(LoginRequestDto(username, password)) }.token
        session.addProfile(baseUrl, token, username)
        return try {
            safeCall { api.me() }
        } catch (e: ApiException) {
            MeDto(username = username, role = "user")
        }
    }

    /** 本地是否有会话(启动时决定 S8/S1)。 */
    fun hasSession(): Flow<Boolean> =
        session.token.map { !it.isNullOrBlank() }
}
