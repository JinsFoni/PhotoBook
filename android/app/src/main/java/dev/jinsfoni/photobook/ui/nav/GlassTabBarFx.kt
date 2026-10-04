package dev.jinsfoni.photobook.ui.nav

import androidx.compose.foundation.Canvas
import androidx.compose.ui.draw.drawBehind
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.unit.dp
import dev.jinsfoni.photobook.core.design.LocalPhotoColors

/**
 * 玻璃条内高光:inset 0 1px 1px glass-hi(顶部 1px 亮线)+ inset 0 -1px 1px glass-lo
 * (底部 1px 暗线)+ inset 0 0 14px glass-glow(内侧泛光)。
 */
@Composable
fun InsetHighlight(modifier: Modifier = Modifier) {
    val colors = LocalPhotoColors.current
    Canvas(modifier.fillMaxSize()) {
        val w = size.width
        val h = size.height
        // 顶部高光线(两侧留出圆角)
        drawLine(
            brush = Brush.horizontalGradient(
                listOf(Color.Transparent, colors.glassHi, colors.glassHi, Color.Transparent)
            ),
            start = Offset(w * 0.08f, 0.5f),
            end = Offset(w * 0.92f, 0.5f),
            strokeWidth = 1.dp.toPx(),
        )
        // 底部暗线
        drawLine(
            brush = Brush.horizontalGradient(
                listOf(Color.Transparent, colors.glassLo, colors.glassLo, Color.Transparent)
            ),
            start = Offset(w * 0.08f, h - 0.5f),
            end = Offset(w * 0.92f, h - 0.5f),
            strokeWidth = 1.dp.toPx(),
        )
        // CSS 的 inset 0 0 14px 泛光不再画:Canvas 硬描边替代不了 14px 软泛光,
        // 画出来是一圈横在玻璃内的灰色环(已去掉)
    }
}

/**
 * 设计稿双层外阴影(ui.css .tabbar box-shadow):
 *   0 14dp 36dp rgba(0,0,0,.26) + 0 2dp 8dp rgba(0,0,0,.12)。
 * 背板有 paper 垫底不透光,阴影只出现在胶囊轮廓外,不会再透过玻璃糊成灰带。
 */
@Composable
fun Modifier.tabBarShadow(): Modifier {
    val colors = LocalPhotoColors.current
    val isDark = colors.ink.luminance() > 0.5f
    val a1 = if (isDark) 0.26f else 0.14f
    val a2 = if (isDark) 0.12f else 0.06f
    return this
        .drawShadowLayer(Color.Black.copy(alpha = a1), blurDp = 36f, dyDp = 14f)
        .drawShadowLayer(Color.Black.copy(alpha = a2), blurDp = 8f, dyDp = 2f)
}

private fun Modifier.drawShadowLayer(
    color: Color,
    blurDp: Float,
    dyDp: Float,
): Modifier = this.drawBehind {
    drawIntoCanvas { canvas ->
        val paint = Paint()
        val frameworkPaint = paint.asFrameworkPaint()
        frameworkPaint.isAntiAlias = true
        frameworkPaint.color = color.toArgb()
        // CSS box-shadow blur = 2×高斯 sigma
        frameworkPaint.maskFilter =
            android.graphics.BlurMaskFilter(blurDp.dp.toPx() / 2f, android.graphics.BlurMaskFilter.Blur.NORMAL)
        val shape = android.graphics.RectF(0f, 0f, size.width, size.height)
        canvas.save()
        canvas.translate(0f, dyDp.dp.toPx())
        canvas.nativeCanvas.drawRoundRect(shape, size.width / 2f, size.height / 2f, frameworkPaint)
        canvas.restore()
    }
}

/** Text 阴影辅助(仅用于需要浮在图上的标题,备用)。 */
internal fun textShadow(color: Color, blurRadius: Float, offset: Offset) =
    Shadow(color, offset, blurRadius)
