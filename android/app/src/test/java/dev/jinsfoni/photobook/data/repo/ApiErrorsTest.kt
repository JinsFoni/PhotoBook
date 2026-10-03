package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStore
import dev.jinsfoni.photobook.data.remote.ApiErrors
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.safeCall
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException

/** 错误体解析 + safeCall 收敛(计划 Task 8 单测第 4 项)。 */
class ApiErrorsTest {

    private lateinit var server: MockWebServer

    @Before fun setUp() { server = MockWebServer(); server.start() }

    @After fun tearDown() { server.shutdown() }

    @Test
    fun `parses error envelope`() {
        val e = ApiErrors.parseErrorBody(
            """{"error":{"code":"invalid_credentials","message":"bad"}}""", 401)
        assertEquals("invalid_credentials", e!!.code)
        assertEquals("bad", e.message)
        assertEquals(401, e.httpStatus)
        assertTrue(e.isAuth)
    }

    @Test
    fun `null on non-envelope body`() {
        assertNull(ApiErrors.parseErrorBody("""{"detail":"oops"}""", 500))
        assertNull(ApiErrors.parseErrorBody("", 500))
        assertNull(ApiErrors.parseErrorBody(null, 500))
    }

    @Test
    fun `safeCall wraps HttpException with parsed code`() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(404)
                .setBody("""{"error":{"code":"not_found","message":"no"}}""")
        )
        val url = server.url("/")
        val client = okhttp3.OkHttpClient()
        try {
            safeCall {
                val resp = client.newCall(okhttp3.Request.Builder().url(url).build()).execute()
                if (!resp.isSuccessful) {
                    // Response.error(body, rawResponse) 构造 404 错误响应 → HttpException
                    val body = okhttp3.ResponseBody.create(null, resp.body?.string() ?: "")
                    @Suppress("UNCHECKED_CAST")
                    throw retrofit2.HttpException(
                        retrofit2.Response.error<Any>(body, resp)
                    )
                }
                ""
            }
            org.junit.Assert.fail("should throw")
        } catch (e: ApiException) {
            assertEquals("not_found", e.code)
            assertEquals(404, e.httpStatus)
        }
    }

    @Test
    fun `safeCall maps IOException to network`() = runTest {
        try {
            safeCall<String> { throw java.io.IOException("down") }
            org.junit.Assert.fail("should throw")
        } catch (e: ApiException) {
            assertEquals(ApiException.NETWORK, e.code)
        }
    }
}
