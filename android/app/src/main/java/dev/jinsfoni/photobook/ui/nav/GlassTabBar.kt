package dev.jinsfoni.photobook.ui.nav

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.luminance
import android.graphics.RuntimeShader
import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.ui.graphics.RenderEffect
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.unit.dp
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.chrisbanes.haze.HazeInput
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.blur.HazeBlurStyle
import dev.chrisbanes.haze.blur.HazeColorEffect
import dev.chrisbanes.haze.blur.hazeBlur
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.IconWidths
import dev.jinsfoni.photobook.ui.icons.StrokeIcon

/** 底部 4 个 tab(顺序即导航顺序),图标取自 StrokeIcons(路径对照 ui.js)。 */
enum class PhotoTab(val iconParts: List<dev.jinsfoni.photobook.ui.icons.IconPart>) {
    EXPLORE(listOf(dev.jinsfoni.photobook.ui.icons.TabExploreIcon)),
    COLLECTIONS(listOf(dev.jinsfoni.photobook.ui.icons.TabCollectionsIcon)),
    MODELS(listOf(dev.jinsfoni.photobook.ui.icons.TabModelsIcon)),
    FAVORITES(listOf(dev.jinsfoni.photobook.ui.icons.TabFavoritesIcon)),
}

/** tab 显示名(资源解析,替代旧 enum 构造参数 label)。 */
@Composable
fun PhotoTab.label(): String = when (this) {
    PhotoTab.EXPLORE -> stringResource(R.string.tab_explore)
    PhotoTab.COLLECTIONS -> stringResource(R.string.collections_noun)
    PhotoTab.MODELS -> stringResource(R.string.models_noun)
    PhotoTab.FAVORITES -> stringResource(R.string.favorites_noun)
}

private val TabHeight = 64.dp
private val TabShape = RoundedCornerShape(999.dp)
private val ShellPad = 6.dp

/** 系统导航栏(手势条/三键)高度:底栏上移与各页列表底部留白都要避让。 */
val LocalGlassBarBottomInset = staticCompositionLocalOf { 0.dp }

/** 玻璃饱和度+亮度:CSS saturate() brightness()(RGB 行整体乘亮度 = 线性提亮)。 */
private fun glassColorFilter(saturation: Float, brightness: Float) =
    ColorFilter.colorMatrix(
        ColorMatrix().apply {
            setToSaturation(saturation)
            for (row in 0..2) for (col in 0..4) this[row, col] *= brightness
        },
    )

/**
 * AGSL 折射透镜(液态玻璃模式):包在 hazeBlur 层之外,对本层已模糊内容
 * 做圆角矩形 SDF 边缘折射。uContent 只能采样本层,所以透镜必须挂在
 * clip → lens → hazeBlur 的顺序里(透镜在外,模糊在内)。
 * [shader] 为 null(低版本 / 关闭)时是空操作。
 */
@RequiresApi(33)
private fun Modifier.lensEffect(
    shader: RuntimeShader?,
    enabled: Boolean,
    cornerRadius: androidx.compose.ui.unit.Dp,
): Modifier = if (shader == null || !enabled) this else this.graphicsLayer {
    val size = size
    shader.setFloatUniform(
        "uSize",
        size.width,
        size.height,
    )
    shader.setFloatUniform("uRadius", cornerRadius.toPx())
    // 边缘折射环带宽 7dp;向内折射深度 7dp;色散 0.15(细微,过强出彩虹描边);
    // 安全边距 15dp = 环带宽 7dp + 背板模糊 6dp 再留余量:折射采样完全跳过
    // 被模糊晕染的最外圈,否则页面内容(白卡/暖色照片)会被压成彩色描边
    shader.setFloatUniform("uRefractionHeight", 7.dp.toPx())
    shader.setFloatUniform("uRefractionAmount", 7.dp.toPx())
    shader.setFloatUniform("uDispersion", 0.15f)
    shader.setFloatUniform("uEdgeInset", 15.dp.toPx())
    renderEffect = android.graphics.RenderEffect
        .createRuntimeShaderEffect(shader, "uContent")
        .asComposeRenderEffect()
}

/**
 * 玻璃底栏,两种材质由 ThemeState.liquidGlass 切换:
 *
 * 薄磨砂(默认,关)= 旧版:
 * 1. 玻璃背板:整条 hazeBlur(页面),blur 3dp + saturate 165% + brightness 1.08 薄玻璃
 *    ——不能用重模糊:bar 紧邻的亮色内容会被晕成横贯全宽的亮带;
 * 2. 选中药丸:blur 2dp + saturate 180% + brightness 1.14 凸透镜片(--pill 垫色),
 *    位置追逐 [position](MainShell 传 pager 小数进度)→ 拖页时「液体跟随」,弹簧产生
 *    Gooey 拉伸(移动越快越扁宽,到位回弹);API 31/32 退回纯色药丸。
 *
 * 液态玻璃(开,参考 iOS 26 / BiliPai):背板换成重模糊磨砂(12dp),
 * 整条 bar 与选中药丸各自包一层 AGSL 折射透镜(LiquidLensShader:圆角矩形 SDF,
 * 只在边缘一圈按 SDF 梯度偏移采样 = 边缘折射环,中心 1:1 零畸变;RGB 波长色散)。
 * 注意 AGSL 只能采样本层内容,透镜必须包在 hazeBlur 层之外(uContent = 已模糊背板)。
 * API < 33 无 RuntimeShader,开关只退化为更重的磨砂。
 *
 * 共通:顶部/底部 1px 高光暗边 = InsetHighlight;外阴影 = tabBarShadow;
 * 选中态 = accent 图标 + 600 字重;按压 scale .94 spring。
 */
@Composable
fun GlassTabBar(
    hazeState: HazeState,
    selected: PhotoTab,
    onSelect: (PhotoTab) -> Unit,
    modifier: Modifier = Modifier,
    position: Float = selected.ordinal.toFloat(),
) {
    val colors = LocalPhotoColors.current
    val liquid = ThemeState.liquidGlass
    // API 33+ 用玻璃药丸层;31/32 由 TabItem 画纯色药丸
    val hasGlassPill = rememberLensShader() != null
    // 液态玻璃透镜:API 33+ 才有 RuntimeShader;开关关闭时不挂
    val lensOn = liquid && hasGlassPill
    val barLens = remember { if (Build.VERSION.SDK_INT >= 33) RuntimeShader(LIQUID_LENS_SKSL) else null }
    val pillLens = remember { if (Build.VERSION.SDK_INT >= 33) RuntimeShader(LIQUID_LENS_SKSL) else null }

    // 药丸追逐 pager 小数进度:spring 追赶 = 液体黏滞感
    val pillX by animateFloatAsState(
        targetValue = position,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = 460f),
        label = "pill-x",
    )
    // Gooey 拉伸:离目标越远越扁宽(飞行中),到位回弹;体积感由 scaleY 反向补偿
    val stretch = 1f + (pillX - position).let { kotlin.math.abs(it) }.coerceAtMost(1.5f) * 0.10f

    Box(
        modifier
            .height(TabHeight)
            .tabBarShadow()
            .clip(TabShape)
            .lensEffect(barLens, enabled = lensOn, cornerRadius = TabHeight / 2)
            .clip(TabShape)
            // 背板:薄磨砂 = 轻模糊;液态玻璃 = 重模糊磨砂,再由外层透镜折边
            .hazeBlur(
                HazeInput.Sources(hazeState),
                HazeBlurStyle {
                    if (liquid) {
                        // 液态玻璃:6dp 中度模糊——保留内容轮廓让边缘折射可读
                        // (12dp 重模糊会把压边糊成一圈纯色,只剩毛玻璃观感)
                        blurRadius(6.dp)
                        noiseFactor(0f)
                        backgroundColor(colors.paper)
                        colorEffects(
                            listOf(
                                HazeColorEffect.colorFilter(glassColorFilter(1.8f, 1.10f)),
                                HazeColorEffect.tint(colors.barBg),
                            )
                        )
                    } else {
                        // ui.css .tabbar: blur(3px) saturate(165%) brightness(1.08)
                        // 薄磨砂:内容保持可辨,只有轻微软化 + 提亮
                        blurRadius(3.dp)
                        noiseFactor(0f)
                        // 不透明 surface 垫底(HazeMaterials 同款):透明区域不再拉低效果层 alpha,
                        // 同时挡住外阴影透过玻璃显形
                        backgroundColor(colors.paper)
                        colorEffects(
                            listOf(
                                HazeColorEffect.colorFilter(glassColorFilter(1.65f, 1.08f)),
                                // tint 用 surface 色代替 CSS background:light 40% 白 / dark 48% 黑
                                HazeColorEffect.tint(colors.barBg),
                            )
                        )
                    }
                    // 边缘保持硬裁切:形状羽化会让玻璃上下边界发虚、拖出灰带
                    blurredEdgeTreatment(BlurredEdgeTreatment.Rectangle)
                },
            ),
    ) {
        // 斜向流光(::after,115deg sheen)——暗色下左端泛白已整体去掉,仅浅色保留
        if (colors.ink.luminance() < 0.5f) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(
                        Brush.linearGradient(
                            0f to colors.sheenA,
                            0.30f to Color.Transparent,
                            0.68f to Color.Transparent,
                            1f to colors.sheenB,
                            start = Offset.Zero,
                            end = Offset(1000f, 466f), // ≈115°
                        )
                    )
            )
        }
        // inset 高光/暗边/内晕
        InsetHighlight()

        // 选中药丸(液体玻璃片);31/32 由 TabItem 画纯色药丸
        if (hasGlassPill) {
            BoxWithConstraints(Modifier.matchParentSize()) {
                // 内容区 = 整条 - ShellPad,槽宽 = 内容区/4;药丸宽 = 槽宽 - 6dp
                val slot = (maxWidth - ShellPad * 2) / PhotoTab.entries.size
                Box(
                    Modifier
                        .align(Alignment.CenterStart)
                        .offset(x = ShellPad + slot * pillX + 3.dp)
                        .padding(vertical = ShellPad)
                        .width(slot - 6.dp)
                        .fillMaxHeight()
                        .graphicsLayer {
                            scaleX = stretch
                            scaleY = 1f - (stretch - 1f) * 0.55f
                        }
                        .clip(TabShape)
                        .lensEffect(pillLens, enabled = lensOn, cornerRadius = (TabHeight - ShellPad * 2) / 2)
                        .clip(TabShape)
                        .hazeBlur(
                            HazeInput.Sources(hazeState),
                            HazeBlurStyle {
                                if (liquid) {
                                    // 药丸比背板更清透更亮 = 前后景深差(凸透镜片)
                                    blurRadius(6.dp)
                                    colorEffects(
                                        listOf(
                                            HazeColorEffect.colorFilter(glassColorFilter(1.9f, 1.18f)),
                                            HazeColorEffect.tint(colors.barBg),
                                        )
                                    )
                                } else {
                                    // ui.css .tab.active: blur(2px) saturate(180%) brightness(1.14)
                                    blurRadius(2.dp)
                                    colorEffects(
                                        listOf(
                                            HazeColorEffect.colorFilter(glassColorFilter(1.8f, 1.14f)),
                                            HazeColorEffect.tint(colors.barBg),
                                        )
                                    )
                                }
                                noiseFactor(0f)
                                backgroundColor(colors.paper)
                                blurredEdgeTreatment(BlurredEdgeTreatment.Rectangle)
                            },
                        )
                        // ui.css .tab.active background: var(--pill)(选中片垫色,very subtle)
                        .background(colors.pill, TabShape),
                )
            }
        }

        Row(
            Modifier
                .fillMaxSize()
                .padding(ShellPad),
        ) {
            PhotoTab.entries.forEachIndexed { i, tab ->
                TabItem(
                    tab = tab,
                    selected = tab == selected,
                    // 33+ 药丸由玻璃片画;31/32 退回纯色药丸
                    showPill = !hasGlassPill,
                    onClick = { onSelect(tab) },
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxHeight(),
                )
            }
        }
    }
}

@Composable
private fun TabItem(
    tab: PhotoTab,
    selected: Boolean,
    showPill: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    // .tab:active scale(.94) → spring 弹性回弹
    val scale by animateFloatAsState(
        targetValue = if (pressed) 0.94f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = 380f),
        label = "tab-scale",
    )
    val iconTint by animateColorAsState(
        if (selected) colors.accent else colors.ink2,
        animationSpec = spring(stiffness = 380f),
        label = "tab-tint",
    )

    Box(
        modifier
            .clip(TabShape)
            .then(if (showPill && selected) Modifier.background(colors.pill, TabShape) else Modifier)
            .photoClickable(interaction, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(3.dp),
            modifier = Modifier.scale(scale),
        ) {
            StrokeIcon(
                parts = tab.iconParts,
                size = 22.dp,
                tint = iconTint,
                strokeWidth = IconWidths.THIN,
            )
            Text(
                tab.label(),
                style = if (selected) PhotoType.tabLabelActive else PhotoType.tabLabel,
                color = if (selected) colors.ink else colors.ink2,
            )
        }
    }
}
