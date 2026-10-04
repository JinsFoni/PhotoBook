package dev.jinsfoni.photobook.ui.screens.favorites

import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.ModelCard
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.photoClickable

/**
 * S7 收藏页:三段 Tab(模特/写真/照片)。数据来自 FavoritesRepository.state
 * (与详情/灯箱心形同一事实源),进入时 refresh。
 * photo key 约定 "slug:idx";S4 路由由 shell 层转成 (slug, idx)。
 */
@Composable
fun FavoritesScreen(
    onOpenModel: (String) -> Unit,
    onOpenCollection: (String) -> Unit,
    onOpenPhoto: (String, Int) -> Unit,
    vm: FavoritesViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()

    // S7 强制 dark(原型 theme:Dark;深色画廊模式,进入照片/模特详情由对方页自管)
    LaunchedEffect(Unit) {
        dev.jinsfoni.photobook.core.design.ThemeState.mode =
            dev.jinsfoni.photobook.core.design.ThemeMode.DARK
        vm.refresh()
    }

    Column(Modifier.fillMaxSize()) {
        // appbar(原型:词标收藏 + 顶栏多选入口 copy 图标,V1 暂无批量操作 → 仅占位)
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "收藏",
                style = PhotoType.byline.copy(fontFamily = FontFamily.Serif, fontSize = 17.sp),
                color = colors.ink,
            )
            Spacer(Modifier.weight(1f))
            dev.jinsfoni.photobook.ui.icons.StrokeIcon(
                dev.jinsfoni.photobook.ui.icons.CopyIcon,
                size = 20.dp,
                tint = colors.ink2,
            )
        }

        // 三段 Tab(原型 .seg:照片/写真/模特;内联计数;整行 1px 底线;选中 2px accent 下划线+计数变红)
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp)
                .drawBehind { drawLine(colors.line, Offset(0f, size.height), Offset(size.width, size.height), 1.dp.toPx()) },
        ) {
            FavTab.entries.forEachIndexed { i, tab ->
                val selected = tab == state.tab
                Column(
                    Modifier
                        .photoClickable { vm.selectTab(tab) }
                        .padding(start = if (i == 0) 0.dp else 24.dp)
                        // 2dp accent 下划线画在本段底部(压在整行底线上,原型 bottom:-1px)
                        .drawBehind {
                            if (selected) {
                                drawRect(
                                    colors.accent,
                                    topLeft = Offset(0f, size.height - 2.dp.toPx()),
                                    size = Size(size.width, 2.dp.toPx()),
                                )
                            }
                        },
                ) {
                    // 计数与文字同基线(原型 inline baseline),底距由外层留白承担
                    Row(
                        Modifier.padding(top = 9.dp),
                        verticalAlignment = Alignment.Bottom,
                    ) {
                        Text(
                            tab.label,
                            style = PhotoType.byline.copy(fontSize = 14.5.sp),
                            color = if (selected) colors.ink else colors.ink3,
                        )
                        Text(
                            " ${state.countFor(tab)}",
                            style = PhotoType.tag.copy(fontSize = 10.5.sp),
                            color = if (selected) colors.accent else colors.ink3,
                        )
                    }
                }
            }
        }

        when {
            state.loading -> TabSkeleton(state.tab)
            state.error != null -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(message = state.error ?: "加载失败")
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "重试", style = PhotoType.caption, color = colors.accent,
                        modifier = Modifier.photoClickable(vm::refresh).padding(8.dp),
                    )
                }
            }
            state.isEmpty() -> Box(
                Modifier.fillMaxSize().padding(bottom = 112.dp),
                contentAlignment = Alignment.Center,
            ) { EmptyState(message = emptyText(state.tab)) }
            else -> when (state.tab) {
                FavTab.MODELS -> LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 112.dp),
                    horizontalArrangement = Arrangement.spacedBy(13.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp),
                ) {
                    items(state.models.size) { i ->
                        val m = state.models[i]
                        ModelCard(
                            name = m.name,
                            subtitle = "${m.count} 个写真",
                            imageUrl = m.imageUrl,
                            onClick = { onOpenModel(m.slug) },
                        )
                    }
                }
                FavTab.COLLECTIONS -> LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 112.dp),
                    horizontalArrangement = Arrangement.spacedBy(13.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp),
                ) {
                    items(state.collections.size) { i ->
                        val c = state.collections[i]
                        CollectionCard(
                            title = c.title,
                            subtitle = "${c.modelName} · ${c.count} 张",
                            imageUrl = c.imageUrl,
                            onClick = { onOpenCollection(c.slug) },
                        )
                    }
                }
                FavTab.PHOTOS -> LazyVerticalGrid(
                    // 照片段 3 列(原型 .grid3:18px 边距,11px gap);图片按原图完整比例展示,不裁方
                    columns = GridCells.Fixed(3),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 15.dp, bottom = 112.dp),
                    horizontalArrangement = Arrangement.spacedBy(11.dp),
                    verticalArrangement = Arrangement.spacedBy(11.dp),
                ) {
                    items(state.photos.size) { i ->
                        val p = state.photos[i]
                        // 无高度约束 → Coil 按图片内在比例定高(等比缩略图,比例保真)
                        AsyncImage(
                            model = p.thumbUrl,
                            contentDescription = p.slug,
                            contentScale = ContentScale.FillWidth,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(2.dp))
                                .background(colors.paper2)
                                .photoClickable { onOpenPhoto(p.slug, p.idx) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TabSkeleton(tab: FavTab) {
    val span = if (tab == FavTab.PHOTOS) 3 else 2
    Row(Modifier.padding(horizontal = 18.dp), horizontalArrangement = Arrangement.spacedBy(13.dp)) {
        repeat(span) { SkeletonBox(Modifier.weight(1f)) }
    }
}

internal fun emptyText(tab: FavTab) = when (tab) {
    FavTab.MODELS -> "还没有收藏模特"
    FavTab.COLLECTIONS -> "还没有收藏写真"
    FavTab.PHOTOS -> "还没有收藏照片"
}
