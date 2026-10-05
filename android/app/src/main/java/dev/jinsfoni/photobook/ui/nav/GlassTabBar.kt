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
import androidx.compose.ui.unit.dp
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
 * 液态玻璃底栏(iOS 26 风格,参数对齐 ui.css):
 * 1. 玻璃背板:整条 hazeBlur(页面),blur 3dp + saturate 165% + brightness 1.08 薄玻璃
 *    ——不能用重模糊:bar 紧邻的亮色内容会被晕成横贯全宽的亮带;
 * 2. 选中药丸:blur 2dp + saturate 180% + brightness 1.14 凸透镜片(--pill 垫色),
 *    位置追逐 [position](MainShell 传 pager 小数进度)→ 拖页时「液体跟随」,弹簧产生
 *    Gooey 拉伸(移动越快越扁宽,到位回弹);API 31/32 退回纯色药丸。
 *    注意:AGSL RuntimeShader 透镜不可挂在这里——实测(API 36)其合成层会被
 *    拉成整条 bar 宽度,在药丸中线拖出横贯亮带,与折射/高光参数无关;
 * 3. 顶部/底部 1px 高光暗边 + 内晕 = InsetHighlight;外阴影 = tabBarShadow。
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
    // API 33+ 用玻璃药丸层;31/32 由 TabItem 画纯色药丸
    // (AGSL 透镜已弃用:RuntimeShaderEffect 合成层 bug,见类注释)
    val hasGlassPill = rememberLensShader() != null

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
            // 背板 = 纯净重模糊玻璃,不套 AGSL:整条宽 bar 的边缘透镜会退化成
            // 上下两条横贯全宽的带状伪影(镜面弧 + 内容拖拽);液态透镜放在药丸上
            .hazeBlur(
                HazeInput.Sources(hazeState),
                HazeBlurStyle {
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

        // 选中药丸(液体玻璃片):blur 2dp 凸透镜观感;31/32 由 TabItem 画纯色药丸
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
                        .hazeBlur(
                            HazeInput.Sources(hazeState),
                            HazeBlurStyle {
                                // ui.css .tab.active: blur(2px) saturate(180%) brightness(1.14)
                                // 药丸比背板更清透更亮 = 前后景深差(凸透镜片);
                                // 中性玻璃(不用 accent 粉),与 iOS 26 原生一致
                                blurRadius(2.dp)
                                colorEffects(
                                    listOf(
                                        HazeColorEffect.colorFilter(glassColorFilter(1.8f, 1.14f)),
                                        HazeColorEffect.tint(colors.barBg),
                                    )
                                )
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
