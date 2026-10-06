package dev.jinsfoni.photobook.ui.screens.detail

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/** S3 VM:详情加载/heroUrl 拼装/收藏乐观+回滚。 */
@OptIn(ExperimentalCoroutinesApi::class)
class DetailViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var vm: DetailViewModel
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
        vm = DetailViewModel(CollectionsRepository(api, store), favs, api)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun enqueueDetail() {
        server.enqueue(
            MockResponse().setBody(
                """{"id":1,"slug":"a","title":"TA","date":"2025.09","model_slug":"m",
                   "model_name":"M1","cover":"a/cover.jpg",
                   "coverThumb":"t/900x/a/cover.webp",
                   "photos":[{"idx":0,"file":"a/p0.jpg","w":900,"h":1350}],
                   "tags":["x"],"count":1,"model":{"slug":"m","name":"M1"}}""".replace("\n", "")
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
    fun `load maps detail with prefixed thumb url`() = runTest(dispatcher.scheduler) {
        enqueueDetail()
        vm.load("a")
        waitUntil { vm.state.value.detail != null }
        val d = vm.state.value.detail!!
        assertEquals("TA", d.title)
        // coverThumb 已带 t/900x 前缀 → 直拼,不得再包 /t/900/
        assertEquals("http://localhost:8000/t/900x/a/cover.webp", d.heroUrl)
        assertEquals(1, d.photos.size)
        assertEquals("http://localhost:8000/t/900/a/p0.jpg.webp", d.photos[0].thumbUrl)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `favorite loads async and toggle is optimistic`() = runTest(dispatcher.scheduler) {
        enqueueDetail()
        // 详情 + favorites GET
        server.enqueue(MockResponse().setBody("""{"model":[],"collection":["a"],"photo":[]}"""))
        vm.load("a")
        waitUntil { vm.state.value.faved }
        assertTrue(vm.state.value.faved)

        // 乐观取消:先翻 false
        server.enqueue(MockResponse().setBody("""{"ok":true,"type":"collection","key":"a","added":false}"""))
        vm.toggleFavorite()
        waitUntil { !vm.state.value.faved }
        assertFalse(vm.state.value.faved)
    }

    @Test
    fun `favorite toggle rolls back on failure`() = runTest(dispatcher.scheduler) {
        enqueueDetail()
        server.enqueue(MockResponse().setBody("""{"model":[],"collection":[],"photo":[]}"""))
        vm.load("a")
        waitUntil { vm.state.value.detail != null && server.requestCount >= 2 }
        assertFalse(vm.state.value.faved)

        // toggle 失败(500)→ 回滚保持 false
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"error":{"code":"server","message":"x"}}"""))
        vm.toggleFavorite()
        waitUntil { server.requestCount >= 3 }
        waitUntil { !vm.state.value.faved }
        assertFalse("rollback must restore false", vm.state.value.faved)
    }

    @Test
    fun `photo full url points to original`() = runTest(dispatcher.scheduler) {
        enqueueDetail()
        vm.load("a")
        waitUntil { vm.state.value.detail != null }
        val p = vm.state.value.detail!!.photos[0]
        assertEquals("http://localhost:8000/media/a/p0.jpg", p.fullUrl)
        assertNotNull(p.thumbUrl)
    }
}

