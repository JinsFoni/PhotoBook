package dev.jinsfoni.photobook.ui.nav

import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.util.fastCoerceAtMost
import kotlinx.coroutines.CompletableDeferred
import top.yukonga.miuix.kmp.blur.BackdropEffectScope
import top.yukonga.miuix.kmp.blur.LayerBackdrop
import top.yukonga.miuix.kmp.blur.isRuntimeShaderSupported
import top.yukonga.miuix.kmp.blur.layerBackdrop
import top.yukonga.miuix.kmp.blur.rememberLayerBackdrop
import top.yukonga.miuix.kmp.blur.runtimeShaderEffect
import androidx.compose.foundation.shape.CornerBasedShape
import androidx.compose.ui.unit.LayoutDirection

/**
 * 液态玻璃底栏的页面采集源 —— BiliPai rememberChromeBackdropSource 同款:
 * 挂到页面内容容器上,页面绘制先录进 [contentLayer] 再上屏;
 * [backdrop] 回放该层供底栏 drawBackdrop 采样。双重录制保证底栏
 * 永远采不到底栏自身(底栏不在内容容器内)。
 */
@Stable
class GlassBarBackdropSource internal constructor(
    val backdrop: LayerBackdrop,
    val modifier: Modifier,
    private val recorded: State<Boolean>,
) {
    val isReady: Boolean get() = recorded.value
}

@Composable
internal fun rememberGlassBarBackdropSource(): GlassBarBackdropSource {
    val contentLayer = rememberGraphicsLayer()
    val recorded = remember(contentLayer) { mutableStateOf(false) }
    val firstRecording = remember(contentLayer) { CompletableDeferred<Unit>() }
    LaunchedEffect(firstRecording) {
        firstRecording.await()
        recorded.value = true
    }
    val backdrop = rememberLayerBackdrop(onDraw = {
        drawLayer(contentLayer)
        firstRecording.complete(Unit)
    })
    return remember(backdrop, contentLayer) {
        GlassBarBackdropSource(
            backdrop = backdrop,
            recorded = recorded,
            modifier = Modifier
                .layerBackdrop(backdrop)
                .drawWithContent {
                    contentLayer.record { this@drawWithContent.drawContent() }
                    drawLayer(contentLayer)
                },
        )
    }
}

/**
 * 圆角矩形折射透镜 —— BiliPai Lens.kt(Kyant0/AndroidLiquidGlass 方案)移植:
 * SDF 边缘环带内沿法线偏移采样(圆弧缓动,中心 1:1 零畸变),可选 RGB 色散。
 * 在 drawBackdrop effects 链中调用(必须链在 blur 之后),由库负责
 * padding/降采样/坐标换算 —— 这是与手搓 RenderEffect 版的本质区别。
 */
fun BackdropEffectScope.lens(
    refractionHeight: Float,
    refractionAmount: Float,
    chromaticAberration: Float = 0f,
) {
    if (!isRuntimeShaderSupported()) return
    if (refractionHeight <= 0f || refractionAmount <= 0f) return

    if (padding < refractionAmount) padding = refractionAmount

    val radii = roundedRectCornerRadii() ?: return

    val dispersionEnabled = chromaticAberration > 0f
    val shaderString =
        if (dispersionEnabled) ROUNDED_RECT_REFRACTION_WITH_DISPERSION_SHADER
        else ROUNDED_RECT_REFRACTION_SHADER
    val key = if (dispersionEnabled) "PhotoBookLensDispersion" else "PhotoBookLens"

    val sf = downscaleFactor.coerceAtLeast(1).toFloat()
    val scaledSizeW = size.width / sf
    val scaledSizeH = size.height / sf
    val scaledPadding = padding / sf
    val scaledRefractionHeight = refractionHeight / sf
    val scaledRefractionAmount = refractionAmount / sf
    val scaledRadii = FloatArray(radii.size) { radii[it] / sf }

    runtimeShaderEffect(
        key = key,
        shaderString = shaderString,
        uniformShaderName = "content",
    ) {
        setFloatUniform("size", scaledSizeW, scaledSizeH)
        setFloatUniform("offset", -scaledPadding, -scaledPadding)
        setFloatUniform("cornerRadii", scaledRadii)
        setFloatUniform("refractionHeight", scaledRefractionHeight)
        setFloatUniform("refractionAmount", -scaledRefractionAmount)
        if (dispersionEnabled) {
            setFloatUniform("chromaticAberration", chromaticAberration)
        }
    }
}

private fun BackdropEffectScope.roundedRectCornerRadii(): FloatArray? {
    val cornerShape = shape as? CornerBasedShape ?: return null
    val sizePx = size
    val maxRadius = sizePx.minDimension / 2f
    val isLtr = layoutDirection == LayoutDirection.Ltr
    val topLeft = if (isLtr) cornerShape.topStart.toPx(sizePx, this) else cornerShape.topEnd.toPx(sizePx, this)
    val topRight = if (isLtr) cornerShape.topEnd.toPx(sizePx, this) else cornerShape.topStart.toPx(sizePx, this)
    val bottomRight = if (isLtr) cornerShape.bottomEnd.toPx(sizePx, this) else cornerShape.bottomStart.toPx(sizePx, this)
    val bottomLeft = if (isLtr) cornerShape.bottomStart.toPx(sizePx, this) else cornerShape.bottomEnd.toPx(sizePx, this)
    return floatArrayOf(
        topLeft.fastCoerceAtMost(maxRadius),
        topRight.fastCoerceAtMost(maxRadius),
        bottomRight.fastCoerceAtMost(maxRadius),
        bottomLeft.fastCoerceAtMost(maxRadius),
    )
}

private const val ROUNDED_RECT_SDF = """
// 圆角轴线与中心可能产生零向量；避免 NaN 传播到纹理采样。
float2 safeNormalize(float2 vector) {
    return vector / max(length(vector), 0.0001);
}

float radiusAt(float2 coord, float4 radii) {
    if (coord.x >= 0.0) {
        if (coord.y <= 0.0) return radii.y;
        else return radii.z;
    } else {
        if (coord.y <= 0.0) return radii.x;
        else return radii.w;
    }
}

float sdRoundedRect(float2 coord, float2 halfSize, float radius) {
    float2 cornerCoord = abs(coord) - (halfSize - float2(radius));
    float outside = length(max(cornerCoord, 0.0)) - radius;
    float inside = min(max(cornerCoord.x, cornerCoord.y), 0.0);
    return outside + inside;
}

float2 gradSdRoundedRect(float2 coord, float2 halfSize, float radius) {
    float2 cornerCoord = abs(coord) - (halfSize - float2(radius));
    if (cornerCoord.x >= 0.0 || cornerCoord.y >= 0.0) {
        return sign(coord) * safeNormalize(max(cornerCoord, 0.0));
    } else {
        float gradX = step(cornerCoord.y, cornerCoord.x);
        return sign(coord) * float2(gradX, 1.0 - gradX);
    }
}
"""

private const val ROUNDED_RECT_REFRACTION_SHADER = """
uniform shader content;

uniform float2 size;
uniform float2 offset;
uniform float4 cornerRadii;
uniform float refractionHeight;
uniform float refractionAmount;

$ROUNDED_RECT_SDF

float circleMap(float x) {
    float clampedX = clamp(x, 0.0, 1.0);
    return 1.0 - sqrt(max(1.0 - clampedX * clampedX, 0.0));
}

half4 main(float2 coord) {
    float2 halfSize = size * 0.5;
    float2 centeredCoord = (coord + offset) - halfSize;
    float radius = radiusAt(centeredCoord, cornerRadii);

    float sd = sdRoundedRect(centeredCoord, halfSize, radius);
    if (-sd >= refractionHeight) {
        return content.eval(coord);
    }
    sd = min(sd, 0.0);

    float d = circleMap(1.0 - -sd / refractionHeight) * refractionAmount;
    float gradRadius = min(radius * 1.5, min(halfSize.x, halfSize.y));
    float2 grad = safeNormalize(gradSdRoundedRect(centeredCoord, halfSize, gradRadius));

    float2 refractedCoord = coord + d * grad;
    return content.eval(refractedCoord);
}
"""

private const val ROUNDED_RECT_REFRACTION_WITH_DISPERSION_SHADER = """
uniform shader content;

uniform float2 size;
uniform float2 offset;
uniform float4 cornerRadii;
uniform float refractionHeight;
uniform float refractionAmount;
uniform float chromaticAberration;

$ROUNDED_RECT_SDF

float circleMap(float x) {
    float clampedX = clamp(x, 0.0, 1.0);
    return 1.0 - sqrt(max(1.0 - clampedX * clampedX, 0.0));
}

half4 main(float2 coord) {
    float2 halfSize = size * 0.5;
    float2 centeredCoord = (coord + offset) - halfSize;
    float radius = radiusAt(centeredCoord, cornerRadii);

    float sd = sdRoundedRect(centeredCoord, halfSize, radius);
    if (-sd >= refractionHeight) {
        return content.eval(coord);
    }
    sd = min(sd, 0.0);

    float d = circleMap(1.0 - -sd / refractionHeight) * refractionAmount;
    float gradRadius = min(radius * 1.5, min(halfSize.x, halfSize.y));
    float2 grad = safeNormalize(gradSdRoundedRect(centeredCoord, halfSize, gradRadius));

    float2 refractedCoord = coord + d * grad;
    float dispersionIntensity = chromaticAberration * ((centeredCoord.x * centeredCoord.y) / (halfSize.x * halfSize.y));
    float2 dispersedCoord = d * grad * dispersionIntensity;

    // 物理光学三通道(RGB)波长色散,透明边缘回退中心样本并统一预乘输出
    half4 rSample = content.eval(refractedCoord + dispersedCoord);
    half4 gSample = content.eval(refractedCoord);
    half4 bSample = content.eval(refractedCoord - dispersedCoord);

    half r = rSample.a > 0.0001 ? rSample.r / rSample.a :
        (gSample.a > 0.0001 ? gSample.r / gSample.a : 0.0);
    half b = bSample.a > 0.0001 ? bSample.b / bSample.a :
        (gSample.a > 0.0001 ? gSample.b / gSample.a : 0.0);
    return half4(r * gSample.a, gSample.g, b * gSample.a, gSample.a);
}
"""
