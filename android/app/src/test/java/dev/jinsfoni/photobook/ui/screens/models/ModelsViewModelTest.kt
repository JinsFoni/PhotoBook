package dev.jinsfoni.photobook.ui.screens.models

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.ModelsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/** S5 模特列表 VM:加载成功/URL 拼装/缓存命中不发请求/失败 error。 */
@OptIn(ExperimentalCoroutinesApi::class)
class ModelsViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: ModelsViewModel
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
        vm = ModelsViewModel(ModelsRepository(api, FakeSessionStore2()))
    }

    private fun waitUntil(cond: () -> Boolean) {
        var waited = 0L
        while (!cond() && waited < 5_000) {
            dispatcher.scheduler.advanceUntilIdle()
            Thread.sleep(25); waited += 25
        }
        dispatcher.scheduler.advanceUntilIdle()
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun enqueueModels() {
        server.enqueue(
            MockResponse().setBody(
                """{"items":[{"id":1,"slug":"aki","name":"Aki","stage":"Studio","gender":"female",
                   "age":24,"height":"165cm","measurements":"B85 W58 H86","since":"2024-03",
                   "tags":["studio"],"count":3,"photo_count":30,"featured":true,
                   "avatar":"media/models/aki/avatar.jpg"}],"total":1}""".replace("\n", "")
            )
        )
    }

    @Test
    fun `start loads and builds thumb url`() = runTest(dispatcher.scheduler) {
        enqueueModels()
        vm.start()
        waitUntil { vm.state.value.items.isNotEmpty() }
        val m = vm.state.value.items[0]
        assertEquals("Aki", m.name)
        assertEquals("http://localhost:8000/t/600x900/media/models/aki/avatar.jpg.webp", m.imageUrl)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `list cache hits without new request`() = runTest(dispatcher.scheduler) {
        enqueueModels()
        vm.start()
        waitUntil { vm.state.value.items.isNotEmpty() }
        vm.start() // 已加载 → 不再发请求
        assertEquals(1, server.requestCount)
        assertTrue(vm.state.value.items.isNotEmpty())
    }

    @Test
    fun `network failure sets error`() = runTest(dispatcher.scheduler) {
        server.shutdown()
        vm.start()
        waitUntil { vm.state.value.error != null }
        assertEquals("无法连接服务器", vm.state.value.error)
        assertTrue(vm.state.value.items.isEmpty())
    }
}

class FakeSessionStore2 : SessionStoreApi {
    override val token = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val username = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val baseUrl = kotlinx.coroutines.flow.MutableStateFlow("http://localhost:8000")
    override suspend fun currentBaseUrl(): String = "http://localhost:8000"
    override suspend fun saveSession(token: String, username: String) {}
    override suspend fun clearSession() {}
    override suspend fun saveBaseUrl(url: String) {}
}
