package dev.jinsfoni.photobook.ui.nav

import android.graphics.RuntimeShader
import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.graphics.RenderEffect

/**
 * 液态玻璃透镜(iOS 26 liquid glass 风格)——AGSL 只能采样本层内容,
 * 所以把它包在「药丸玻璃层」外:uContent = 药丸内已模糊的页面背板,
 * 边缘带向内折射(中心放大)+ 顶左镜面高光。
 *
 * 药丸 = hazeBlur(页面) + 本 shader 包裹:
 *   1. r = 归一化半径,edge = smoothstep(0.45,1,r) 只在边缘生效;
 *   2. 采样点向圆心偏移 -n·edge·uStrength → 边缘内容被压缩 = 折射透镜感;
 *   3. 高光:n 与「左上光源」的朝向分量 × edge → 顶左弧一段玻璃反光。
 */
@RequiresApi(33)
internal const val LENS_SKSL: String = """
    uniform shader uContent;
    uniform float2 uResolution;
    uniform float uStrength;
    uniform float4 uSpecular;

    half4 main(float2 fragCoord) {
        // 胶囊 SDF(按「到管壁距离」归一化):
        //   中段(|x-cx|<halfLen):r = |dy|/rad —— 只有上下边缘折射;
        //   圆头区:             r = |q|/rad —— 圆头边缘折射。
        // 错误写法(距端帽圆心距离)会让中段 r≈5 → edge=1 全程折射+采样错位,
        // 在与端帽区交界处撕裂出横向暗带
        float rad = uResolution.y * 0.5;
        float halfLen = uResolution.x * 0.5 - rad;
        float2 q = float2(abs(fragCoord.x - uResolution.x * 0.5) - halfLen,
                          fragCoord.y - rad);
        float ql = length(q);
        float r = q.x > 0.0 ? ql / rad : abs(q.y) / rad;
        float2 n = q.x > 0.0 ? (ql > 0.0001 ? q / ql : float2(0.0))
                             : float2(0.0, q.y > 0.0 ? 1.0 : -1.0);
        float edge = smoothstep(0.45, 1.0, r);
        float2 off = -n * edge * uStrength;
        float2 suv = clamp(fragCoord + off, float2(0.0), uResolution - float2(1.0));
        half4 col = uContent.eval(suv);
        // 镜面只看垂直分量(顶光):若含 -n.x 项,左端帽(n.x=-1)会被点亮
        // 而右端(n.x=+1)被 max(0,·) 截断 → 左右不对称
        float spec = edge * max(0.0, -n.y);
        col.rgb += uSpecular.rgb * uSpecular.a * spec;
        return col;
    }
"""

/** API 33+ 才有 RuntimeShader;31/32 返回 null 走纯色药丸回退。 */
@Composable
internal fun rememberLensShader(): RuntimeShader? {
    if (Build.VERSION.SDK_INT < 33) return null
    return remember { RuntimeShader(LENS_SKSL) }
}

/** 默认透镜参数:边缘折射 2dp,镜面高光 = 白 45%。 */
internal const val LENS_STRENGTH_DP = 2f
internal const val LENS_SPECULAR_ALPHA = 0.45f

/** shader → Compose RenderEffect(uContent 绑定本层内容)。 */
@RequiresApi(33)
internal fun RuntimeShader.asLensEffect(): RenderEffect {
    val effect = android.graphics.RenderEffect.createRuntimeShaderEffect(this, "uContent")
    return effect.asComposeRenderEffect()
}
