package dev.jinsfoni.photobook.ui.screens.videos

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import dev.jinsfoni.photobook.R
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.BackIcon
import dev.jinsfoni.photobook.ui.icons.CheckIcon
import dev.jinsfoni.photobook.ui.icons.SortLatestIcon
import dev.jinsfoni.photobook.ui.icons.SortOldestIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import dev.jinsfoni.photobook.ui.nav.LocalGlassBarBottomInset

/**
 * 写真视频列表:与 S2 写真列表完全平行的一套(2 列卡流 / 排序四档 / 滚动分页)。
 * 视频是独立模块 —— 同一 repo 层的不同端点,写真列表零影响。
 */
@Composable
fun VideosScreen(
    onOpenVideoAlbum: (String) -> Unit,
    onOpenSearch: (() -> Unit)? = {},
    onBack: (() -> Unit)? = null,
    vm: VideosViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val gridState = rememberLazyGridState()

    LaunchedEffect(Unit) { vm.start(null) }

    LaunchedEffect(gridState, state.endReached) {
        snapshotFlow { gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
            .collect { last ->
                val total = gridState.layoutInfo.totalItemsCount
                if (total > 0 && last >= total - 4) vm.loadMore()
            }
    }

    Box(Modifier.fillMaxSize()) {
        BlurBackdrop(state.items.firstOrNull()?.imageUrl)
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (onBack != null) {
                Box(
                    Modifier.photoClickable(onBack).padding(8.dp),
                ) {
                    StrokeIcon(BackIcon, size = 22.dp, tint = colors.ink2)
                }
            }
            Text(
                stringResource(R.string.video_albums_noun),
                style = PhotoType.wordmark,
                color = colors.ink,
            )
            Spacer(Modifier.weight(1f))
            if (onOpenSearch != null) {
                StrokeIcon(
                    dev.jinsfoni.photobook.ui.icons.SearchIcon,
                    size = 20.dp,
                    tint = colors.ink2,
                    modifier = Modifier.photoClickable(onOpenSearch).padding(4.dp),
                )
            }
        }

        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 2.dp)
                .padding(bottom = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            VideoSortMenu(state.sort, vm::setSort, colors.ink2)
            Spacer(Modifier.weight(1f))
            Text(
                state.countText,
                style = PhotoType.micro.copy(letterSpacing = 0.4.sp),
                color = colors.ink3,
            )
        }

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
            ) { EmptyState(message = stringResource(R.string.empty_videos)) }
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
                        subtitle = "${c.modelName} · ${c.count} 段",
                        imageUrl = c.imageUrl,
                        onClick = { onOpenVideoAlbum(c.slug) },
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

/** 排序菜单(与写真列表同款四档,轴分组 + 右侧打勾)。 */
@Composable
private fun VideoSortMenu(sort: VideoAlbumSort, onSelect: (VideoAlbumSort) -> Unit, tint: androidx.compose.ui.graphics.Color) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        StrokeIcon(
            if (sort.name.endsWith("_LATEST")) SortLatestIcon else SortOldestIcon,
            size = 20.dp,
            tint = tint,
            modifier = Modifier.photoClickable { expanded = true }.padding(4.dp),
        )
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            containerColor = MaterialTheme.colorScheme.surface,
        ) {
            val axes = listOf(
                stringResource(R.string.sort_by_published) to listOf(
                    VideoAlbumSort.PUBLISHED_LATEST, VideoAlbumSort.PUBLISHED_OLDEST),
                stringResource(R.string.sort_by_added) to listOf(
                    VideoAlbumSort.ADDED_LATEST, VideoAlbumSort.ADDED_OLDEST),
            )
            axes.forEachIndexed { ai, (label, options) ->
                if (ai > 0) HorizontalDivider()
                DropdownMenuItem(
                    text = { Text(label, style = PhotoType.caption) },
                    onClick = {},
                    enabled = false,
                )
                options.forEach { s ->
                    val selected = s == sort
                    DropdownMenuItem(
                        text = {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    stringResource(if (s.name.endsWith("_LATEST")) R.string.sort_latest else R.string.sort_earliest),
                                    style = PhotoType.caption,
                                    color = if (selected) tint else tint.copy(alpha = 0.6f),
                                )
                                Spacer(Modifier.weight(1f))
                                if (selected) {
                                    StrokeIcon(CheckIcon, size = 14.dp, tint = tint)
                                }
                            }
                        },
                        onClick = { expanded = false; onSelect(s) },
                    )
                }
            }
        }
    }
}
