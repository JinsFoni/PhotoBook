package dev.jinsfoni.photobook.data.remote

import org.junit.Assert.assertEquals
import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Before
import org.junit.Test

/** HostSelectionInterceptor:请求落点重写到活动档案地址。 */
class HostSelectionInterceptorTest {

    private lateinit var server: MockWebServer
    private lateinit var store: FakeSessionStore

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        store = FakeSessionStore()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun client() = OkHttpClient.Builder()
        .addInterceptor(HostSelectionInterceptor(store))
        .build()

    @Test
    fun `请求被重写到活动档案 host`() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        store.addProfile(server.url("/").toString(), "tok", "alice")

        // 请求发到占位地址,应被重写落进 MockWebServer
        client().newCall(
            Request.Builder().url("http://placeholder.invalid:1/api/mobile/discover").build()
        ).execute().use { resp -> assertEquals(200, resp.code) }

        val recorded = server.takeRequest()
        assertEquals("/api/mobile/discover", recorded.path)
    }

    @Test
    fun `路径与查询串保持不变`() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        store.addProfile(server.url("/").toString(), "tok", "alice")

        client().newCall(
            Request.Builder()
                .url("http://placeholder.invalid:1/api/mobile/collections?limit=20&offset=40")
                .build()
        ).execute()

        val recorded = server.takeRequest()
        assertEquals("/api/mobile/collections?limit=20&offset=40", recorded.path)
    }
}
