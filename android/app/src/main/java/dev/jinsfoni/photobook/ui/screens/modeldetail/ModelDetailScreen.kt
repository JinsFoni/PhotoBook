package dev.jinsfoni.photobook.ui.screens.modeldetail

import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import dev.jinsfoni.photobook.R
import androidx.compose.foundation.border
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
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.components.FavoriteButton
import dev.jinsfoni.photobook.ui.components.CollectionCard
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.BackIcon
import dev.jinsfoni.photobook.ui.icons.IconWidths
import dev.jinsfoni.photobook.ui.icons.StrokeIcon

/**
 * S6 模特详情:顶部 2:3 hero(沉浸 + 渐隐纱 + 返回)→ 刊头(名/stage/bio/meta)
 * → 「写真 N」2 列卡。跟随全局主题。
 */
@Composable
fun ModelDetailScreen(
    slug: String,
    onBack: () -> Unit,
    onOpenCollection: (String) -> Unit,
    vm: ModelDetailViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()

    LaunchedEffect(Unit) { vm.load(slug) }

    Box(Modifier.fillMaxSize()) {
        // 虚化主题垫底:模特 hero(设计稿 s6 用 cover-1.jpg 同源做法)
        BlurBackdrop(state.detail?.heroUrl)
    when {
        state.loading -> DetailSkeleton()
        state.detail != null -> ModelDetailContent(
            state = state,
            onBack = onBack,
            onToggleFavorite = vm::toggleFavorite,
            onOpenCollection = onOpenCollection,
        )
        else -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                EmptyState(message = state.error ?: "加载失败")
                Spacer(Modifier.height(12.dp))
                Text(
                    stringResource(R.string.retry),
                    style = PhotoType.caption,
                    color = colors.accent,
                    modifier = Modifier.photoClickable { vm.load(slug) }.padding(8.dp),
                )
            }
        }
    }
    }
}

@Composable
private fun ModelDetailContent(
    state: ModelDetailUiState,
    onBack: () -> Unit,
    onToggleFavorite: () -> Unit,
    onOpenCollection: (String) -> Unit,
) {
    val d = state.detail!!
    val colors = LocalPhotoColors.current
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        // 转场时新旧两页同屏叠加,页面根布局必须不透明,否则滑动时缝隙里透出下层页
        modifier = Modifier.fillMaxSize().background(colors.paper),
        contentPadding = PaddingValues(bottom = 48.dp),
        horizontalArrangement = Arrangement.spacedBy(13.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        // hero:跨两列,2:3 大图(高度约 0.66× 屏宽×2 …实际占满宽,高=宽×1.5)
        item(span = { GridItemSpan(2) }) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .aspectRatio(390f / 500f),
            ) {
                AsyncImage(
                    model = d.heroUrl,
                    contentDescription = d.name,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
                // 底部渐隐纱 → 融入 paper
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                0f to Color(0, 0, 0, 60),
                                0.55f to Color(0, 0, 0, 0),
                                1f to colors.paper,
                            )
                        ),
                )
                // 返回钮(白字,沉浸区)+ 右上收藏心(模特段 S7 唯一入口)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .statusBarsPadding()
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Box(
                        Modifier
                            .photoClickable(onBack)
                            .padding(8.dp),
                    ) {
                        StrokeIcon(BackIcon, size = 22.dp, tint = Color.White, strokeWidth = IconWidths.THIN)
                    }
                    Box(
                        Modifier
                            .background(Color.Black.copy(alpha = 0.28f), RoundedCornerShape(999.dp))
                            .padding(6.dp),
                    ) {
                        FavoriteButton(
                            isFavorite = state.faved,
                            onToggle = onToggleFavorite,
                        )
                    }
                }
                // 名字压图
                Column(
                    Modifier
                        .align(Alignment.BottomStart)
                        .padding(horizontal = 18.dp),
                ) {
                    if (d.stage.isNotBlank()) {
                        Text(
                            d.stage,
                            style = PhotoType.tag.copy(letterSpacing = 2.5.sp),
                            color = Color.White.copy(alpha = 0.69f),
                        )
                    }
                    Text(
                        d.name,
                        style = PhotoType.heroTitle,
                        color = Color.White,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
        }
        // 刊头:bio + meta(标签行)
        item(span = { GridItemSpan(2) }) {
            Column(Modifier.padding(horizontal = 18.dp)) {
                if (d.bio.isNotBlank()) {
                    Text(
                        d.bio,
                        style = PhotoType.caption.copy(fontSize = 15.sp, lineHeight = 23.sp),
                        color = colors.ink2,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                }
                val meta = listOf(d.agency, d.height, d.measurements).filter { it.isNotBlank() }
                if (meta.isNotEmpty()) {
                    Text(
                        meta.joinToString(" · "),
                        style = PhotoType.caption,
                        color = colors.ink3,
                        modifier = Modifier.padding(top = 10.dp),
                    )
                }
                if (d.tags.isNotEmpty()) {
                    androidx.compose.foundation.layout.FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(7.dp),
                        modifier = Modifier.padding(top = 12.dp),
                    ) {
                        d.tags.forEach { tag ->
                            Box(
                                Modifier
                                    .border(0.7.dp, colors.line2, RoundedCornerShape(999.dp))
                                    .padding(horizontal = 11.dp, vertical = 5.dp),
                            ) {
                                Text("#$tag", style = PhotoType.micro, color = colors.ink2)
                            }
                        }
                    }
                }
            }
        }
        // 「写真 N」标题
        item(span = { GridItemSpan(2) }) {
            dev.jinsfoni.photobook.ui.components.SectionHeader(
                title = "写真 ${d.count}",
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        }
        if (d.collections.isEmpty()) {
            item(span = { GridItemSpan(2) }) {
                Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                    EmptyState(message = stringResource(R.string.empty_collections))
                }
            }
        }
        // 卡片随列贴边加 18dp 页边距(与收藏/写真集一致);不能挂到 grid contentPadding 上——
        // hero 跨两列要全出血,会一起被内缩。i%2 即列号,Fixed(2) 逐行铺位恒成立。
        items(d.collections.size) { i ->
            val c = d.collections[i]
            CollectionCard(
                title = c.title,
                subtitle = "${c.modelName} · ${c.count} 张",
                imageUrl = c.imageUrl,
                onClick = { onOpenCollection(c.slug) },
                modifier = Modifier.padding(
                    start = if (i % 2 == 0) 18.dp else 0.dp,
                    end = if (i % 2 == 1) 18.dp else 0.dp,
                ),
            )
        }
    }
}

@Composable
private fun DetailSkeleton() {
    Column(Modifier.fillMaxSize()) {
        SkeletonBox(
            Modifier
                .fillMaxWidth()
                .aspectRatio(390f / 500f)
                .statusBarsPadding(),
            cornerRadius = 0,
        )
        Row(Modifier.padding(horizontal = 18.dp, vertical = 15.dp), horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
    }
}
