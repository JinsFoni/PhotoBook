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
        // 胶囊几何:半径 = 高/2,端帽圆心在左右两端;
        // 取距最近端帽的距离归一化 → 中段 r<1 平坦区(不折射),
        // 只有两个圆头边缘才有透镜效果(整条宽 bar 不能用 min(cx,cy) 圆形公式)
        float rad = uResolution.y * 0.5;
        float2 c1 = float2(rad, rad);
        float2 c2 = float2(uResolution.x - rad, rad);
        float2 d1 = fragCoord - c1;
        float2 d2 = fragCoord - c2;
        float2 d = length(d1) < length(d2) ? d1 : d2;
        float r = length(d) / rad;
        float2 n = length(d) > 0.0001 ? d / length(d) : float2(0.0);
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
