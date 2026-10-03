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
        // 内侧泛光:大圆角描边模拟 inset 0 0 14px
        drawRoundRect(
            brush = Brush.verticalGradient(listOf(colors.glassGlow, Color.Transparent)),
            topLeft = Offset(6f, 6f),
            size = androidx.compose.ui.geometry.Size(w - 12f, h * 0.5f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(999f, 999f),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = 10.dp.toPx()),
        )
    }
}

/**
 * 单层外阴影,对齐 BiliPai dropShadow:radius = Small+Micro(≈14px),
 * α 浅色 0.10 / 深色 0.20,dy ≈ 6px。
 * (不再用 CSS 双层重影:0.26α+36px blur 会在胶囊上下糊出两条灰带)
 */
@Composable
fun Modifier.tabBarShadow(): Modifier {
    val colors = LocalPhotoColors.current
    val isDark = colors.ink.luminance() > 0.5f
    val alpha = if (isDark) 0.20f else 0.10f
    return this.drawShadowLayer(
        Color.Black.copy(alpha = alpha),
        blurPx = 14f * 2f, // CSS blur 14px ≈ 双层高斯 sigma 总量
        dyPx = 6f,
    )
}

private fun Modifier.drawShadowLayer(
    color: Color,
    blurPx: Float,
    dyPx: Float,
): Modifier = this.drawBehind {
    drawIntoCanvas { canvas ->
        val paint = Paint()
        val frameworkPaint = paint.asFrameworkPaint()
        frameworkPaint.isAntiAlias = true
        frameworkPaint.color = color.toArgb()
        // CSS box-shadow blur = 2×高斯 sigma
        frameworkPaint.maskFilter =
            android.graphics.BlurMaskFilter(blurPx / 2f, android.graphics.BlurMaskFilter.Blur.NORMAL)
        val shape = android.graphics.RectF(0f, 0f, size.width, size.height)
        canvas.save()
        canvas.translate(0f, dyPx)
        canvas.nativeCanvas.drawRoundRect(shape, size.width / 2f, size.height / 2f, frameworkPaint)
        canvas.restore()
    }
}

/** Text 阴影辅助(仅用于需要浮在图上的标题,备用)。 */
internal fun textShadow(color: Color, blurRadius: Float, offset: Offset) =
    Shadow(color, offset, blurRadius)
