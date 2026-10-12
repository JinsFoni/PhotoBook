package dev.jinsfoni.photobook.ui.nav

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import com.kyant.backdrop.BackdropEffectScope
import com.kyant.backdrop.backdrops.LayerBackdrop
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.kyant.backdrop.effects.lens as libraryLens

/**
 * 玻璃底栏的页面采集源(Kyant0/AndroidLiquidGlass Backdrop 体系):
 * 挂到页面内容容器上,页面绘制录进 LayerBackdrop 供底栏 drawBackdrop 采样。
 * 底栏不在内容容器内,永远采不到自身。
 */
@Stable
class GlassBarBackdropSource internal constructor(
    val backdrop: LayerBackdrop,
    val modifier: Modifier,
) {
    val isReady: Boolean get() = true
}

@Composable
internal fun rememberGlassBarBackdropSource(): GlassBarBackdropSource {
    val backdrop = rememberLayerBackdrop()
    return remember(backdrop) {
        GlassBarBackdropSource(
            backdrop = backdrop,
            modifier = Modifier.layerBackdrop(backdrop),
        )
    }
}

/**
 * 库本体自带 lens(roundedRect 折射透镜,SDF 边缘环带内沿法线偏移采样,
 * 中心 1:1 零畸变,可选深度效果/RGB 色散)。转发调用保持调用侧语义同旧版。
 */
fun BackdropEffectScope.lens(
    refractionHeight: Float,
    refractionAmount: Float,
    chromaticAberration: Boolean = false,
    depthEffect: Boolean = false,
) {
    libraryLens(
        refractionHeight = refractionHeight,
        refractionAmount = refractionAmount,
        depthEffect = depthEffect,
        chromaticAberration = chromaticAberration,
    )
}

