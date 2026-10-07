package dev.jinsfoni.photobook.ui.screens.lightbox

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 保存原图到相册(Pictures/PhotoBook/)。
 *
 * M1 曾用 DownloadManager,但系统下载进程(Android 14+)拒绝 cleartext http 源,
 * 自托管局域网部署会被静默丢弃;改为进程内 HttpURLConnection 拉流 → MediaStore 落盘。
 * (App 进程已开 usesCleartextTraffic,同域图片已在相册里浏览过,拉流无障碍)
 */
@Singleton
class PhotoDownloader @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun download(url: String, fileName: String) {
        android.util.Log.w("PhotoDl", "start $url -> $fileName")
        scope.launch {
            runCatching {
                android.util.Log.w("PhotoDl", "fetching...")
                // 1) 拉字节(进程内,cleartext 已放行)。
                // HttpURLConnection 只跟随同协议重定向;服务端 /media 在原图
                // 已上传外部存储时会 302 跳 https 图床(跨协议),须手动跟随。
                val bytes = fetchFollowingRedirects(url)
                // 2) MediaStore 插入 Pictures/PhotoBook/(无需写权限,API 29+)
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, fileName)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH,
                        "${Environment.DIRECTORY_PICTURES}/PhotoBook")
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                }
                val resolver = context.contentResolver
                val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                    ?: error("MediaStore insert failed")
                android.util.Log.w("PhotoDl", "fetched ${bytes.size}B, uri=$uri")
                val os = resolver.openOutputStream(uri)
                if (os != null) {
                    os.write(bytes)
                    os.flush()
                    os.close()
                    android.util.Log.w("PhotoDl", "saved OK")
                }
                values.clear()
                values.put(MediaStore.Images.Media.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            }.onFailure { android.util.Log.w("PhotoDl", "FAIL", it) }
        }
    }

    /** 手动跟随重定向(含 http↔https 跨协议),上限 5 跳。 */
    private fun fetchFollowingRedirects(url: String, redirects: Int = 0): ByteArray {
        check(redirects <= 5) { "too many redirects" }
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 30_000
        conn.instanceFollowRedirects = false
        try {
            when (conn.responseCode) {
                HttpURLConnection.HTTP_MOVED_PERM,
                HttpURLConnection.HTTP_MOVED_TEMP,
                307, 308 -> {
                    val loc = conn.getHeaderField("Location")
                        ?: error("redirect without Location")
                    conn.disconnect()
                    val next = java.net.URI(url).resolve(loc).toString()
                    android.util.Log.w("PhotoDl", "redirect -> $next")
                    return fetchFollowingRedirects(next, redirects + 1)
                }
            }
            if (conn.responseCode !in 200..299) {
                error("HTTP ${conn.responseCode}")
            }
            return conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }
}
