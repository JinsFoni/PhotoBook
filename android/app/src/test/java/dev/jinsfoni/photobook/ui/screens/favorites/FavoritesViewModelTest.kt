package dev.jinsfoni.photobook.ui.screens.favorites

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
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
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import okhttp3.MediaType.Companion.toMediaType
import dev.jinsfoni.photobook.data.repo.FavoritesRepository

/** S7 收藏页 VM:resolve 成功三段填充 / 网络失败 error / Tab 切换保留数据。 */
@OptIn(ExperimentalCoroutinesApi::class)
class FavoritesViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: FavoritesViewModel
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
        val favoritesRepo = FavoritesRepository(api, FakeSessionStore())
        vm = FavoritesViewModel(favoritesRepo, api, FakeSessionStore())
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

    private fun enqueueResolve() {
        server.enqueue(
            MockResponse().setBody(
                """{"models":[{"id":1,"slug":"m","name":"Aki","stage":"Studio","gender":"female",
                   "age":24,"height":"165cm","measurements":"B85 W58 H86","since":"2024-03",
                   "tags":["studio"],"count":2,"photo_count":30,"featured":true,
                   "avatar":"media/models/m/avatar.jpg"}],
                   "collections":[{"id":2,"slug":"c","title":"C","model_slug":"m","model_name":"Aki",
                   "cover":"/m/c/cover.jpg","coverThumb":"t/600/c/cover.webp","tags":["x"],"count":9}],
                   "photos":[{"key":"c:1","slug":"c","idx":1,"file":"p1.jpg",
                   "title":"C","thumb":"t/600/p1.jpg.webp"}],
                   "videoAlbums":[{"id":3,"slug":"clip","title":"Clip","model_slug":"m","model_name":"Aki",
                   "cover":"m/clip/c0.mp4","coverThumb":"t/s900/m/clip/c0.mp4.webp","tags":[],"count":2}],
                   "videos":[{"key":"clip:v0","slug":"clip","idx":0,"file":"m/clip/c0.mp4",
                   "title":"Clip","thumb":"t/s900/m/clip/c0.mp4.webp","w":1920,"h":1080,"duration":42.5}]}""".replace("\n", "")
            )
        )
    }

    @Test
    fun `refresh resolves three sections`() = runTest(dispatcher.scheduler) {
        enqueueResolve()
        vm.refresh()
        waitUntil { !vm.state.value.loading }
        val s = vm.state.value
        assertEquals(1, s.models.size)
        assertEquals("Aki", s.models[0].name)
        assertEquals("http://localhost:8000/t/600/p1.jpg.webp", s.photos[0].thumbUrl)
        assertEquals("http://localhost:8000/t/600/c/cover.webp", s.collections[0].imageUrl)
        assertEquals(1, server.requestCount)
        assertNull(s.error)
    }

    @Test
    fun `network failure sets error and retry recovers`() = runTest(dispatcher.scheduler) {
        enqueueResolve()
        vm.refresh()
        waitUntil { !vm.state.value.loading }
        // 有数据时下拉刷新失败不打断现状:只收指示器、清 error、保留列表
        server.shutdown()
        vm.refresh()
        waitUntil { !vm.state.value.refreshing }
        assertNull(vm.state.value.error)
        assertEquals(1, vm.state.value.models.size)
        // 空态首刷失败才显示错误 + 重试恢复
        val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
        val api = Retrofit.Builder()
            .baseUrl("http://localhost:1/")
            .client(OkHttpClient())
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(MobileApi::class.java)
        val vm2 = FavoritesViewModel(FavoritesRepository(api, FakeSessionStore()), api, FakeSessionStore())
        vm2.refresh()
        waitUntil { vm2.state.value.error != null }
        assertEquals("无法连接服务器", vm2.state.value.error)
    }

    @Test
    fun `tab switch keeps resolved data`() = runTest(dispatcher.scheduler) {
        enqueueResolve()
        vm.refresh()
        waitUntil { !vm.state.value.loading }
        vm.selectTab(FavTab.PHOTOS)
        assertEquals(FavTab.PHOTOS, vm.state.value.tab)
        assertEquals(1, vm.state.value.photos.size)
        assertEquals("1 张", vm.state.value.countText())
        assertEquals("还没有收藏写真", emptyTextFor(FavTab.COLLECTIONS))
    }

    @Test
    fun `video buckets resolve album card and clip poster`() = runTest(dispatcher.scheduler) {
        enqueueResolve()
        vm.refresh()
        waitUntil { !vm.state.value.loading }
        // 视频专辑段:封面帧卡(与写真卡同型,imageUrl 拼 base + coverThumb)
        assertEquals(1, vm.state.value.videoAlbums.size)
        assertEquals("clip", vm.state.value.videoAlbums[0].slug)
        assertEquals(
            "http://localhost:8000/t/s900/m/clip/c0.mp4.webp",
            vm.state.value.videoAlbums[0].imageUrl,
        )
        // 单条视频段:poster = 封面帧 thumb;aspect 由服务端 w/h 得出(16:9)
        assertEquals(1, vm.state.value.videos.size)
        val v = vm.state.value.videos[0]
        assertEquals("clip", v.slug)
        assertEquals(0, v.idx)
        assertEquals("http://localhost:8000/t/s900/m/clip/c0.mp4.webp", v.posterUrl)
        assertEquals(16f / 9f, v.aspect, 0.01f)
        // 两个新 tab 的计数与空态文案
        vm.selectTab(FavTab.VIDEO_ALBUMS)
        assertEquals("1 部", vm.state.value.countText())
        assertEquals("还没有收藏视频专辑", emptyTextFor(FavTab.VIDEO_ALBUMS))
        vm.selectTab(FavTab.VIDEOS)
        assertEquals("1 段", vm.state.value.countText())
        assertEquals("还没有收藏视频", emptyTextFor(FavTab.VIDEOS))
    }
}

