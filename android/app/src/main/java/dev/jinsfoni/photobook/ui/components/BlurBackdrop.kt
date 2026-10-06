package dev.jinsfoni.photobook.ui.components

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import kotlinx.coroutines.launch

/**
 * 虚化垫底单层:真实代表图 saturate(1.12)+scale+blur(42px),由调用方叠纱。
 * scale 常态 1.35:把 blur 的边缘光晕推出屏外(clipToBounds 裁掉溢出)。
 */
@Composable
private fun BlurredLayer(
    model: Any?,
    alpha: Float,
    scale: Float,
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
        modifier = Modifier
            .fillMaxSize()
            .graphicsLayer {
                this.alpha = alpha
                scaleX = scale
                scaleY = scale
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
 * 虚化主题垫底层(ui.css .blur-canvas / web 灯箱 paintBackdrop 同配方):
 * 非虚化主题不渲染任何东西;图片 URL 由各屏自备,无图时不渲染。
 * clipToBounds 必须挂:图放大把模糊光晕推出屏外,但溢出部分在 Pager 横滑 /
 * NavHost 滑动转场时会铺到相邻页上(单页静止时被屏幕裁掉看不见)。
 *
 * 切图 = 双缓冲交叉淡入 + Ken Burns(对齐 web .lightbox__backdrop):
 * - 换图时旧图垫底不动,新图加载成功(SUCCESS)后才开始 620ms 淡入,
 *   同时 scale 1.5→1.35 缓落 1400ms;旧层镜像回涨 1.35→1.5(压在新层
 *   之下,交叉期可见,淡出不可见故无需 opacity 动画)。
 * - 换图瞬间旧氛围始终铺在屏上,预取命中时新图近乎瞬时就绪;
 *   未就绪前维持旧画面,不露黑。
 * - 翻回已展示过的图直接揭示(同图幂等,不重播动效)。
 */
@Composable
fun BlurBackdrop(imageUrl: String?, modifier: Modifier = Modifier) {
    if (LocalThemeMode.current != ThemeMode.BLUR) return
    Box(modifier.fillMaxSize().clipToBounds()) {
        if (imageUrl != null) {
            BackdropLayers(imageUrl)
        }
    }
}

@Composable
private fun BackdropLayers(imageUrl: String) {
    // 已完整展示过的图(连翻时 previous 保持为最后一张成功展示的图)
    var shown by remember { mutableStateOf<String?>(null) }
    // 旧图:新层完全不透明前持续垫底,之后移除
    var previous by remember { mutableStateOf<String?>(null) }
    // 本轮目标图是否已就绪(SUCCESS):就绪前新层整体隐藏
    var loaded by remember(imageUrl) { mutableStateOf(false) }
    // 最近一次完成揭示动效的 URL:翻回去时直接揭示,不重播
    var revealed by remember { mutableStateOf<String?>(null) }

    val alpha = remember(imageUrl) { Animatable(0f) }
    val scale = remember(imageUrl) { Animatable(1.5f) }
    val prevScale = remember(imageUrl) { Animatable(1.35f) }

    LaunchedEffect(imageUrl, loaded) {
        if (!loaded) return@LaunchedEffect
        if (imageUrl == revealed) {
            alpha.snapTo(1f)
            scale.snapTo(1.35f)
            previous = null
            return@LaunchedEffect
        }
        // 离场层回涨与新层缓落互为镜像(web 撤层回涨 1.2 的移植)
        launch { prevScale.animateTo(1.5f, tween(1400, easing = LinearOutSlowInEasing)) }
        launch { scale.animateTo(1.35f, tween(1400, easing = LinearOutSlowInEasing)) }
        alpha.animateTo(1f, tween(620, easing = LinearOutSlowInEasing))
        revealed = imageUrl
        previous = null
    }

    previous?.let { prev ->
        BlurredLayer(model = prev, alpha = 1f, scale = prevScale.value)
    }
    BlurredLayer(
        model = imageUrl,
        alpha = if (loaded) alpha.value else 0f,
        scale = scale.value,
        onState = { st ->
            if (st is AsyncImagePainter.State.Success) {
                // 新图就位:当前展示图转为旧图垫底(web 双缓冲的 front/back 交替)
                if (shown != null && shown != imageUrl) previous = shown
                shown = imageUrl
                loaded = true
            }
        },
    )
    Scrim()
}
