package dev.jinsfoni.photobook.ui.screens.detail

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.staggeredgrid.LazyVerticalStaggeredGrid
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridCells
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridItemSpan
import androidx.compose.foundation.lazy.staggeredgrid.rememberLazyStaggeredGridState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
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
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.components.EmptyState
import dev.jinsfoni.photobook.ui.components.SkeletonBox
import dev.jinsfoni.photobook.ui.components.arrangeTwoColumnWall
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.HeartIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import dev.jinsfoni.photobook.ui.nav.LocalSharedScopes
import dev.jinsfoni.photobook.ui.nav.photoSharedKey

/**
 * S3 详情:crumb + 衬线标题 + byline + TagRow → 2 列瀑布照片墙;
 * 底部玻璃条(收藏心形 + 页码,下载 M1 简化由 S4 承担)。
 */
@Composable
fun DetailScreen(
    slug: String,
    onBack: () -> Unit,
    onOpenPhoto: (slug: String, idx: Int) -> Unit,
    vm: DetailViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val gridState = rememberLazyStaggeredGridState()

    LaunchedEffect(slug) { vm.load(slug) }

    Box(Modifier.fillMaxSize()) {
        // 虚化主题垫底:本合集 hero(设计稿 s3 用 cover-5.jpg 同源做法)
        BlurBackdrop(state.detail?.heroUrl ?: state.detail?.photos?.firstOrNull()?.thumbUrl)
    Column(Modifier.fillMaxSize()) {
        // appbar(背景延伸式)
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 返回(← 用 CloseIcon 旋转太绕,直接文字符号,设计原型 back 为箭头)
            Text(
                "←",
                style = PhotoType.byline,
                color = colors.ink,
                modifier = Modifier
                    .photoClickable(onBack)
                    .padding(8.dp),
            )
            Spacer(Modifier.weight(1f))
            // 收藏心(appbar 侧,与底部同步乐观态)
            StrokeIcon(
                HeartIcon,
                size = 22.dp,
                tint = if (state.faved) colors.accent else colors.ink2,
                filled = state.faved,
                modifier = Modifier
                    .photoClickable(vm::toggleFavorite)
                    .padding(8.dp),
            )
        }

        when {
            state.loading -> DetailSkeleton()
            state.detail == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                EmptyState(message = state.error ?: "加载失败")
            }
            else -> {
                val d = state.detail!!
                // 照片墙重排:竖图成对填满两列,横图独占一行(共享实现见 PhotoWallLayout)
                val wall = remember(d.photos) {
                    val order = arrangeTwoColumnWall(d.photos.map { p ->
                        if (p.width > 0 && p.height > 0) p.width.toFloat() / p.height else 0f
                    })
                    order.map { d.photos[it] }
                }
                LazyVerticalStaggeredGrid(
                    columns = StaggeredGridCells.Fixed(2),
                    state = gridState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 132.dp),
                    horizontalArrangement = Arrangement.spacedBy(11.dp),
                    verticalItemSpacing = 11.dp,
                ) {
                    // 刊头(跨两列)
                    item(span = StaggeredGridItemSpan.FullLine) {
                        Column(Modifier.padding(top = 4.dp, bottom = 18.dp)) {
                            // crumb:写真集 · 模特 · 日期
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text("写真集", style = PhotoType.tag, color = colors.ink3)
                                Box(Modifier.size(3.dp).clip(RoundedCornerShape(50)).background(colors.line2))
                                Text(d.modelName, style = PhotoType.tag, color = colors.ink3)
                                Box(Modifier.size(3.dp).clip(RoundedCornerShape(50)).background(colors.line2))
                                Text(d.date, style = PhotoType.tag, color = colors.ink3)
                            }
                            Text(
                                d.title,
                                style = PhotoType.detailTitle,
                                color = colors.ink,
                                modifier = Modifier.padding(top = 13.dp),
                            )
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(11.dp),
                                modifier = Modifier.padding(top = 11.dp),
                            ) {
                                Text(d.modelName, style = PhotoType.byline, color = colors.ink2)
                                Text("${d.count} 张", style = PhotoType.caption, color = colors.ink3)
                            }
                            // TagRow
                            if (d.tags.isNotEmpty()) {
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    modifier = Modifier.padding(top = 15.dp),
                                ) {
                                    d.tags.take(4).forEach { tag ->
                                        dev.jinsfoni.photobook.ui.components.TagChip(
                                            label = "#$tag",
                                            selected = false,
                                            onClick = {},
                                        )
                                    }
                                }
                            }
                        }
                    }
                    // 照片墙:竖图统一 2:3,横图跨整行,wall 已重排补位
                    items(
                        count = wall.size,
                        span = { i ->
                            val p = wall[i]
                            if (p.width > 0 && p.height > 0 && p.width > p.height)
                                StaggeredGridItemSpan.FullLine
                            else StaggeredGridItemSpan.SingleLane
                        },
                    ) { i ->
                        val p = wall[i]
                        val landscape = p.width > 0 && p.height > 0 && p.width > p.height
                        val ratio = if (landscape) p.width.toFloat() / p.height.toFloat() else 2f / 3f
                        // 共享元素:缩略图与灯箱大图共用 key,进出大图时从卡片位置飞入/飞回
                        val scopes = LocalSharedScopes.current
                        val sharedModifier = if (scopes != null) {
                            with(scopes.sharedScope) {
                                Modifier.sharedElement(
                                    rememberSharedContentState(photoSharedKey(slug, p.idx)),
                                    animatedVisibilityScope = scopes.navScope,
                                )
                            }
                        } else Modifier
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .aspectRatio(ratio)
                                .clip(RoundedCornerShape(2.dp))
                                .background(colors.paper2)
                                .photoClickable { onOpenPhoto(slug, p.idx) },
                        ) {
                            AsyncImage(
                                model = p.thumbUrl,
                                contentDescription = "Photo ${p.idx + 1}",
                                contentScale = ContentScale.Crop,
                                modifier = sharedModifier.then(Modifier.fillMaxSize()),
                            )
                        }
                    }
                }
            }
        }
    }
    }
}

@Composable
private fun DetailSkeleton() {
    val colors = LocalPhotoColors.current
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        SkeletonBox(Modifier.fillMaxWidth().height(40.dp), cornerRadius = 2)
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(11.dp)) {
            SkeletonBox(Modifier.weight(1f))
            SkeletonBox(Modifier.weight(1f))
        }
    }
}
