package dev.jinsfoni.photobook.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.IconWidths
import dev.jinsfoni.photobook.ui.icons.SettingsIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import dev.jinsfoni.photobook.ui.screens.collections.CollectionsScreen
import dev.jinsfoni.photobook.ui.screens.explore.ExploreScreen
import dev.jinsfoni.photobook.ui.screens.favorites.FavoritesScreen
import dev.jinsfoni.photobook.ui.screens.models.ModelsScreen
import dev.jinsfoni.photobook.ui.nav.GlassTabBar
import dev.jinsfoni.photobook.ui.nav.PhotoTab
import kotlinx.coroutines.launch

/**
 * 主壳:顶部 4 页横滑(占位屏)+ 玻璃底栏 + 右上角临时主题切换(S9 实装后移除)。
 * S1 发现屏(Task 10)会替换 discover 占位。
 */
@Composable
fun MainShell(
    hazeState: HazeState,
    onThemeCycle: () -> Unit,
    onOpenCollection: (String) -> Unit = {},
    onOpenModel: (String) -> Unit = {},
    onOpenPhoto: (String, Int) -> Unit = { _, _ -> },
    onOpenSearch: () -> Unit = {},
) {
    val colors = LocalPhotoColors.current
    val pagerState = rememberPagerState(pageCount = { PhotoTab.entries.size })
    val scope = rememberCoroutineScope()
    // 「查看全部」跨页动作:发现页跳到写真 tab(S2 即全部列表)
    val openAllCollections: () -> Unit = {
        scope.launch { pagerState.animateScrollToPage(PhotoTab.COLLECTIONS.ordinal) }
    }

    Box(Modifier.fillMaxSize().background(colors.paper)) {
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .fillMaxSize()
                // 收雪:页面内容进入 haze,玻璃底栏取它做磨砂
                .hazeSource(hazeState),
        ) { page ->
            // haze capture 不含 modifier 链上 hazeSource 之前的绘制(如 background),
            // 所以不透明底必须画在 source 内容**内部**:各屏不含 paper 底,
            // 透明区域 blur 后仍透明,玻璃会透出自身阴影(灰色磨砂板观感)
            Box(Modifier.fillMaxSize().background(colors.paper)) {
                when (PhotoTab.entries[page]) {
                    PhotoTab.EXPLORE -> ExploreScreen(
                        onOpenCollection = onOpenCollection,
                        onOpenAllCollections = openAllCollections,
                    )
                    PhotoTab.COLLECTIONS -> CollectionsScreen(
                        initialTag = null,
                        onOpenCollection = onOpenCollection,
                        onOpenSearch = onOpenSearch,
                    )
                    PhotoTab.MODELS -> ModelsScreen(onOpenModel = onOpenModel)
                    PhotoTab.FAVORITES -> FavoritesScreen(
                        onOpenModel = onOpenModel,
                        onOpenCollection = onOpenCollection,
                        onOpenPhoto = { slug: String, idx: Int -> onOpenPhoto(slug, idx) },
                    )
                }
            }
        }

        // 右上角临时主题切换按钮(悬浮,白描边图标,适配沉浸图区)
        Box(
            Modifier
                .align(Alignment.TopEnd)
                .padding(
                    top = WindowInsets.statusBars.asPaddingValues()
                        .calculateTopPadding() + 10.dp,
                    end = 18.dp,
                )
        ) {
            ThemeCycleButton(onThemeCycle)
        }

        GlassTabBar(
            hazeState = hazeState,
            selected = PhotoTab.entries[pagerState.currentPage],
            onSelect = { tab ->
                scope.launch { pagerState.animateScrollToPage(tab.ordinal) }
            },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(horizontal = 14.dp)
                .padding(bottom = 20.dp),
        )
    }
}

/** 临时主题循环按钮:Light → Dark → Blur。 */
@Composable
private fun ThemeCycleButton(onClick: () -> Unit) {
    val mode = LocalThemeMode.current
    // 沉浸区背景未知,垫一个纱底保证可读
    Box(
        Modifier
            .height(36.dp)
            .background(
                Brush.verticalGradient(
                    listOf(Color.White.copy(alpha = 0.18f), Color.White.copy(alpha = 0.08f))
                ),
                RoundedCornerShape(999.dp)
            )
            .photoClickable(onClick),
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            StrokeIcon(SettingsIcon, size = 16.dp, tint = Color.White, strokeWidth = IconWidths.THIN)
            Text(
                when (mode) {
                    ThemeMode.LIGHT -> "Light"
                    ThemeMode.DARK -> "Dark"
                    ThemeMode.BLUR -> "Blur"
                },
                style = PhotoType.micro,
                color = Color.White,
            )
        }
    }
}
