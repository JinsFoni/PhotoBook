package dev.jinsfoni.photobook.data.remote

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * 缩略图 URL 约定回归:服务端 /t/ 路径最后一段就是源文件真实后缀,
 * 客户端附加 .webp 会让服务端把 x.jpg.webp 当源文件名 → 全部 404
 * (曾导致安卓详情页照片墙与发现页轮播空白)。
 */
class MediaUrlsTest {

    private val base = "http://192.168.0.100:8000"

    @Test
    fun `short side thumb keeps source suffix and never appends webp`() {
        assertEquals(
            "http://192.168.0.100:8000/t/s900/models/aki/p0.jpg",
            MediaUrls.thumbShortSide(base, "models/aki/p0.jpg", 900),
        )
        assertEquals(
            "http://192.168.0.100:8000/t/s2400/models/aki/cover.jpg",
            MediaUrls.thumbShortSide(base, "models/aki/cover.jpg", 2400),
        )
    }

    @Test
    fun `webp source keeps single extension`() {
        assertEquals(
            "http://192.168.0.100:8000/t/s900/a/p0.webp",
            MediaUrls.thumbShortSide(base, "a/p0.webp", 900),
        )
    }

    @Test
    fun `width and crop thumbs keep source suffix`() {
        assertEquals("http://192.168.0.100:8000/t/600/a/p0.png",
            MediaUrls.thumb(base, "a/p0.png", 600))
        assertEquals("http://192.168.0.100:8000/t/600x800/a/p0.png",
            MediaUrls.thumb(base, "a/p0.png", 600, 800))
    }

    @Test
    fun `leading slash in rel does not produce double slash`() {
        assertEquals("http://192.168.0.100:8000/media/a/p0.jpg",
            MediaUrls.original(base, "/a/p0.jpg"))
        assertEquals("http://192.168.0.100:8000/t/s900/a/p0.jpg",
            MediaUrls.thumbShortSide(base, "/a/p0.jpg", 900))
        assertEquals("http://192.168.0.100:8000/t/s900/a/cover.jpg",
            MediaUrls.fromPrefixed(base, "/t/s900/a/cover.jpg"))
    }

    @Test
    fun `media urls live on origin root even when base url has api path`() {
        assertEquals("http://host:8000/t/s900/a/p0.jpg",
            MediaUrls.thumbShortSide("http://host:8000/api", "a/p0.jpg", 900))
        assertEquals("http://host:8000/media/a/p0.jpg",
            MediaUrls.original("http://host:8000/api/", "a/p0.jpg"))
    }
}
