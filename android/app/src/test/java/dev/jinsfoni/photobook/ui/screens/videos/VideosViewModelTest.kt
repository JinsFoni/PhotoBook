package dev.jinsfoni.photobook.ui.screens.videos

import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.tempCacheDir
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * 写真视频列表 VM(与写真列表平行的一套):首载/排序参数/分页/封面帧 URL 拼接。
 * MockWebServer 走真实 Retrofit 反序列化 —— 校验服务端 videos 载荷形状
 * 与客户端映射(coverThumb → imageUrl)对得上。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class VideosViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: VideosViewModel
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
        vm = VideosViewModel(CollectionsRepository(api, FakeSessionStore(), tempCacheDir()))
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun page(vararg slugs: String, total: Int = 20) {
        val items = slugs.joinToString(",") { slug ->
            """{"id":1,"slug":"$slug","title":"T$slug","model_slug":"m","model_name":"M",
               "cover":"m/$slug/c0.mp4","coverThumb":"t/s900/m/$slug/c0.mp4.webp",
               "tags":[],"count":3}"""
        }
        server.enqueue(
            MockResponse().setBody("""{"items":[${items}],"total":$total,"page":1,"pageSize":20}""")
        )
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
    fun `start loads first page and maps cover thumb`() = runTest(dispatcher.scheduler) {
        page("clip-a", "clip-b")
        vm.start(null)
        waitUntil { vm.state.value.items.isNotEmpty() }
        val req = server.takeRequest()
        assertTrue(req.path!!.startsWith("/videos"))
        assertTrue(req.path!!.contains("page=1"))
        assertEquals(2, vm.state.value.items.size)
        assertEquals(20, vm.state.value.total)
        // 封面帧 webp 与图片 thumb 同构:base + coverThumb 前缀 rel
        assertEquals(
            "http://localhost:8000/t/s900/m/clip-a/c0.mp4.webp",
            vm.state.value.items[0].imageUrl,
        )
        assertEquals(3, vm.state.value.items[0].count)
    }

    @Test
    fun `sort switch passes added_oldest`() = runTest(dispatcher.scheduler) {
        page("clip-a")
        vm.start(null)
        waitUntil { vm.state.value.items.isNotEmpty() }
        page("clip-b")
        vm.setSort(VideoAlbumSort.ADDED_OLDEST)
        waitUntil { vm.state.value.items.firstOrNull()?.slug == "clip-b" }
        server.takeRequest()
        assertTrue(server.takeRequest().path!!.contains("sort=added_oldest"))
    }

    @Test
    fun `loadMore appends and stops at total`() = runTest(dispatcher.scheduler) {
        page("a", "b", total = 2)
        vm.start(null)
        waitUntil { vm.state.value.items.size == 2 }
        assertTrue(vm.state.value.endReached)
        vm.loadMore()                   // 应被挡住(不发请求)
        waitUntil { server.requestCount == 1 }
        assertEquals(1, server.requestCount)
        assertFalse(vm.state.value.loadingMore)
    }

    @Test
    fun `error on first load shows retry text`() = runTest(dispatcher.scheduler) {
        server.shutdown()
        vm.start(null)
        waitUntil { vm.state.value.error != null }
        assertEquals("无法连接服务器", vm.state.value.error)
    }
}
