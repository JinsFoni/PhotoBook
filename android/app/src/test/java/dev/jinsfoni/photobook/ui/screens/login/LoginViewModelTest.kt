package dev.jinsfoni.photobook.ui.screens.login

import app.cash.turbine.test
import dev.jinsfoni.photobook.data.prefs.SessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.AuthRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.nio.file.Files

/**
 * 登录 VM 分支:空值校验/成功/401 错误体/网络失败。
 * 用 MockWebServer + 真 Retrofit(与生产同一解析路径)。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class LoginViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: LoginViewModel
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        server = MockWebServer()
        server.start()
        val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
        val api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .client(OkHttpClient())
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(MobileApi::class.java)
        // 真实 SessionStore 需要 Context;这里用临时目录包装最小实现不可行(DataStore 要求 Context),
        // 改用仅记录调用的桩:AuthRepository 只依赖 saveSession/clearSession/token 流。
        val repo = AuthRepository(api, FakeSessionStore())
        vm = LoginViewModel(repo)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun `blank submit shows validation error without request`() = runTest(dispatcher.scheduler) {
        vm.submit()
        assertEquals("请输入用户名和密码", vm.state.value.error)
        assertEquals(0, server.requestCount)
    }

    /** 真实 IO(OkHttp 线程)+ 虚拟 Main 调度:轮询并持续推进虚拟时间。 */
    private fun waitUntil(cond: () -> Boolean) {
        var waited = 0L
        while (!cond() && waited < 5_000) {
            dispatcher.scheduler.advanceUntilIdle()
            Thread.sleep(25); waited += 25
        }
        dispatcher.scheduler.advanceUntilIdle()
    }

    @Test
    fun `success emits event and clears error`() = runTest(dispatcher.scheduler) {
        server.enqueue(MockResponse().setBody("""{"token":"tk1","expires_at":"2026-01-01T00:00:00"}"""))
        server.enqueue(MockResponse().setBody("""{"username":"demo","role":"user"}"""))
        vm.onUsername("demo")
        vm.onPassword("demo123")
        vm.events.test {
            vm.submit()
            // OkHttp 在真实线程执行,虚拟时间推进不等真实 IO —— 轮询等 loading 结束
            var waited = 0L
            while (vm.state.value.loading && waited < 5_000) { Thread.sleep(25); waited += 25 }
            assertEquals(LoginEvent.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertFalse(vm.state.value.loading)
        assertNull(vm.state.value.error)
        assertEquals("/auth/login", server.takeRequest().path)
        assertEquals("/auth/me", server.takeRequest().path)
    }

    @Test
    fun `invalid credentials maps to friendly message`() = runTest(dispatcher.scheduler) {
        server.enqueue(MockResponse().setResponseCode(401)
            .setBody("""{"error":{"code":"invalid_credentials","message":"bad"}}"""))
        vm.onUsername("demo")
        vm.onPassword("wrong")
        vm.submit()
        waitUntil { vm.state.value.error != null }
        assertEquals("用户名或密码错误", vm.state.value.error)
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun `network failure maps to server unreachable`() = runTest(dispatcher.scheduler) {
        server.shutdown()
        vm.onUsername("demo")
        vm.onPassword("x")
        vm.submit()
        waitUntil { vm.state.value.error != null }
        assertEquals("无法连接服务器", vm.state.value.error)
    }
}

/** 内存桩:替代 SessionStore(它需要 Android Context)。 */
private class FakeSessionStore : dev.jinsfoni.photobook.data.prefs.SessionStoreApi {
    var saved: Pair<String, String>? = null
    private val flow = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val token: kotlinx.coroutines.flow.Flow<String?> = flow
    override val username: kotlinx.coroutines.flow.Flow<String?> =
        kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val baseUrl: kotlinx.coroutines.flow.Flow<String> =
        kotlinx.coroutines.flow.MutableStateFlow("http://localhost:8000")
    override suspend fun saveSession(token: String, username: String) { saved = token to username }
    override suspend fun clearSession() { saved = null }
    override suspend fun currentBaseUrl(): String = "http://localhost:8000"
    override suspend fun saveBaseUrl(url: String) {}
}
