package dev.jinsfoni.photobook.ui.screens.explore

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import okhttp3.MediaType.Companion.toMediaType

/** 发现页 VM:首载成功/网络失败/强制刷新(缓存穿透)。 */
@OptIn(ExperimentalCoroutinesApi::class)
class ExploreViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: ExploreViewModel
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
        val repo = CollectionsRepository(api, FakeSessionStore())
        vm = ExploreViewModel(repo)
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

    private fun enqueueDiscover() {
        server.enqueue(
            MockResponse().setBody(
                """{"featured":[{"id":1,"slug":"a","title":"A","model_slug":"m","model_name":"M1",
                   "cover":"/m/a/cover.jpg","coverThumb":"/t/900x/a/cover.webp","tags":["f"],"count":3}],
                   "latest":[{"id":2,"slug":"b","title":"B","model_slug":"m","model_name":"M2",
                   "cover":"/m/b/cover.jpg","coverThumb":"/t/900x/b/cover.webp","tags":[],"count":5}],
                   "models":[],"tags":[],"stats":{"collections":2,"models":2}}""".replace("\n", "")
            )
        )
    }

    @Test
    fun `init loads feed`() = runTest(dispatcher.scheduler) {
        enqueueDiscover()
        waitUntil { vm.state.value.feed != null }
        val feed = vm.state.value.feed
        assertNotNull(feed)
        assertEquals(1, feed!!.featured.size)
        assertEquals("A", feed.featured[0].title)
        // URL 拼装:coverThumb 相对路径 + base(无双重前缀)
        assertTrue(feed.featured[0].imageUrl!!.endsWith("/t/900x/a/cover.webp"))
        assertEquals("/discover", server.takeRequest().path)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `network failure sets error and retry recovers`() = runTest(dispatcher.scheduler) {
        enqueueDiscover()
        waitUntil { vm.state.value.feed != null }
        // 断网重试失败
        server.shutdown()
        vm.retry()
        waitUntil { vm.state.value.error != null }
        assertEquals("无法连接服务器,下拉重试", vm.state.value.error)
    }

    @Test
    fun `refresh forces cache bypass`() = runTest(dispatcher.scheduler) {
        enqueueDiscover()
        waitUntil { vm.state.value.feed != null }
        enqueueDiscover()
        vm.refresh()
        waitUntil { server.requestCount >= 2 }
        waitUntil { !vm.state.value.refreshing }
        assertNull(vm.state.value.error)
        assertEquals(2, server.requestCount)
    }
}

private class FakeSessionStore : SessionStoreApi {
    override val token = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val username = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val baseUrl = kotlinx.coroutines.flow.MutableStateFlow("http://localhost:8000")
    override suspend fun currentBaseUrl(): String = "http://localhost:8000"
    override suspend fun saveSession(token: String, username: String) {}
    override suspend fun clearSession() {}
    override suspend fun saveBaseUrl(url: String) {}
}
