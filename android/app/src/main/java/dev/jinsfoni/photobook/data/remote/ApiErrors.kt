package dev.jinsfoni.photobook.data.remote

import dev.jinsfoni.photobook.data.prefs.SessionStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Response
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

/** 读 DataStore token,注入 Bearer(无 token 不加头)。 */
@Singleton
class AuthInterceptor @Inject constructor(private val session: SessionStore) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val token = runBlocking { session.token.firstOrNull() }
        val request = if (token.isNullOrBlank()) {
            chain.request()
        } else {
            chain.request().newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        }
        return chain.proceed(request)
    }
}

/**
 * 错误体转 ApiException:
 * - 4xx/5xx 带 {"error":{...}} → ApiException(code,message)
 * - 其他 HTTP 错误 → ApiException(SERVER)
 * - 网络异常(IO 等)由调用侧 catch 包成 ApiException(NETWORK)(见 safeCall)。
 */
object ApiErrors {

    val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    fun parseErrorBody(body: String?, httpStatus: Int): ApiException? {
        if (body.isNullOrBlank()) return null
        return try {
            val obj = json.parseToJsonElement(body)
            val error = (obj as? JsonObject)?.get("error")?.jsonObject ?: return null
            val code = error["code"]?.jsonPrimitive?.content
            val message = error["message"]?.jsonPrimitive?.content
            ApiException(
                code = code ?: ApiException.SERVER,
                message = message ?: "HTTP $httpStatus",
                httpStatus = httpStatus,
            )
        } catch (_: Exception) {
            null
        }
    }
}

/** 统一包一层:HttpException → ApiException;IO/未知 → NETWORK。 */
/** 网络异常消息(纯 JVM 层,不能 stringResource;ViewModel 显示时映射 R.string.network_unreachable)。 */
const val NETWORK_MSG = "网络不可达"

suspend fun <T> safeCall(block: suspend () -> T): T = try {
    block()
} catch (e: HttpException) {
    val body = e.response()?.errorBody()?.string()
    throw ApiErrors.parseErrorBody(body, e.code())
        ?: ApiException(ApiException.SERVER, "HTTP ${e.code()}", e.code(), e)
} catch (e: java.io.IOException) {
    throw ApiException(ApiException.NETWORK, NETWORK_MSG, cause = e)
}
