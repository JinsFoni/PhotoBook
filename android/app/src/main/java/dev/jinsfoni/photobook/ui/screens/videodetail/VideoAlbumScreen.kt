package dev.jinsfoni.photobook.ui.screens.videodetail

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
import androidx.compose.ui.graphics.Color
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
import dev.jinsfoni.photobook.ui.components.TagChip
import dev.jinsfoni.photobook.ui.components.arrangeTwoColumnWall
import dev.jinsfoni.photobook.ui.components.photoClickable
import dev.jinsfoni.photobook.ui.icons.HeartIcon
import dev.jinsfoni.photobook.ui.icons.PlayIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon

/**
 * 视频专辑详情(S3 平行):crumb + 衬线标题 + byline → 2 列瀑布视频瓦片。
 * 瓦片 = 封面帧(ffmpeg 缺失时为深色底)+ 左下时长胶囊 + 中央播放三角;
 * 点击进灯箱播放(路由由外层转成 lightbox/video/{slug}/{idx})。
 */
@Composable
fun VideoAlbumScreen(
    slug: String,
    onBack: () -> Unit,
    onOpenVideo: (slug: String, idx: Int) -> Unit,
    onOpenTag: (String) -> Unit = {},
    vm: VideoAlbumViewModel = hiltViewModel(),
) {
    val colors = LocalPhotoColors.current
    val state by vm.state.collectAsState()
    val gridState = rememberLazyStaggeredGridState()

    LaunchedEffect(slug) { vm.load(slug) }

    Box(Modifier.fillMaxSize().background(colors.paper)) {
        // 虚化主题垫底:专辑封面帧(无封面帧时退回空,与详情页 hero 同源)
        BlurBackdrop(state.detail?.heroUrl)
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "←",
                style = PhotoType.byline,
                color = colors.ink,
                modifier = Modifier.photoClickable(onBack).padding(8.dp),
            )
            Spacer(Modifier.weight(1f))
            StrokeIcon(
                HeartIcon,
                size = 22.dp,
                tint = if (state.faved) colors.accent else colors.ink2,
                filled = state.faved,
                modifier = Modifier.photoClickable(vm::toggleFavorite).padding(8.dp),
            )
        }

        when {
            state.loading -> VideoAlbumSkeleton()
            state.detail == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                EmptyState(message = state.error ?: "加载失败")
            }
            else -> {
                val d = state.detail!!
                val wall = remember(d.videos) {
                    val order = arrangeTwoColumnWall(d.videos.map { v ->
                        if ((v.width ?: 0) > 0 && (v.height ?: 0) > 0)
                            v.width!!.toFloat() / v.height!!.toFloat() else 0f
                    })
                    order.map { d.videos[it] }
                }
                LazyVerticalStaggeredGrid(
                    columns = StaggeredGridCells.Fixed(2),
                    state = gridState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 132.dp),
                    horizontalArrangement = Arrangement.spacedBy(11.dp),
                    verticalItemSpacing = 11.dp,
                ) {
                    item(span = StaggeredGridItemSpan.FullLine) {
                        Column(Modifier.padding(top = 4.dp, bottom = 18.dp)) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text("写真视频", style = PhotoType.tag, color = colors.ink3)
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
                                Text(d.modelName, style = PhotoType.bylineModel, color = colors.ink2)
                                Text("${d.count} 段", style = PhotoType.caption, color = colors.ink3)
                            }
                            if (d.tags.isNotEmpty()) {
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    modifier = Modifier.padding(top = 15.dp),
                                ) {
                                    d.tags.take(4).forEach { tag ->
                                        TagChip(
                                            label = "#$tag",
                                            selected = false,
                                            onClick = { onOpenTag(tag) },
                                        )
                                    }
                                }
                            }
                        }
                    }
                    if (wall.isEmpty()) {
                        item(span = StaggeredGridItemSpan.FullLine) {
                            Box(Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                                EmptyState(message = "这个视频专辑还没有视频文件")
                            }
                        }
                    }
                    // 瓦片:横视频跨整行,竖视频(含未知尺寸)两列成对
                    items(
                        count = wall.size,
                        span = { i ->
                            val v = wall[i]
                            if ((v.width ?: 0) > 0 && (v.height ?: 0) > 0 && v.width!! > v.height!!)
                                StaggeredGridItemSpan.FullLine
                            else StaggeredGridItemSpan.SingleLane
                        },
                    ) { i ->
                        val v = wall[i]
                        val landscape = (v.width ?: 0) > 0 && (v.height ?: 0) > 0 && v.width!! > v.height!!
                        val ratio = if (landscape) v.width!!.toFloat() / v.height!!.toFloat() else 2f / 3f
                        VideoTile(
                            posterUrl = v.posterUrl,
                            durationSec = v.durationSec,
                            ratio = ratio,
                            paper2 = colors.paper2,
                            onClick = { onOpenVideo(slug, v.idx) },
                        )
                    }
                }
            }
        }
    }
    }
}

/** 视频瓦片:封面帧 + 时长胶囊 + 中央播放三角(封面帧缺失 → 深色底兜底)。 */
@Composable
private fun VideoTile(
    posterUrl: String?,
    durationSec: Double?,
    ratio: Float,
    paper2: Color,
    onClick: () -> Unit,
) {
    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(ratio)
            .clip(RoundedCornerShape(2.dp))
            .background(paper2)
            .photoClickable(onClick),
    ) {
        if (posterUrl != null) {
            AsyncImage(
                model = posterUrl,
                contentDescription = "视频封面",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
        // 中央播放三角:常显(视频不像图片有 hover 态,触屏一律可见)
        Box(Modifier.align(Alignment.Center)) {
            StrokeIcon(
                PlayIcon,
                size = 30.dp,
                tint = Color.White.copy(alpha = 0.92f),
                strokeWidth = dev.jinsfoni.photobook.ui.icons.IconWidths.THIN,
                modifier = Modifier
                    .background(Color.Black.copy(alpha = 0.38f), androidx.compose.foundation.shape.CircleShape)
                    .padding(6.dp),
            )
        }
        // 左下时长胶囊 m:ss(服务端 duration 为秒,缺失时隐藏)
        val dur = durationSec
        if (dur != null && dur > 0) {
            val total = dur.toInt()
            Text(
                text = "${total / 60}:${"%02d".format(total % 60)}",
                style = PhotoType.micro.copy(
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Default,
                    fontFeatureSettings = "tnum",
                ),
                color = Color.White,
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .padding(6.dp)
                    .background(Color.Black.copy(alpha = 0.62f), RoundedCornerShape(3.dp))
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            )
        }
    }
}

@Composable
private fun VideoAlbumSkeleton() {
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
