package dev.jinsfoni.photobook.ui.screens.explore

import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import dev.jinsfoni.photobook.core.design.LocalPhotoColors
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.nav.LocalGlassBarBottomInset
import dev.jinsfoni.photobook.ui.models.DiscoverFeed

/** S1 发现页(原型 s1-explore.html):hero 轮播 → 最新入库 grid2。 */
@Composable
fun ExploreScreen(
    onOpenCollection: (slug: String) -> Unit,
    onOpenAllCollections: () -> Unit = {},
    onOpenSearch: () -> Unit = {},
    vm: ExploreViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()

    Box(Modifier.fillMaxSize()) {
        val feed = state.feed
        when {
            state.loading && feed == null -> ExploreSkeleton()
            feed != null -> ExploreContent(
                feed = feed,
                refreshing = state.refreshing,
                onOpenCollection = onOpenCollection,
                onOpenAllCollections = onOpenAllCollections,
                onOpenSearch = onOpenSearch,
                onRetry = vm::retry,
            )
            state.error != null -> Box(
                Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(message = state.error ?: "加载失败")
                    Spacer(Modifier.height(16.dp))
                    Text(
                        stringResource(R.string.retry),
                        style = PhotoType.caption,
                        color = colors.accent,
                        modifier = Modifier.photoClickable(vm::retry).padding(8.dp),
                    )
                }
            }
        }
    }
}

/** 首载骨架:hero 块 + 2 列卡骨架。 */
@Composable
private fun ExploreSkeleton() {
    val colors = LocalPhotoColors.current
    Column(Modifier.fillMaxSize()) {
        SkeletonBox(
            Modifier
                .fillMaxWidth()
                .aspectRatio(390f / 436f)
                .statusBarsPadding(),
            cornerRadius = 0,
        )
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 15.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            SkeletonBox(Modifier.size(width = 110.dp, height = 26.dp), cornerRadius = 2)
            SkeletonBox(Modifier.size(width = 52.dp, height = 17.dp), cornerRadius = 2)
        }
        Row(Modifier.padding(horizontal = 18.dp), horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
    }
}

@Composable
private fun ExploreContent(
    feed: DiscoverFeed,
    refreshing: Boolean,
    onOpenCollection: (String) -> Unit,
    onOpenAllCollections: () -> Unit,
    onOpenSearch: () -> Unit,
    onRetry: () -> Unit,
) {
    val colors = LocalPhotoColors.current
    val gridState = rememberLazyGridState()

    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        state = gridState,
        modifier = Modifier.fillMaxSize(),
        // 与写真页一致:左右 18dp 留白,卡片不贴屏幕边
        contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 112.dp + LocalGlassBarBottomInset.current),
        horizontalArrangement = Arrangement.spacedBy(13.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // 顶栏:词标 + 设置入口(词标与 hero 重叠区由 hero 纱保证可读性)
        item(span = { GridItemSpan(2) }) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(colors.paper)
                    .statusBarsPadding()
                    .padding(top = 6.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Photo Collection",
                    style = PhotoType.cardTitle,
                    color = colors.ink,
                )
                // 搜索入口:与图集页一致的描边放大镜(20dp,ink2)
                dev.jinsfoni.photobook.ui.icons.StrokeIcon(
                    dev.jinsfoni.photobook.ui.icons.SearchIcon,
                    size = 20.dp,
                    tint = colors.ink2,
                    modifier = Modifier
                        .photoClickable(onOpenSearch)
                        .padding(4.dp),
                )
            }
        }
        // hero 轮播(最新入库前 4,跨两列;不按 featured 精选标记走)
        item(span = { GridItemSpan(2) }) {
            HeroCarousel(
                items = feed.latest.take(4),
                onOpen = onOpenCollection,
            )
        }
        // 节标题「最新入库」
        item(span = { GridItemSpan(2) }) {
            dev.jinsfoni.photobook.ui.components.SectionHeader(
                title = stringResource(R.string.latest_added),
                actionText = stringResource(R.string.view_all),
                // 全部列表 = 写真 tab(S2);不能传空 slug 开详情 ——
                // 空 slug 会请求 GET collections/ 被 307 重定向到列表接口,
                // 详情 DTO 解码列表 JSON 即崩(MissingFieldException)
                onAction = onOpenAllCollections,
            )
        }
        if (feed.latest.isEmpty() && !refreshing) {
            item(span = { GridItemSpan(2) }) {
                Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                    EmptyState(message = stringResource(R.string.empty_collections_pull))
                }
            }
        }
        items(feed.latest.size) { i ->
            val c = feed.latest[i]
            CollectionCard(
                title = c.title,
                subtitle = "${c.modelName} · ${c.count} 张",
                imageUrl = c.imageUrl,
                onClick = { onOpenCollection(c.slug) },
            )
        }
    }
}

/** hero 轮播:436dp 高,底部渐隐纱 + kick/标题/meta(原型 .hero)。 */
@Composable
private fun HeroCarousel(
    items: List<dev.jinsfoni.photobook.ui.models.CollectionCard>,
    onOpen: (String) -> Unit,
) {
    if (items.isEmpty()) return
    val pagerState = rememberPagerState(pageCount = { items.size })

    Column {
        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxWidth()) { page ->
            val item = items[page]
            Box(
                Modifier
                    .fillMaxWidth()
                    .aspectRatio(390f / 436f)
                    .photoClickable { onOpen(item.slug) },
            ) {
                AsyncImage(
                    model = item.imageUrl,
                    contentDescription = item.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
                // 底部渐隐纱(rgba(5,5,6,.78)→0,62% 处收)
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                0f to Color(0, 0, 0, 0),
                                0.62f to Color(0, 0, 0, 0),
                                1f to Color(5, 5, 6, 199),
                            )
                        ),
                )
                Column(Modifier.align(Alignment.BottomStart).padding(22.dp)) {
                    Text(
                        stringResource(R.string.latest_added),
                        style = PhotoType.tag.copy(letterSpacing = 2.5.sp),
                        color = Color.White.copy(alpha = 0.69f),
                    )
                    Text(
                        item.title,
                        style = PhotoType.heroTitle,
                        color = Color.White,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 9.dp),
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(9.dp),
                        modifier = Modifier.padding(top = 11.dp),
                    ) {
                        Text(item.modelName, style = PhotoType.caption, color = Color.White.copy(alpha = 0.65f))
                        Box(Modifier.size(3.dp).clip(RoundedCornerShape(50)).background(Color.White.copy(alpha = 0.44f)))
                        Text("${item.count} Photos", style = PhotoType.caption, color = Color.White.copy(alpha = 0.65f))
                    }
                }
            }
        }
        // 页码条(.pager:2dp 短条,激活 24dp accent)
        Row(
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            modifier = Modifier.padding(start = 18.dp, top = 15.dp),
        ) {
            repeat(items.size) { i ->
                Box(
                    Modifier
                        .padding(vertical = 0.dp)
                        .height(2.dp)
                        .fillMaxWidth(if (i == pagerState.currentPage) 0.062f else 0.038f)
                        .clip(RoundedCornerShape(1.dp))
                        .background(
                            if (i == pagerState.currentPage) LocalPhotoColors.current.accent
                            else LocalPhotoColors.current.line2
                        ),
                )
            }
        }
    }
}
