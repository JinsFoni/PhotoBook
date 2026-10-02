package dev.jinsfoni.photobook

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import javax.inject.Inject
import androidx.compose.runtime.Composable
import dagger.hilt.android.AndroidEntryPoint
import dev.jinsfoni.photobook.core.design.PhotoTheme
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.jinsfoni.photobook.ui.nav.AppRoot
import dev.jinsfoni.photobook.ui.screens.lightbox.PhotoDownloader

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var downloader: PhotoDownloader
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            Bootstrap(downloader)
        }
    }
}

@Composable
private fun Bootstrap(downloader: PhotoDownloader) {
    // M1 临时主题状态(内存态,S9 换 DataStore 持久化)
    PhotoTheme(mode = ThemeState.mode) {
        AppRoot(downloader = downloader)
    }
}
