package dev.jinsfoni.photobook.data.remote

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 多服务器请求落点重写(M3):
 * Retrofit 需要固定的 base URL,这里在拦截层把每个请求的 scheme/host/port
 * 替换为当前活动档案的地址(路径/查询原样保留)。Coil 图片 URL 由 Repo 用
 * baseUrl 拼出,天然跟随活动档案,不经过此层。
 */
@Singleton
class HostSelectionInterceptor @Inject constructor(
    private val session: SessionStoreApi,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val base = runBlocking { session.currentBaseUrl() }.toHttpUrl()
        val rewritten = request.url.newBuilder()
            .scheme(base.scheme)
            .host(base.host)
            .port(base.port)
            .build()
        return chain.proceed(
            if (rewritten == request.url) request
            else request.newBuilder().url(rewritten).build()
        )
    }
}
