package dev.jinsfoni.photobook

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.ui.tooling.preview.Preview
import dagger.hilt.android.AndroidEntryPoint
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.rememberHazeState
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.PhotoTheme
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.jinsfoni.photobook.ui.screens.MainShell
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            Bootstrap()
        }
    }
}

@Composable
private fun Bootstrap() {
    // M1 临时主题状态(内存态,S9 换 DataStore 持久化)
    PhotoTheme(mode = ThemeState.mode) {
        val hazeState = rememberHazeState()
        MainShell(
            hazeState = hazeState,
            onThemeCycle = {
                ThemeState.mode = when (ThemeState.mode) {
                    ThemeMode.LIGHT -> ThemeMode.DARK
                    ThemeMode.DARK -> ThemeMode.BLUR
                    ThemeMode.BLUR -> ThemeMode.LIGHT
                }
            },
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun BootstrapPreview() {
    Bootstrap()
}
