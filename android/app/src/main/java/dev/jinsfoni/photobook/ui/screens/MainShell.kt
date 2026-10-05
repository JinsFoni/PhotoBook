package dev.jinsfoni.photobook.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.ScopedTheme
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.ui.screens.collections.CollectionsScreen
import dev.jinsfoni.photobook.ui.screens.explore.ExploreScreen
import dev.jinsfoni.photobook.ui.screens.favorites.FavoritesScreen
import dev.jinsfoni.photobook.ui.screens.models.ModelsScreen
import dev.jinsfoni.photobook.ui.nav.GlassTabBar
import dev.jinsfoni.photobook.ui.nav.LocalGlassBarBottomInset
import dev.jinsfoni.photobook.ui.nav.PhotoTab
import dev.jinsfoni.photobook.ui.nav.rememberGlassBarBackdropSource
import kotlinx.coroutines.launch

/**
 * 主壳:顶部 4 页横滑(占位屏)+ 玻璃底栏。
 * 主题切换收敛到 S9 设置页(右上角临时循环按钮已移除)。
 * 各页主题隔离:写真/收藏强制深色画廊,发现/模特跟随全局——页面级 ScopedTheme,
 * 不改写 ThemeState.mode;底栏材质颜色跟随当前所在页。
 */

/** 每个 tab 的主题:深色画廊页(写真/收藏),其余 null = 跟随全局。 */
private val PhotoTab.shellTheme: ThemeMode?
    get() = when (this) {
        PhotoTab.COLLECTIONS, PhotoTab.FAVORITES -> ThemeMode.DARK
        else -> null
    }

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
    // 手势条/三键导航的高度:底栏上浮 + 各页列表底部留白都靠它避让
    val navBarInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    // 「查看全部」跨页动作:发现页跳到写真 tab(S2 即全部列表)
    val openAllCollections: () -> Unit = {
        scope.launch { pagerState.animateScrollToPage(PhotoTab.COLLECTIONS.ordinal) }
    }

    CompositionLocalProvider(LocalGlassBarBottomInset provides navBarInset) {
        // 液态玻璃采集源(BiliPai ChromeBackdropSource 同款):挂在页面容器上,
        // 底栏 drawBackdrop 采样它 —— 页面先录进 GraphicsLayer 再上屏,底栏永远采不到自身
        val liquidSource = rememberGlassBarBackdropSource()
        Box(Modifier.fillMaxSize().background(colors.paper)) {
            HorizontalPager(
                state = pagerState,
                modifier = Modifier
                    .fillMaxSize()
                    // 收雪:页面内容进入 haze,玻璃底栏取它做磨砂
                    .hazeSource(hazeState)
                    // 液态玻璃采集:同页内容双录(miuix layerBackdrop + GraphicsLayer 回放)
                    .then(liquidSource.modifier),
            ) { page ->
                val tab = PhotoTab.entries[page]
                ScopedTheme(mode = tab.shellTheme) {
                    val pageColors = LocalPhotoColors.current
                    // haze capture 不含 modifier 链上 hazeSource 之前的绘制(如 background),
                    // 所以不透明底必须画在 source 内容**内部**:各屏不含 paper 底,
                    // 透明区域 blur 后仍透明,玻璃会透出自身阴影(灰色磨砂板观感)
                    Box(Modifier.fillMaxSize().background(pageColors.paper)) {
                        when (tab) {
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
            }

            // 底栏材质颜色跟随当前页的主题(拖页切换瞬间生效)
            val currentTab = PhotoTab.entries[pagerState.currentPage]
            ScopedTheme(mode = currentTab.shellTheme) {
                val barColors = LocalPhotoColors.current
                GlassTabBar(
                    hazeState = hazeState,
                    selected = currentTab,
                    // 小数进度:拖页时选中药丸「液体跟随」
                    position = pagerState.currentPage + pagerState.currentPageOffsetFraction,
                    onSelect = { tab ->
                        scope.launch { pagerState.animateScrollToPage(tab.ordinal) }
                    },
                    liquidBackdrop = liquidSource.backdrop,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        // 先让出系统导航栏(手势区/三键区),再贴设计稿的 14/20dp 边距
                        .windowInsetsPadding(WindowInsets.navigationBars)
                        .padding(horizontal = 14.dp)
                        .padding(bottom = 20.dp),
                )
            }
        }
    }
}
