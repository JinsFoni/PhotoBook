package dev.jinsfoni.photobook

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class PhotoBookApp : Application() {
    companion object {
        /** Coil ImageLoader 在 Hilt 图中构建需要的 Application 引用。 */
        lateinit var instance: PhotoBookApp
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
    }
}
