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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.HazeInput
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.blur.HazeBlurStyle
import dev.chrisbanes.haze.blur.HazeColorEffect
import dev.chrisbanes.haze.blur.hazeBlur
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.IconWidths
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import top.yukonga.miuix.kmp.blur.Backdrop
import top.yukonga.miuix.kmp.blur.blur
import top.yukonga.miuix.kmp.blur.colorControls
import top.yukonga.miuix.kmp.blur.drawBackdrop
import top.yukonga.miuix.kmp.blur.isRuntimeShaderSupported

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

private val TabHeight = 58.dp
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
 * 玻璃底栏,两种材质由 ThemeState.liquidGlass 切换(BiliPai/miuix 同款架构):
 *
 * 薄磨砂(默认,关)= 旧版 hazeBlur 链,参数不变:
 * 1. 背板:blur 3dp + saturate 165% + brightness 1.08 薄玻璃;
 * 2. 药丸:blur 2dp + saturate 180% + brightness 1.14 凸透镜片。
 *
 * 液态玻璃(开,BiliPai tuned 预设):整条 bar 与选中药丸各自独立 drawBackdrop
 * (miuix-blur 的 Backdrop 体系:页面内容先被 ChromeBackdropSource 式采集进
 * GraphicsLayer,再由库做降采样高斯模糊 + AGSL 折射透镜,并自动管理折射
 * 采样所需的 padding/边界)——
 * 1. 背板:vibrancy(saturate 1.5) → blur 4dp → 透镜(高/量各 8dp);
 * 2. 药丸:blur 4dp → 透镜(高 10dp/量 14dp,Miuix 上游药丸参数)。
 * API < 33 库内全部 shader 路径有守卫,自动退化为纯色表面。
 *
 * 共通:药丸位置追逐 [position](MainShell 传 pager 小数进度)→ 拖页时「液体跟随」,
 * 弹簧产生 Gooey 拉伸;顶部/底部 1px 高光暗边 = InsetHighlight;外阴影 = tabBarShadow;
 * 选中态 = accent 图标 + 600 字重;按压 scale .94 spring。
 */
@Composable
fun GlassTabBar(
    hazeState: HazeState,
    selected: PhotoTab,
    onSelect: (PhotoTab) -> Unit,
    modifier: Modifier = Modifier,
    position: Float = selected.ordinal.toFloat(),
    liquidBackdrop: Backdrop? = null,
) {
    val colors = LocalPhotoColors.current
    val liquid = ThemeState.liquidGlass
    val darkTheme = colors.ink.luminance() > 0.5f
    // 液态模式需要 API 33+(RuntimeShader);缺 backdrop/低版本退回薄磨砂链
    val liquidActive = liquid && liquidBackdrop != null && isRuntimeShaderSupported()
    // API 33+ 用玻璃药丸层;31/32 由 TabItem 画纯色药丸
    val hasGlassPill = isRuntimeShaderSupported()

    // 药丸追逐 pager 小数进度:spring 追赶 = 液体黏滞感
    val pillX by animateFloatAsState(
        targetValue = position,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = 460f),
        label = "pill-x",
    )
    // Gooey 拉伸:离目标越远越扁宽(飞行中),到位回弹;体积感由 scaleY 反向补偿
    val stretch = 1f + (pillX - position).let { kotlin.math.abs(it) }.coerceAtMost(1.5f) * 0.10f

    // BiliPai tuned 预设的容器色:表面 40% alpha(dark 用暗 surface,light 用白)
    // ——液态玻璃的 tint 走 onDrawSurface,不再是 haze 的 colorEffects
    val liquidContainer = if (darkTheme) Color(0xFF16181B).copy(alpha = 0.40f) else Color.White.copy(alpha = 0.40f)
    val liquidPillContainer = if (darkTheme) Color(0xFF1E2124).copy(alpha = 0.32f) else Color.White.copy(alpha = 0.46f)

    Box(
        modifier
            .height(TabHeight)
            .tabBarShadow()
            .clip(TabShape)
            .then(
                if (liquidActive && liquidBackdrop != null) {
                    Modifier.liquidGlassSurface(
                        backdrop = liquidBackdrop,
                        shape = TabShape,
                        containerColor = liquidContainer,
                    )
                } else {
                    Modifier.hazeBlur(
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
                    )
                },
            ),
    ) {
        // 斜向流光(::after,115deg sheen)——暗色下左端泛白已整体去掉,仅浅色保留;
        // 液态模式由 surface 层自绘 tint,不再叠 sheen
        if (!liquidActive && colors.ink.luminance() < 0.5f) {
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
        if (!liquidActive) {
            InsetHighlight()
        }

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
                        .then(
                            if (liquidActive && liquidBackdrop != null) {
                                Modifier.liquidGlassSurface(
                                    backdrop = liquidBackdrop,
                                    shape = TabShape,
                                    containerColor = liquidPillContainer,
                                    isPill = true,
                                )
                            } else {
                                Modifier.hazeBlur(
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
                            },
                        )
                        // ui.css .tab.active background: var(--pill)(选中片垫色,very subtle)
                        .then(if (!liquidActive) Modifier.background(colors.pill, TabShape) else Modifier),
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

/**
 * BiliPai miuixFloatingDockSurface 液态玻璃简化版:
 * drawBackdrop(页面采集)→ vibrancy → blur → 折射透镜 → onDrawSurface 垫容器色。
 * [isPill] = 药丸档:Miuix 上游药丸透镜参数(高 10dp/量 14dp),色散可见。
 */
private fun Modifier.liquidGlassSurface(
    backdrop: Backdrop,
    shape: Shape,
    containerColor: Color,
    isPill: Boolean = false,
): Modifier = drawBackdrop(
    backdrop = backdrop,
    shape = { shape },
    effects = {
        colorControls(brightness = 0f, contrast = 1f, saturation = 1.5f)
        val blurPx = (if (isPill) 4.dp else 4.dp).toPx()
        blur(blurPx, blurPx)
        if (isPill) {
            // Miuix 上游药丸透镜:高 10dp / 折射量 14dp,色散 0.5(API pill 同款)
            lens(
                refractionHeight = 10.dp.toPx(),
                refractionAmount = 14.dp.toPx(),
                chromaticAberration = 0.4f,
            )
        } else {
            // 壳体透镜:58dp 高 bar 用 8dp(过强会让上下折射边在中线相撞出虾线)
            lens(
                refractionHeight = 8.dp.toPx(),
                refractionAmount = 8.dp.toPx(),
                chromaticAberration = 0f,
            )
        }
    },
    onDrawSurface = {
        drawRect(containerColor)
    },
)

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
