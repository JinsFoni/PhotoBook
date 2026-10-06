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
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.ThemeMode

/**
 * 虚化主题垫底层(ui.css .blur-canvas):真实代表图 blur(42px)+saturate(1.12)+scale(1.35),
 * 上面压深色纱(rgba(8,9,10,.78)→.66)保证前景对比。非虚化主题不渲染任何东西;
 * 图片 URL 由各屏自备(当前数据的代表图),无图时退回纯 paper 基色。
 * clipToBounds 必须挂:图放大 1.35 把模糊光晕推出屏外,但溢出部分在 Pager 横滑 /
 * NavHost 滑动转场时会铺到相邻页上(单页静止时被屏幕裁掉看不见)。
 */
@Composable
fun BlurBackdrop(imageUrl: String?, modifier: Modifier = Modifier) {
    if (LocalThemeMode.current != ThemeMode.BLUR) return
    Box(modifier.fillMaxSize().clipToBounds()) {
        if (imageUrl != null) {
            // 换图淡入,对齐 web 的 0.55s opacity 过渡
            var alpha by remember(imageUrl) { mutableFloatStateOf(0f) }
            LaunchedEffect(imageUrl) {
                animate(0f, 1f, animationSpec = tween(550)) { v, _ -> alpha = v }
            }
            Box(Modifier.fillMaxSize().graphicsLayer { this.alpha = alpha }) {
                AsyncImage(
                    model = imageUrl,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    colorFilter = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(1.12f) }),
                    // blur 在内、scale 在外 = CSS「先 filter 后 transform」;放大同时把模糊边缘光晕推出屏外
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer {
                            scaleX = 1.35f
                            scaleY = 1.35f
                        }
                        .blur(42.dp),
                )
                // 深色纱(.blur-canvas::after)
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
        }
    }
}
