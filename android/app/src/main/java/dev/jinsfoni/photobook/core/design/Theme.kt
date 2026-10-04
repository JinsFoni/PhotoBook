package dev.jinsfoni.photobook.core.design

import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier

/** 主题模式 —— light/dark/blur 三态(与 Web 端 data-theme 一致)。 */
enum class ThemeMode { LIGHT, DARK, BLUR }

val LocalPhotoColors = staticCompositionLocalOf<PhotoColors> {
    lightColors()
}

val LocalThemeMode = staticCompositionLocalOf { ThemeMode.LIGHT }

/** 主题宿主:内存态驱动重组;启动从 DataStore 灌入,变更写回(见 AppRoot/MainShell)。 */
object ThemeState {
    var mode by mutableStateOf(ThemeMode.LIGHT)
}

fun PhotoColors.forMode(mode: ThemeMode): PhotoColors = when (mode) {
    ThemeMode.LIGHT -> lightColors()
    ThemeMode.DARK -> darkColors()
    ThemeMode.BLUR -> blurColors()
}

/**
 * 应用主题根:提供 PhotoColors / ThemeMode,并以 paper 铺底。
 * blur 主题的「垫底代表图」由各屏内容层实现(设计文档:真实图片 blur+saturate)。
 */
@Composable
fun PhotoTheme(
    modifier: Modifier = Modifier,
    mode: ThemeMode = ThemeState.mode,
    content: @Composable () -> Unit,
) {
    val colors = lightColors().forMode(mode)
    CompositionLocalProvider(
        LocalPhotoColors provides colors,
        LocalThemeMode provides mode,
    ) {
        Surface(color = colors.paper, modifier = modifier) {
            content()
        }
    }
}
