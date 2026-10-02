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
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
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
enum class PhotoTab(val label: String, val iconParts: List<dev.jinsfoni.photobook.ui.icons.IconPart>) {
    EXPLORE("发现", listOf(dev.jinsfoni.photobook.ui.icons.TabExploreIcon)),
    COLLECTIONS("写真", listOf(dev.jinsfoni.photobook.ui.icons.TabCollectionsIcon)),
    MODELS("模特", listOf(dev.jinsfoni.photobook.ui.icons.TabModelsIcon)),
    FAVORITES("收藏", listOf(dev.jinsfoni.photobook.ui.icons.TabFavoritesIcon)),
}

private val TabHeight = 64.dp
private val TabShape = RoundedCornerShape(999.dp)

/**
 * 玻璃底栏(原型 .tabbar):64dp 高、999dp 全圆角、blur 3dp + saturate 165% +
 * brightness 1.08(色彩矩阵 1.782≈1.65×1.08)、barBg 纱色、斜向流光、inset 高光/暗边。
 * 选中 tab = pill 胶囊 + accent 图标 + 600 字重;按压 scale .94 spring 弹性。
 */
@Composable
fun GlassTabBar(
    hazeState: HazeState,
    selected: PhotoTab,
    onSelect: (PhotoTab) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalPhotoColors.current

    Box(
        modifier
            .height(TabHeight)
            .tabBarShadow()
            .clip(TabShape)
            .hazeBlur(
                HazeInput.Sources(hazeState),
                HazeBlurStyle {
                    blurRadius(3.dp)
                    backgroundColor(colors.barBg)
                    colorEffects(
                        listOf(
                            HazeColorEffect.colorFilter(
                                ColorFilter.colorMatrix(
                                    ColorMatrix(
                                        floatArrayOf(
                                            1.782f, 0f, 0f, 0f, 0f,
                                            0f, 1.782f, 0f, 0f, 0f,
                                            0f, 0f, 1.782f, 0f, 0f,
                                            0f, 0f, 0f, 1f, 0f,
                                        )
                                    )
                                )
                            )
                        )
                    )
                },
            ),
    ) {
        // 斜向流光(::after,115deg sheen)
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
        // inset 高光/暗边/内晕
        InsetHighlight()

        Row(
            Modifier
                .fillMaxSize()
                .padding(6.dp),
        ) {
            PhotoTab.entries.forEach { tab ->
                TabItem(
                    tab = tab,
                    selected = tab == selected,
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
            .then(if (selected) Modifier.background(colors.pill, TabShape) else Modifier)
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
                tab.label,
                style = if (selected) PhotoType.tabLabelActive else PhotoType.tabLabel,
                color = if (selected) colors.ink else colors.ink2,
            )
        }
    }
}
