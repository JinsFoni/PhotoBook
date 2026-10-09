package dev.jinsfoni.photobook.ui.screens.collections

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.TagChip
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.nav.LocalGlassBarBottomInset

/**
 * S2 写真列表:2 列卡流、筛选行(标签 chips + 排序 + 计数)、
 * 滚动分页(20/页)。进入时由导航传入 tag(点 S1 标签)。
 */
@Composable
fun CollectionsScreen(
    initialTag: String?,
    onOpenCollection: (String) -> Unit,
    onOpenSearch: () -> Unit = {},
    vm: CollectionsViewModel = hiltViewModel(),
) {
    // 所有页面统一跟随全局主题(设置页切换),不再有页面级强制深/浅
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val gridState = rememberLazyGridState()

    LaunchedEffect(Unit) { vm.start(initialTag) }

    // 滚动接近尾部触发分页
    LaunchedEffect(gridState, state.endReached) {
        snapshotFlow { gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
            .collect { last ->
                val total = gridState.layoutInfo.totalItemsCount
                if (total > 0 && last >= total - 4) vm.loadMore()
            }
    }

    Box(Modifier.fillMaxSize()) {
        // 虚化主题垫底:首张合集封面(设计稿 s2 用 cover-3.jpg 同源做法)
        BlurBackdrop(state.items.firstOrNull()?.imageUrl)
    Column(Modifier.fillMaxSize()) {
        // appbar(背景延伸式:内容从状态栏下开始)
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                if (state.tag != null) "#${state.tag}" else stringResource(R.string.collections_noun),
                style = PhotoType.wordmark,
                color = colors.ink,
            )
            Spacer(Modifier.weight(1f))
            dev.jinsfoni.photobook.ui.icons.StrokeIcon(
                dev.jinsfoni.photobook.ui.icons.SearchIcon,
                size = 20.dp,
                tint = colors.ink2,
                modifier = Modifier
                    .photoClickable(onOpenSearch)
                    .padding(4.dp),
            )
        }

        // 筛选行:排序 chip + 计数(原型 .filterrow;标签筛选由进入参数决定,M1 不做抽屉)
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 2.dp)
                .padding(bottom = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TagChip(
                label = if (state.sort == "latest") stringResource(R.string.sort_latest) else stringResource(R.string.sort_earliest),
                selected = true,
                onClick = vm::toggleSort,
            )
            Spacer(Modifier.weight(1f))
            Text(
                state.countText,
                style = PhotoType.micro.copy(letterSpacing = 0.4.sp),
                color = colors.ink3,
            )
        }

        // 下拉刷新(仅内容区;首载骨架/错误态走骨架与重试,不套指示器)
        androidx.compose.material3.pulltorefresh.PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize(),
        ) {
        when {
            state.loading -> GridSkeleton()
            state.items.isEmpty() && state.error != null -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp + LocalGlassBarBottomInset.current),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(message = state.error ?: "加载失败")
                    Spacer(Modifier.height(12.dp))
                    Text(
                        stringResource(R.string.retry),
                        style = PhotoType.caption,
                        color = colors.accent,
                        modifier = Modifier.photoClickable(vm::retry).padding(8.dp),
                    )
                }
            }
            state.items.isEmpty() -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp + LocalGlassBarBottomInset.current),
                contentAlignment = Alignment.Center,
            ) { EmptyState(message = stringResource(R.string.empty_tag)) }
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                state = gridState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 112.dp + LocalGlassBarBottomInset.current),
                horizontalArrangement = Arrangement.spacedBy(13.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                items(state.items.size) { i ->
                    val c = state.items[i]
                    CollectionCard(
                        title = c.title,
                        subtitle = "${c.modelName} · ${c.count} 张",
                        imageUrl = c.imageUrl,
                        onClick = { onOpenCollection(c.slug) },
                    )
                }
                if (state.loadingMore) {
                    item(span = { GridItemSpan(2) }) {
                        Box(Modifier.fillMaxWidth().padding(vertical = 14.dp), contentAlignment = Alignment.Center) {
                            SkeletonBox(Modifier.height(2.dp).fillMaxWidth(0.2f), cornerRadius = 1)
                        }
                    }
                }
            }
        }
        }
    }
    }
}

@Composable
private fun GridSkeleton() {
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
    }
}
