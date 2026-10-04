package dev.jinsfoni.photobook.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.ui.screens.collections.CollectionsScreen
import dev.jinsfoni.photobook.ui.screens.explore.ExploreScreen
import dev.jinsfoni.photobook.ui.screens.favorites.FavoritesScreen
import dev.jinsfoni.photobook.ui.screens.models.ModelsScreen
import dev.jinsfoni.photobook.ui.nav.GlassTabBar
import dev.jinsfoni.photobook.ui.nav.PhotoTab
import kotlinx.coroutines.launch

/**
 * 主壳:顶部 4 页横滑(占位屏)+ 玻璃底栏。
 * 主题切换收敛到 S9 设置页(右上角临时循环按钮已移除)。
 */
@Composable
fun MainShell(
    hazeState: HazeState,
    onOpenSettings: () -> Unit = {},
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
                        onOpenSearch = onOpenSearch,
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
                        onOpenSettings = onOpenSettings,
                    )
                }
            }
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
