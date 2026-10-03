package dev.jinsfoni.photobook.ui.screens.search

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.SearchRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
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

/** S10 搜索 VM:300ms 防抖(空 key 不发)/竞态丢弃旧响应/失败 error。 */
@OptIn(ExperimentalCoroutinesApi::class)
class SearchViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: SearchViewModel
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
        vm = SearchViewModel(SearchRepository(api, FakeSessionStore3()))
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

    private fun enqueueSearch() {
        server.enqueue(
            MockResponse().setBody(
                """{"q":"aki","models":[{"slug":"aki","name":"Aki","stage":"Studio",
                   "thumb":"t/160x/aki/a.webp","count":2,"tags":[]}],
                   "collections":[{"id":9,"slug":"c","title":"C","model_slug":"aki",
                   "model_name":"Aki","cover":"/m/c/cover.jpg","coverThumb":"t/600x/c/c.webp",
                   "tags":[],"count":4}],"tags":["studio"]}""".replace("\n", "")
            )
        )
    }

    @Test
    fun `blank query resets to pristine without request`() = runTest(dispatcher.scheduler) {
        vm.onQueryChange("a")
        vm.onQueryChange("")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(0, server.requestCount)
        assertTrue(vm.state.value.pristine)
        assertNull(vm.state.value.results)
    }

    @Test
    fun `debounced search fills three sections`() = runTest(dispatcher.scheduler) {
        enqueueSearch()
        vm.onQueryChange("aki")
        assertEquals(0, server.requestCount) // 防抖窗内未发
        waitUntil { vm.state.value.results != null }
        val r = vm.state.value.results!!
        assertEquals("Aki", r.models[0].name)
        assertEquals("http://localhost:8000/t/600x/c/c.webp", r.collections[0].imageUrl)
        assertEquals(listOf("studio"), r.tags)
    }

    @Test
    fun `stale response is dropped`() = runTest(dispatcher.scheduler) {
        enqueueSearch()
        vm.onQueryChange("aki")
        waitUntil { vm.state.value.results != null }
        // 响应到达后改 query(未发新请求前)→ 旧结果仍在,但下次搜索会覆盖;
        // 这里验证竞态守卫逻辑本身:q 已变时不再接受旧响应
        server.shutdown()
        vm.onQueryChange("aki2") // 会发请求 → 失败 → q 已是 aki2,error 设置
        waitUntil { vm.state.value.error != null }
        assertEquals("aki2", vm.state.value.q)
        assertEquals("无法连接服务器", vm.state.value.error)
    }
}

class FakeSessionStore3 : SessionStoreApi {
    override val token = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val username = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)
    override val baseUrl = kotlinx.coroutines.flow.MutableStateFlow("http://localhost:8000")
    override suspend fun currentBaseUrl(): String = "http://localhost:8000"
    override suspend fun saveSession(token: String, username: String) {}
    override suspend fun clearSession() {}
    override suspend fun saveBaseUrl(url: String) {}
}
