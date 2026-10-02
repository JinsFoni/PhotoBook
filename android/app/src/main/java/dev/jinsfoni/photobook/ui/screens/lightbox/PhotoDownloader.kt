package dev.jinsfoni.photobook.ui.screens.lightbox

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** DownloadManager 封装:系统下载通知栏,M1 不做进度 UI。 */
@Singleton
class PhotoDownloader @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun download(url: String, fileName: String) {
        val req = DownloadManager.Request(Uri.parse(url))
            .setTitle(fileName)
            .setDescription("PhotoBook")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_PICTURES, "PhotoBook/$fileName")
            .setAllowedOverMetered(true)
        context.getSystemService(DownloadManager::class.java).enqueue(req)
    }
}
