package dev.jinsfoni.photobook.ui.components

import androidx.compose.animation.core.EaseIn
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle

/**
 * 站名词标:衬线专字体(思源宋 KR 拉丁子集 600,独立于风格包,对齐 Web
 * static/fonts/wordmark.css)+ FoamGirl 同款扫光。
 *
 * 扫光对齐 Web .wordmark(wordmark-shine):一道 105° 斜向光带掠过字形后
 * 停顿循环 —— 1.5s 周期内前 1s ease-in 扫完、后 0.5s 停住。Web 用
 * background-clip:text + background-position-x 把 300% 宽渐变滑过字形;
 * 这里等价换算:光带中心从词左半宽外扫到右半宽外(行程 2×词宽),
 * 光带占词宽 60%,光带色取中性灰 #9A9AA0(深底白字压暗高光、
 * 浅底深字提亮)。渐变两端钳制为底色,字形其余部分不受影响。
 */
@Composable
fun Wordmark(
    text: String,
    style: TextStyle,
    color: Color,
    modifier: Modifier = Modifier,
) {
    var widthPx by remember { mutableFloatStateOf(0f) }
    val progress by rememberInfiniteTransition(label = "wordmark-shine").animateFloat(
        initialValue = 1f,
        targetValue = -1f,
        animationSpec = infiniteRepeatable(
            animation = keyframes {
                durationMillis = 1500
                1f at 0
                -1f at 1000 using EaseIn
                -1f at 1500
            },
        ),
        label = "wordmark-shine-x",
    )
    val textStyle = if (widthPx > 0f) style.copy(brush = shineBrush(progress, widthPx, color)) else style
    Text(
        text,
        style = textStyle,
        color = color,
        maxLines = 1,
        onTextLayout = { widthPx = it.size.width.toFloat() },
        modifier = modifier,
    )
}

/** 105° 斜向光带渐变:光带中心 (0.5f - progress) × 词宽,占词宽 60%。 */
private fun shineBrush(progress: Float, widthPx: Float, base: Color): Brush {
    val w = widthPx.coerceAtLeast(1f)
    // CSS 105deg:指向右、略向下(y 轴向下),单位向量 (sin105°, -cos105°)
    val dir = Offset(0.9659f, 0.2588f)
    // 渐变跨 3×词宽 → 中段 20% 恰为 0.6 词宽的光带(同 Web 渐变 40/50/60%)
    val half = 1.5f * w
    val center = Offset((0.5f - progress) * w, 0f)
    return Brush.linearGradient(
        0.0f to base,
        0.4f to base,
        0.5f to Color(0xFF9A9AA0),
        0.6f to base,
        1.0f to base,
        start = center - dir * half,
        end = center + dir * half,
    )
}
