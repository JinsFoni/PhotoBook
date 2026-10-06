package dev.jinsfoni.photobook.ui.components

import androidx.compose.animation.core.animate
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import coil3.compose.AsyncImagePainter
import coil3.request.ImageRequest
import coil3.request.crossfade
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.ThemeMode

/** 虚化垫底单层:真实代表图 saturate(1.12)+scale(1.35)+blur(42px),由调用方叠纱。 */
@Composable
private fun BlurredLayer(
    model: Any?,
    alpha: Float = 1f,
    onState: ((AsyncImagePainter.State) -> Unit)? = null,
) {
    AsyncImage(
        model = ImageRequest.Builder(LocalContext.current)
            .data(model)
            .crossfade(false) // 淡入节奏自管,不用 Coil 默认 crossfade
            .build(),
        contentDescription = null,
        contentScale = ContentScale.Crop,
        colorFilter = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(1.12f) }),
        onState = onState,
        // blur 在内、scale 在外 = CSS「先 filter 后 transform」;放大同时把模糊边缘光晕推出屏外
        modifier = Modifier
            .fillMaxSize()
            .graphicsLayer {
                this.alpha = alpha
                scaleX = 1.35f
                scaleY = 1.35f
            }
            .blur(42.dp),
    )
}

/** 深色纱(.blur-canvas::after),统一压暗保证前景对比。 */
@Composable
private fun Scrim() {
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    0f to Color(8, 9, 10, 199),
                    1f to Color(8, 9, 10, 168),
                )
            ),
    )
}

/**
 * 虚化主题垫底层(ui.css .blur-canvas):真实代表图 blur(42px)+saturate(1.12)+scale(1.35),
 * 上面压深色纱(rgba(8,9,10,.78)→.66)保证前景对比。非虚化主题不渲染任何东西;
 * 图片 URL 由各屏自备(当前数据的代表图),无图时退回纯 paper 基色。
 * clipToBounds 必须挂:图放大 1.35 把模糊光晕推出屏外,但溢出部分在 Pager 横滑 /
 * NavHost 滑动转场时会铺到相邻页上(单页静止时被屏幕裁掉看不见)。
 *
 * 切图策略(不露黑):换图时旧图留在底层,新图加载成功(SUCCESS)后才开始
 * 淡入盖上去——预取命中时新图近乎瞬时就绪,无「黑 → 虚化」中间态;首次进入
 * 无旧图时等 SUCCESS 再淡入,底色为 paper 而非黑。
 */
@Composable
fun BlurBackdrop(imageUrl: String?, modifier: Modifier = Modifier) {
    if (LocalThemeMode.current != ThemeMode.BLUR) return
    Box(modifier.fillMaxSize().clipToBounds()) {
        if (imageUrl != null) {
            // 旧图:切图期间垫底,新图 SUCCESS 后清掉
            var previous by remember { mutableStateOf<String?>(null) }
            // 记住"上一张已展示的图":进入新 URL 时把当前图转为旧图垫底
            var shown by remember { mutableStateOf<String?>(null) }
            if (shown != null && shown != imageUrl) previous = shown
            shown = imageUrl

            var alpha by remember(imageUrl) { mutableFloatStateOf(0f) }
            var loaded by remember(imageUrl) { mutableStateOf(false) }

            // 成功就绪才开始淡入:未就绪时维持旧画面,避免半透明黑闪
            LaunchedEffect(imageUrl, loaded) {
                if (!loaded) return@LaunchedEffect
                animate(0f, 1f, animationSpec = tween(280)) { v, _ -> alpha = v }
            }

            // 底:旧图(新图就位后 previous=null 自然退场)
            if (previous != null && previous != imageUrl) {
                BlurredLayer(model = previous)
            }
            // 新图:SUCCESS 前整体隐藏(alpha=0 由 loaded 门控),避免截屏残影
            BlurredLayer(
                model = imageUrl,
                alpha = if (loaded) alpha else 0f,
                onState = { st ->
                    if (st is AsyncImagePainter.State.Success) {
                        loaded = true
                        previous = null
                    }
                },
            )
            Scrim()
        }
    }
}
