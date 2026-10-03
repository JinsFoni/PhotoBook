package dev.jinsfoni.photobook.ui.icons

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Fill
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * 自绘描边图标 —— 路径逐条抄自原型 docs/android-design/ui/ui.js ICONS
 * (24 viewBox,1.6/1.7 描边,round 帽/角)。Material 图标风格不符,按原样移植。
 */

/** 一个 24×24 空间里的绘制片段。 */
fun interface IconPart {
    fun PathScope.build()
}

/** SVG 风格 Path 构建(自维护当前点,支持相对指令;smooth cubic 自动反射控制点)。 */
class PathScope(val path: Path) {
    private var cx = 0f
    private var cy = 0f
    private var lastC2x = 0f
    private var lastC2y = 0f

    fun moveTo(x: Float, y: Float) {
        path.moveTo(x, y); cx = x; cy = y
    }

    fun lineTo(x: Float, y: Float) {
        path.lineTo(x, y); cx = x; cy = y
    }

    fun lineToRelative(dx: Float, dy: Float) = lineTo(cx + dx, cy + dy)

    fun horizontalLineTo(x: Float) = lineTo(x, cy)

    fun horizontalLineToRelative(dx: Float) = lineTo(cx + dx, cy)

    fun verticalLineTo(y: Float) = lineTo(cx, y)

    fun verticalLineToRelative(dy: Float) = lineTo(cx, cy + dy)

    fun curveTo(c1x: Float, c1y: Float, c2x: Float, c2y: Float, x: Float, y: Float) {
        path.cubicTo(c1x, c1y, c2x, c2y, x, y)
        lastC2x = c2x; lastC2y = c2y; cx = x; cy = y
    }

    fun curveToRelative(c1x: Float, c1y: Float, c2x: Float, c2y: Float, x: Float, y: Float) =
        curveTo(cx + c1x, cy + c1y, cx + c2x, cy + c2y, cx + x, cy + y)

    /** S/s —— 反射上一控制点为第一控制点。 */
    fun smoothCurveTo(c2x: Float, c2y: Float, x: Float, y: Float) {
        val r1x = 2 * cx - lastC2x
        val r1y = 2 * cy - lastC2y
        curveTo(r1x, r1y, c2x, c2y, x, y)
    }

    fun smoothCurveToRelative(c2x: Float, c2y: Float, x: Float, y: Float) =
        smoothCurveTo(cx + c2x, cy + c2y, cx + x, cy + y)

    fun quadTo(c1x: Float, c1y: Float, x: Float, y: Float) {
        path.quadraticBezierTo(c1x, c1y, x, y); cx = x; cy = y
    }

    fun close() = path.close()

    /** 圆心 (cx,cy) 半径 r —— SVG circle(cx,cy,r) 语义(Offset 是左上角,故减 r)。 */
    fun circle(cx: Float, cy: Float, r: Float) =
        path.addOval(Rect(Offset(cx - r, cy - r), Size(r * 2, r * 2)))

    fun roundedRect(x: Float, y: Float, w: Float, h: Float, r: Float) =
        path.addRoundRect(RoundRect(x, y, x + w, y + h, CornerRadius(r, r)))
}

object IconWidths {
    const val THIN = 1.6f
    const val BOLD = 1.7f
}

@Composable
fun StrokeIcon(
    parts: List<IconPart>,
    size: Dp,
    tint: Color,
    modifier: Modifier = Modifier,
    strokeWidth: Float = IconWidths.THIN,
    filled: Boolean = false,
) {
    Box(modifier.size(size)) {
        Canvas(Modifier.size(size)) {
            val scale = this.size.minDimension / 24f
            withTransform({ scale(scale, scale, pivot = Offset.Zero) }) {
                val style = if (filled) Fill
                else Stroke(strokeWidth, cap = StrokeCap.Round, join = StrokeJoin.Round)
                for (part in parts) {
                    val scope = PathScope(Path())
                    part.run { scope.build() }
                    drawPath(scope.path, tint, style = style)
                }
            }
        }
    }
}

@Composable
fun StrokeIcon(
    part: IconPart,
    size: Dp,
    tint: Color,
    modifier: Modifier = Modifier,
    strokeWidth: Float = IconWidths.THIN,
    filled: Boolean = false,
) = StrokeIcon(listOf(part), size, tint, modifier, strokeWidth, filled)

private fun part(build: PathScope.() -> Unit): IconPart = IconPart { build() }

// ---- 图标定义(路径对照 ui.js ICONS)------------------------------------------

val BackIcon = part {
    moveTo(15f, 5f); lineToRelative(-7f, 7f); lineToRelative(7f, 7f)
}

val CloseIcon = part {
    moveTo(6f, 6f); lineToRelative(12f, 12f)
    moveTo(18f, 6f); lineTo(6f, 18f)
}

val SearchIcon = part {
    circle(11f, 11f, 7f)
    moveTo(20f, 20f); lineToRelative(-3.8f, -3.8f)
}

val SortIcon = part {
    moveTo(4f, 7f); horizontalLineToRelative(16f)
    moveTo(7f, 12f); horizontalLineToRelative(10f)
    moveTo(10f, 17f); horizontalLineToRelative(4f)
}

val HeartIcon = part {
    moveTo(12f, 21f)
    // s-7.5-4.7-10-9.3(无前曲,反射控制点=当前点 → 退化为普通相对曲线)
    curveToRelative(-3.75f, -2.35f, -7.5f, -4.7f, -10f, -9.3f)
    curveTo(0.5f, 8f, 2.5f, 4.5f, 6f, 4.5f)
    curveToRelative(2.2f, 0f, 3.7f, 1.2f, 4.6f, 2.6f)
    lineTo(12f, 9f)
    lineToRelative(1.4f, -1.9f)
    curveToRelative(0.9f, -1.4f, 2.4f, -2.6f, 4.6f, -2.6f)
    curveToRelative(3.5f, 0f, 5.5f, 3.5f, 4f, 7.2f)
    curveTo(19.5f, 16.3f, 12f, 21f, 12f, 21f)
    close()
}

val DownloadIcon = part {
    moveTo(12f, 4f); verticalLineToRelative(11f)
    moveTo(12f, 15f); lineToRelative(4f, -4f)
    moveTo(12f, 15f); lineToRelative(-4f, -4f)
    moveTo(5f, 20f); horizontalLineTo(19f)
}

val CopyIcon = part {
    roundedRect(8f, 8f, 12f, 12f, 1.5f)
    moveTo(16f, 8f); verticalLineTo(5.5f)
    quadTo(16f, 4f, 14.5f, 4f)
    horizontalLineTo(5.5f)
    quadTo(4f, 4f, 4f, 5.5f)
    verticalLineTo(14.5f)
    quadTo(4f, 16f, 5.5f, 16f)
    horizontalLineTo(8f)
}

val SettingsIcon = part {
    circle(12f, 12f, 3.2f)
    moveTo(5f, 12f); horizontalLineTo(3f)
    moveTo(21f, 12f); horizontalLineTo(19f)
    moveTo(12f, 5f); verticalLineTo(3f)
    moveTo(12f, 21f); verticalLineTo(19f)
}

val TabExploreIcon = part {
    moveTo(3f, 11.5f); lineTo(12f, 4f); lineToRelative(9f, 7.5f)
    moveTo(5.5f, 10f); verticalLineToRelative(9f); horizontalLineToRelative(13f); verticalLineTo(10f)
}

val TabCollectionsIcon = part {
    roundedRect(3.5f, 4f, 7f, 10.5f, 1f)
    roundedRect(13.5f, 4f, 7f, 10.5f, 1f)
    moveTo(6f, 18.5f); horizontalLineTo(18f)
}

val TabModelsIcon = part {
    circle(12f, 8f, 3.6f)
    moveTo(5f, 20f)
    curveToRelative(1f, -3.8f, 3.8f, -5.6f, 7f, -5.6f)
    smoothCurveToRelative(6f, 1.8f, 7f, 5.6f)
}

val TabFavoritesIcon = HeartIcon
