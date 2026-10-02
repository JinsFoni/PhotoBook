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

/** M1 临时主题宿主:可变状态驱动重组(临时切换按钮用,S9 换成 DataStore 驱动)。 */
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
    content: @Composable () -> Unit,
) {
    val mode = ThemeState.mode
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
