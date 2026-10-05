package dev.jinsfoni.photobook.ui.nav

/**
 * 液态玻璃透镜(AGSL,API 33+)——重做版,参考 BiliPai / Kyant0(AndroidLiquidGlass,
 * Apache 2.0)的圆角矩形 SDF 折射方案:
 *   1. sdRoundedRect 求片元到玻璃边缘的有符号距离;
 *   2. 只有靠边 refractionHeight 一圈生效,depth = circleMap(1 + sd/height)
 *      (圆弧缓动,越靠边缘折射越强,中心平直 = 真实凸透镜截面);
 *   3. 采样点沿 SDF 梯度(边缘法线)向外偏移 depth × refractionAmount
 *      ——边缘内容被「拉近压缩」,产生玻璃厚度折射感;
 *   4. 色散:RGB 三通道各采样一次,偏移量随 depth 缩放,边缘出一圈细彩虹纹。
 *
 * 与旧版胶囊 shader 的区别:旧版对整层内容做全幅透镜(易出横贯亮带),
 * 本版只在边缘环带内偏移采样,中心 1:1 原样输出,不会畸变中部内容。
 */
internal const val LIQUID_LENS_SKSL: String = """
    uniform shader uContent;
    uniform float2 uSize;
    uniform float uRadius;
    uniform float uRefractionHeight;
    uniform float uRefractionAmount;
    uniform float uDispersion;

    // 到圆角矩形边缘的有符号距离(内部为负)
    float sdRoundedRect(float2 coord, float2 halfSize, float radius) {
        float2 q = abs(coord) - (halfSize - float2(radius));
        return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
    }

    // SDF 梯度 = 边缘法线;轴线与圆心重合时避免零向量 NaN
    float2 gradSd(float2 coord, float2 halfSize, float radius) {
        float2 q = abs(coord) - (halfSize - float2(radius));
        if (q.x >= 0.0 || q.y >= 0.0) {
            return normalize(coord / max(length(coord), 0.0001)) *
                   sign(coord.x + coord.y + 0.0001);
        }
        float2 g = float2(step(q.y, q.x), 1.0 - step(q.y, q.x));
        return sign(coord) * g;
    }

    // 圆弧缓动:线性输入 → 圆的下降沿,边缘处折射最陡
    float circleMap(float x) {
        x = clamp(x, 0.0, 1.0);
        return 1.0 - sqrt(max(1.0 - x * x, 0.0));
    }

    half4 main(float2 fragCoord) {
        float2 halfSize = uSize * 0.5;
        float2 c = fragCoord - halfSize;
        float radius = min(uRadius, min(halfSize.x, halfSize.y));
        float sd = sdRoundedRect(c, halfSize, radius);

        // 边缘环带之外(深入玻璃 > height)原样输出:中心内容零畸变
        if (-sd >= uRefractionHeight) return uContent.eval(fragCoord);
        float sdIn = min(sd, 0.0);

        float depth = circleMap(1.0 - -sdIn / uRefractionHeight) * uRefractionAmount;
        float gradRadius = min(radius * 1.5, min(halfSize.x, halfSize.y));
        float2 grad = gradSd(c, halfSize, gradRadius);
        // 向内采样(负号,Kyant0/BiliPai 同款):边缘外侧的内容被「压进」
        // 边环 = 凸透镜折射;向外采样会越出玻璃层采到层外像素(蓝色描边 bug)
        float2 refracted = clamp(fragCoord - depth * grad, float2(0.0), uSize - float2(1.0));

        if (uDispersion <= 0.0) return uContent.eval(refracted);

        // RGB 波长色散:偏移集中在边缘环带外侧(depth 已随边缘增大),
        // 内侧两通道收敛回主采样,不出浑浊彩边
        float2 disp = depth * grad * uDispersion;
        float2 rC = clamp(refracted + disp, float2(0.0), uSize - float2(1.0));
        float2 bC = clamp(refracted - disp, float2(0.0), uSize - float2(1.0));
        half4 r = uContent.eval(rC);
        half4 g = uContent.eval(refracted);
        half4 b = uContent.eval(bC);
        return half4(r.r, g.g, b.b, g.a);
    }
"""
