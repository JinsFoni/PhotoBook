package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.clickable
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import me.saket.telephoto.zoomable.coil3.ZoomableAsyncImage
import me.saket.telephoto.zoomable.rememberZoomableImageState
import dev.jinsfoni.photobook.ui.icons.DownloadIcon
import dev.jinsfoni.photobook.ui.icons.HeartIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import dev.jinsfoni.photobook.ui.models.PhotoItem
import kotlinx.coroutines.delay

/**
 * S4 灯箱:全出血黑屏、HorizontalPager 翻页、单击 chrome 显隐(6s 自动隐)、
 * 顶部轻纱+页码+返回、底部轻纱+收藏/下载(DownloadManager)。
 */
@Composable
fun LightboxScreen(
    slug: String,
    initialIdx: Int,
    onBack: () -> Unit,
    vm: LightboxViewModel = hiltViewModel(),
    downloader: PhotoDownloader,
) {
    val state by vm.state.collectAsState()
    LaunchedEffect(slug) { vm.load(slug) }

    val detail = state.detail
    Box(Modifier.fillMaxSize().background(Color(8, 9, 10))) {
        if (detail == null) {
            if (state.error != null) {
                Text(
                    state.error ?: "",
                    color = Color.White.copy(alpha = 0.7f),
                    style = dev.jinsfoni.photobook.core.design.PhotoType.caption,
                    modifier = Modifier.align(Alignment.Center),
                )
            }
            return@Box
        }

        val photos = detail.photos
        val pagerState = rememberPagerState(
            initialPage = initialIdx.coerceIn(0, (photos.size - 1).coerceAtLeast(0)),
        ) { photos.size }

        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
            PhotoPage(photos[page])
        }

        var chromeVisible by remember { mutableStateOf(true) }
        LaunchedEffect(pagerState.currentPage, chromeVisible) {
            if (chromeVisible) {
                delay(6000)   // 原型 600ms → 实机 6s 更合理(记录偏差)
                chromeVisible = false
            }
        }
        val chromeAlpha by animateFloatAsState(
            targetValue = if (chromeVisible) 1f else 0f,
            animationSpec = tween(180),
            label = "chrome",
        )

        Box(
            Modifier
                .fillMaxSize()
                .pointerInput(Unit) {
                    detectTapGestures(onTap = { chromeVisible = !chromeVisible })
                },
        )

        AnimatedVisibility(
            visible = chromeVisible,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
            modifier = Modifier.align(Alignment.TopCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(92.dp)
                    .background(
                        Brush.verticalGradient(0f to Color(8, 9, 10, 128), 1f to Color(8, 9, 10, 0))
                    ),
            ) {
                Text(
                    "←",
                    color = Color(0xFFF7F7F5),
                    style = dev.jinsfoni.photobook.core.design.PhotoType.byline,
                    modifier = Modifier
                        .align(Alignment.CenterStart)
                        .statusBarsPadding()
                        .clickableNoRipple { onBack() }
                        .padding(start = 8.dp, top = 8.dp, bottom = 8.dp, end = 8.dp),
                )
                Text(
                    "${pagerState.currentPage + 1} / ${photos.size}",
                    color = Color(0xFFF7F7F5),
                    style = dev.jinsfoni.photobook.core.design.PhotoType.caption
                        .copy(letterSpacing = 1.sp),
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .align(Alignment.Center)
                        .statusBarsPadding(),
                )
            }
        }

        AnimatedVisibility(
            visible = chromeVisible,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(110.dp)
                    .background(
                        Brush.verticalGradient(0f to Color(8, 9, 10, 0), 1f to Color(8, 9, 10, 132))
                    ),
            ) {
                val cur = photos.getOrNull(pagerState.currentPage)
                Row(
                    horizontalArrangement = Arrangement.spacedBy(56.dp),
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(bottom = 20.dp),
                ) {
                    if (cur != null) {
                        val key = "${detail.slug}#${cur.idx}"
                        val faved = vm.isPhotoFaved(key)
                        StrokeIcon(
                            HeartIcon,
                            size = 24.dp,
                            tint = if (faved) Color(0xFFE0455A) else Color(0xFFF7F7F5),
                            filled = faved,
                            modifier = Modifier.clickableNoRipple { vm.togglePhotoFavorite(key) },
                        )
                        StrokeIcon(
                            DownloadIcon,
                            size = 24.dp,
                            tint = Color(0xFFF7F7F5),
                            modifier = Modifier.clickableNoRipple {
                                downloader.download(cur.fullUrl, "PhotoBook-${detail.slug}-${cur.idx}.jpg")
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun PhotoPage(photo: PhotoItem) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        val zoomState = rememberZoomableImageState()
        ZoomableAsyncImage(
            model = photo.fullUrl,
            contentDescription = "Photo ${photo.idx + 1}",
            state = zoomState,
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize(),
        )
    }
}

/** 无涟漪 clickable(设计规范禁 Material 涟漪)。 */
private fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier = composed {
    clickable(
        interactionSource = remember { MutableInteractionSource() },
        indication = null,
        onClick = onClick,
    )
}
