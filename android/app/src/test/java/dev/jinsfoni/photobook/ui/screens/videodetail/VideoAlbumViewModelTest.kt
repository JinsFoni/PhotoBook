package dev.jinsfoni.photobook.ui.screens.videodetail

import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
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
 * 视频专辑详情 VM:DTO → UI 模型映射(播放源 /video/、封面帧 /t/s900/、
 * 时长透传),以及 video_album 型收藏的乐观切换。校验的是灯箱/详情屏
 * 真正消费的那几个 URL 字段。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class VideoAlbumViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: VideoAlbumViewModel
    private lateinit var favs: FavoritesRepository
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
        val store = FakeSessionStore()
        favs = FavoritesRepository(api, store)
        vm = VideoAlbumViewModel(CollectionsRepository(api, store, tempCacheDir()), favs, api)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun enqueueAlbum() {
        server.enqueue(
            MockResponse().setBody(
                """{"id":7,"slug":"clip","title":"Clip Set","date":"2025.10",
                   "featured":false,"model_slug":"m","model_name":"M1",
                   "cover":"m/clip/c0.mp4","coverThumb":"t/s900/m/clip/c0.mp4.webp",
                   "videos":[{"idx":0,"file":"m/clip/c0.mp4","w":1920,"h":1080,
                              "duration":42.5,"poster":"m/clip/c0.mp4"}],
                   "tags":["studio"],"count":1,"model":{"slug":"m","name":"M1"}}""".replace("\n", "")
            )
        )
    }

    private fun enqueueFavorites(vararg videoAlbums: String) {
        val albums = videoAlbums.joinToString(",") { "\"$it\"" }
        server.enqueue(
            MockResponse().setBody(
                """{"model":[],"collection":[],"photo":[],"video_album":[$albums],"video":[]}"""
            )
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
    fun `load maps video urls and poster`() = runTest(dispatcher.scheduler) {
        enqueueAlbum()
        vm.load("clip")
        waitUntil { vm.state.value.detail != null }
        val d = vm.state.value.detail!!
        assertEquals("Clip Set", d.title)
        assertEquals(1, d.videos.size)
        val v = d.videos[0]
        // 播放源走 /video/(服务端 FileResponse 原生 Range)
        assertEquals("http://localhost:8000/video/m/clip/c0.mp4", v.videoUrl)
        // 封面帧走缩略图缓存树(与照片 thumb 同构):rel + .webp
        assertEquals("http://localhost:8000/t/s900/m/clip/c0.mp4.webp", v.posterUrl)
        // hero 用 coverThumb 已带 t/s900 前缀 → 直拼
        assertEquals("http://localhost:8000/t/s900/m/clip/c0.mp4.webp", d.heroUrl)
        assertEquals(42.5, v.durationSec!!.toDouble(), 0.01)
        assertEquals(1920, v.width)
        assertEquals(1080, v.height)
    }

    @Test
    fun `favorite toggle uses video_album type`() = runTest(dispatcher.scheduler) {
        enqueueAlbum()
        enqueueFavorites("clip")            // 详情 + favorites GET
        vm.load("clip")
        waitUntil { vm.state.value.faved }
        assertTrue(vm.state.value.faved)

        // 乐观取消 + 服务端确认 added=false
        val before = server.requestCount
        server.enqueue(MockResponse().setBody("""{"ok":true,"type":"video_album","key":"clip","added":false}"""))
        vm.toggleFavorite()
        waitUntil { !vm.state.value.faved }
        assertFalse(vm.state.value.faved)
        // 等 POST 真正到达(乐观翻态比网络快,不能只等本地态)
        waitUntil { server.requestCount > before }
        val bodies = server.requestCount.let { n -> (1..n).map { server.takeRequest() } }
            .filter { it.method == "POST" }
            .map { it.body.readUtf8() }
        assertTrue("bodies=$bodies", bodies.any { it.contains("video_album") && it.contains("clip") })
    }

    @Test
    fun `blank slug is rejected before network`() = runTest(dispatcher.scheduler) {
        vm.load("")
        waitUntil { vm.state.value.error != null }
        assertEquals("链接无效,请从列表重新进入", vm.state.value.error)
        assertEquals(0, server.requestCount)
    }
}
