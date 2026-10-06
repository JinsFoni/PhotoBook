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
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
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
import androidx.compose.ui.zIndex
import coil3.compose.AsyncImage
import coil3.compose.AsyncImagePainter
import coil3.request.ImageRequest
import coil3.request.crossfade
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.ThemeMode
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private const val FADE_MS = 620
private const val KB_MS = 1400

/** Ken Burns 起手幅度:web 1.2→1.0(相对 20%);Android 常态 1.35(把 blur 边缘光晕推出屏),等比放大 1.62。 */
private const val KB_FROM = 1.62f
private const val KB_TO = 1.35f

/**
 * 常驻双缓冲槽位(web 灯箱 data-lb-bd="a"/"b" 的移植):a/b 交替前后台。
 * 可见层的 model 永不变更——换图只发生在隐藏槽的 AsyncImage 上,Coil 换请求
 * 清画布的时刻不可见,黑帧/闪烁不可能出现。
 * ready:本槽当前 url 已解码(SUCCESS);zIndex:交叉期间新层 2 / 旧层 1,平时 0。
 */
private class Slot {
    var url by mutableStateOf<String?>(null)
    var ready by mutableStateOf(false)
    var zIndex by mutableFloatStateOf(0f)
    val alpha = Animatable(0f)
    val scale = Animatable(KB_TO)
}

/**
 * 虚化垫底单层:真实代表图 saturate(1.12)+scale+blur(42px),由调用方叠纱。
 * alpha 为 0 时摘掉 blur(隐藏槽常驻组合,RenderEffect 的逐帧采样不能白付)。
 */
@Composable
private fun BlurredLayer(
    model: Any?,
    alpha: Float,
    scale: Float,
    zIndex: Float,
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
            .zIndex(zIndex)
            .graphicsLayer {
                this.alpha = alpha
                scaleX = scale
                scaleY = scale
            }
            .then(if (alpha > 0f) Modifier.blur(42.dp) else Modifier),
    )
}

/** 深色纱(.blur-canvas::after),统一压暗保证前景对比;zIndex 必须压过交叉中的两层(zIndex 1/2)。 */
@Composable
private fun Scrim() {
    Box(
        Modifier
            .fillMaxSize()
            .zIndex(3f)
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
 * 切图 = 常驻双缓冲 + 回弹动效(对齐 web .lightbox__backdrop):
 * - 两个常驻槽位 a/b,可见层的 model 永不变更,换图只发生在隐藏槽上,
 *   因此旧氛围从换图瞬间到新图揭示完毕始终铺满全屏,不可能闪黑。
 * - 新图就绪(SUCCESS)后揭示:新层置顶 620ms 淡入 + Ken Burns 缓落
 *   1.62→1.35(1400ms),旧层镜像回涨 1.35→1.62(web 撤层回涨的移植)。
 * - 翻回已展示过的图:图层还在(ready 未清),立即重播揭示,不等加载。
 * - 连翻时未揭示就再换:后台槽无声撤下再换内容,前台不受影响。
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
    val slots = remember { listOf(Slot(), Slot()) }
    var front by remember { mutableIntStateOf(0) }

    LaunchedEffect(imageUrl) {
        val current = slots[front]
        if (current.url == imageUrl) {
            // 同图幂等(web: front.dataset.src === src 直接返回)。发生在这条
            // 路径的只能是"换走又翻回来、且上一轮揭示没走完":另一槽可能还
            // 压在交叉半路,无声撤下;前台复位满不透明。
            val other = slots[1 - front]
            other.alpha.snapTo(0f)
            other.zIndex = 0f
            current.alpha.snapTo(1f)
            current.scale.snapTo(KB_TO)
            return@LaunchedEffect
        }
        val target = slots[1 - front]
        if (target.url != imageUrl) {
            // 后台槽可能还带上一轮交叉的残影:先无声撤下再换内容(此刻前台层
            // 铺满全屏,屏幕上没有任何变化)。ready 必须先于 url 归位,否则
            // 旧图遗留的 ready 会让揭示抢在新图解码之前。
            target.alpha.snapTo(0f)
            target.zIndex = 0f
            target.ready = false
            target.url = imageUrl
        }
        // 等新图解码(SUCCESS);命中内存缓存时立即通过,未就绪前旧图持续垫底
        snapshotFlow { target.ready && target.url == imageUrl }.first { it }
        // 揭示(web reveal()):新层置顶淡入 + Ken Burns 缓落,旧层镜像回涨。
        // 旧层全程满不透明垫底,交叉只发生在两层虚化图之间。
        target.zIndex = 2f
        current.zIndex = 1f
        target.scale.snapTo(KB_FROM)
        target.alpha.snapTo(0f)
        launch { current.scale.animateTo(KB_FROM, tween(KB_MS, easing = LinearOutSlowInEasing)) }
        launch { target.scale.animateTo(KB_TO, tween(KB_MS, easing = LinearOutSlowInEasing)) }
        target.alpha.animateTo(1f, tween(FADE_MS, easing = LinearOutSlowInEasing))
        // 淡入完成:角色交换,旧层压底归零(在新层之下,不可见)
        front = 1 - front
        current.alpha.snapTo(0f)
        current.zIndex = 0f
    }

    Box(modifier = Modifier.fillMaxSize()) {
        slots.forEach { slot ->
            BlurredLayer(
                model = slot.url,
                alpha = slot.alpha.value,
                scale = slot.scale.value,
                zIndex = slot.zIndex,
                onState = { st ->
                    if (st is AsyncImagePainter.State.Success) slot.ready = true
                },
            )
        }
        Scrim()
    }
}
