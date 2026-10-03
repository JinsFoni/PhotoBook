package dev.jinsfoni.photobook.ui.screens.favorites

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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

    androidx.compose.runtime.LaunchedEffect(Unit) { vm.refresh() }

    Column(Modifier.fillMaxSize()) {
        // appbar
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
        }

        // 三段 Tab:文本 + 2dp accent 底条(原型 .fav-tabs)
        Row(
            Modifier.padding(horizontal = 18.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            FavTab.entries.forEach { tab ->
                val selected = tab == state.tab
                // IntrinsicSize.Min: Column 宽度 = 文字宽,底条才不会拓到整行把其他 Tab 挤出屏
                Column(
                    Modifier
                        .width(IntrinsicSize.Min)
                        .photoClickable { vm.selectTab(tab) },
                ) {
                    Text(
                        tab.label,
                        style = if (selected) PhotoType.cardTitle else PhotoType.caption,
                        color = if (selected) colors.ink else colors.ink3,
                    )
                    Box(
                        Modifier
                            .padding(top = 5.dp)
                            .fillMaxWidth()
                            .height(2.dp)
                            .clip(RoundedCornerShape(1.dp))
                            .background(if (selected) colors.accent else androidx.compose.ui.graphics.Color.Transparent)
                    )
                }
            }
            Spacer(Modifier.weight(1f))
            Text(
                state.countText(),
                style = PhotoType.micro.copy(letterSpacing = 0.4.sp),
                color = colors.ink3,
            )
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
                    // 照片段 3 列方图(design.md S7)
                    columns = GridCells.Fixed(3),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 14.dp, end = 14.dp, bottom = 112.dp),
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                    verticalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    items(state.photos.size) { i ->
                        val p = state.photos[i]
                        Box(
                            Modifier
                                .aspectRatio(1f)
                                .clip(RoundedCornerShape(2.dp))
                                .background(colors.paper2)
                                .photoClickable { onOpenPhoto(p.slug, p.idx) },
                        ) {
                            AsyncImage(
                                model = p.thumbUrl,
                                contentDescription = p.slug,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize(),
                            )
                        }
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
