package dev.jinsfoni.photobook.ui.screens.collections

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/** S2 VM:首载/排序参数/分页拼接/tag 过滤/收尾。 */
@OptIn(ExperimentalCoroutinesApi::class)
class CollectionsViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: CollectionsViewModel
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
        vm = CollectionsViewModel(CollectionsRepository(api, FakeSessionStore()))
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    /** 页响应:slug 前缀 s,共 total 张(每页 3 便于测分页)。 */
    private fun page(vararg slugs: String, total: Int = 20) {
        val items = slugs.joinToString(",") { slug ->
            """{"id":1,"slug":"$slug","title":"T$slug","model_slug":"m","model_name":"M",
               "cover":"/m/$slug/c.jpg","coverThumb":"/t/900x/$slug/c.webp","tags":[],"count":1}"""
        }
        server.enqueue(MockResponse().setBody("""{"items":[${items}],"total":$total,"page":1,"pageSize":20}"""))
    }

    private fun waitUntil(cond: () -> Boolean) {
        var waited = 0L
        while (!cond() && waited < 5_000) {
            dispatcher.scheduler.advanceUntilIdle()
            Thread.sleep(25); waited += 25
        }
        dispatcher.scheduler.advanceUntilIdle()
    }

    @Test
    fun `start loads first page with tag param`() = runTest(dispatcher.scheduler) {
        page("a", "b")
        vm.start("fashion")
        waitUntil { vm.state.value.items.isNotEmpty() }
        val req = server.takeRequest()
        assertTrue(req.path!!.contains("tag=fashion"))
        assertTrue(req.path!!.contains("page=1"))
        assertEquals(2, vm.state.value.items.size)
        assertEquals(20, vm.state.value.total)
    }

    @Test
    fun `loadMore appends pages until end`() = runTest(dispatcher.scheduler) {
        page("a", "b", "c")            // page 1: 3 items, total 20
        vm.start(null)
        waitUntil { vm.state.value.items.size == 3 }
        page("d", "e", "f")            // page 2
        vm.loadMore()
        waitUntil { vm.state.value.items.size == 6 }
        assertEquals(2, server.requestCount)
        assertTrue(server.takeRequest().path!!.contains("page=1"))
        assertTrue(server.takeRequest().path!!.contains("page=2"))
        assertFalse(vm.state.value.endReached)
    }

    @Test
    fun `toggleSort reloads with oldest`() = runTest(dispatcher.scheduler) {
        page("a")
        vm.start(null)
        waitUntil { vm.state.value.items.isNotEmpty() }
        page("b")
        vm.toggleSort()
        waitUntil { vm.state.value.items.firstOrNull()?.slug == "b" }
        server.takeRequest()            // 第一次(sort=latest)
        val p2 = server.takeRequest()   // 重载请求
        assertTrue(p2.path!!.contains("sort=oldest"))
    }

    @Test
    fun `loadMore stops when items exhausted`() = runTest(dispatcher.scheduler) {
        page("a", total = 1)            // total 1 → endReached
        vm.start(null)
        waitUntil { vm.state.value.items.size == 1 }
        assertTrue(vm.state.value.endReached)
        vm.loadMore()                   // 应被挡住
        waitUntil { server.requestCount == 1 }
        assertEquals(1, server.requestCount)
    }
}

