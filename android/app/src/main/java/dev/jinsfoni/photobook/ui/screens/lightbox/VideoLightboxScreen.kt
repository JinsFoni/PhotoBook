package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.rememberTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.PhotoType
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.icons.DownloadIcon
import dev.jinsfoni.photobook.ui.icons.HeartIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
import kotlinx.coroutines.delay

/**
 * 视频灯箱(写真视频模块,与 LightboxScreen 平行):
 * 全出血黑屏、HorizontalPager 翻页、chrome 6s 自动隐、底部收藏/下载。
 * 与图片灯箱的关键差异 —— 每页一个 ExoPlayer 实例,翻页即释放上一页播放器
 * (media3 官方 AndroidView+Player 生命周期模式);playWhenReady 恒 false:
 * 省流量,进度条拖动交给 PlayerView 原生控件(Range 服务端已支持)。
 */
@Composable
fun VideoLightboxScreen(
    slug: String,
    initialIdx: Int,
    onBack: () -> Unit,
    vm: VideoLightboxViewModel = hiltViewModel(),
    downloader: PhotoDownloader,
) {
    val state by vm.state.collectAsState()
    LaunchedEffect(slug) { vm.load(slug) }

    // 退出编排(与图片灯箱同款):黑底/chrome 先撤,视频层溶解
    val leaving = remember { androidx.compose.animation.core.MutableTransitionState(false) }
    val exitTransition = rememberTransition(leaving, label = "vlb-exit")
    val backdropAlpha by exitTransition.animateFloat(
        transitionSpec = { tween(durationMillis = 120) }, label = "backdrop",
    ) { if (it) 0f else 1f }
    val contentAlpha by exitTransition.animateFloat(
        transitionSpec = { tween(durationMillis = 240, delayMillis = 100) }, label = "content",
    ) { if (it) 0f else 1f }
    val onBackKey = {
        if (!leaving.currentState) {
            leaving.targetState = true
            onBack()
        }
        Unit
    }
    androidx.activity.compose.BackHandler(enabled = !leaving.currentState) { onBackKey() }

    val detail = state.detail
    val videos = detail?.videos ?: emptyList()
    val pagerState = rememberPagerState(initialPage = 0) { videos.size }
    LaunchedEffect(videos.size) {
        if (videos.isNotEmpty()) pagerState.scrollToPage(initialIdx.coerceIn(0, videos.size - 1))
    }

    val blurTheme = LocalThemeMode.current == ThemeMode.BLUR
    var backdropIdx by remember { mutableIntStateOf(-1) }
    LaunchedEffect(Unit) {
        androidx.compose.runtime.snapshotFlow { pagerState.targetPage }.collect { backdropIdx = it }
    }
    Box(Modifier.fillMaxSize()) {
        if (blurTheme) {
            Box(Modifier.fillMaxSize().graphicsLayerCompat(backdropAlpha)) {
                BlurBackdrop(videos.getOrNull(backdropIdx)?.posterUrl ?: detail?.heroUrl)
            }
        } else {
            Box(
                Modifier.fillMaxSize().background(
                    Color(8, 9, 10, (backdropAlpha * 255).toInt()),
                ),
            )
        }
        if (detail == null) {
            if (state.error != null) {
                Text(
                    state.error ?: "",
                    color = Color.White.copy(alpha = 0.7f),
                    style = PhotoType.caption,
                    modifier = Modifier.align(Alignment.Center),
                )
            }
            return@Box
        }

        var chromeVisible by remember { mutableStateOf(true) }
        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
            val v = videos[page]
            VideoPage(
                url = v.videoUrl,
                posterUrl = v.posterUrl,
                contentAlpha = contentAlpha,
                onToggleChrome = { chromeVisible = !chromeVisible },
            )
        }
        LaunchedEffect(pagerState.currentPage, chromeVisible) {
            if (chromeVisible) {
                delay(6000)
                chromeVisible = false
            }
        }

        AnimatedVisibility(
            visible = chromeVisible && !leaving.targetState,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
            modifier = Modifier.align(Alignment.TopCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(92.dp)
                    .pointerInput(Unit) { detectTapGestures { } }
                    .background(Brush.verticalGradient(0f to Color(8, 9, 10, 128), 1f to Color(8, 9, 10, 0))),
            ) {
                Text(
                    "←",
                    color = Color(0xFFF7F7F5),
                    style = PhotoType.byline,
                    modifier = Modifier
                        .align(Alignment.CenterStart)
                        .statusBarsPadding()
                        .clickableNoRipple { onBackKey() }
                        .padding(8.dp),
                )
                Text(
                    "${pagerState.currentPage + 1} / ${videos.size}",
                    color = Color(0xFFF7F7F5),
                    style = PhotoType.caption.copy(letterSpacing = 1.sp),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.align(Alignment.Center).statusBarsPadding(),
                )
            }
        }

        AnimatedVisibility(
            visible = chromeVisible && !leaving.targetState,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(110.dp)
                    .pointerInput(Unit) { detectTapGestures { } }
                    .background(Brush.verticalGradient(0f to Color(8, 9, 10, 0), 1f to Color(8, 9, 10, 132))),
            ) {
                val cur = videos.getOrNull(pagerState.currentPage)
                val favorites by vm.favoritesState.collectAsState()
                Row(
                    horizontalArrangement = Arrangement.spacedBy(56.dp),
                    modifier = Modifier.align(Alignment.Center).padding(bottom = 20.dp),
                ) {
                    if (cur != null) {
                        // video key 约定 "album_slug:v{idx}"(v 前缀与照片键区分)
                        val key = "${detail.slug}:v${cur.idx}"
                        val faved = favorites?.contains("video", key) ?: false
                        StrokeIcon(
                            HeartIcon,
                            size = 24.dp,
                            tint = if (faved) Color(0xFFE0455A) else Color(0xFFF7F7F5),
                            filled = faved,
                            modifier = Modifier
                                .clickableNoRipple { vm.toggleVideoFavorite(key) }
                                .padding(10.dp),
                        )
                        StrokeIcon(
                            DownloadIcon,
                            size = 24.dp,
                            tint = Color(0xFFF7F7F5),
                            modifier = Modifier
                                .clickableNoRipple { downloader.downloadVideo(cur.videoUrl, "PhotoBook-${detail.slug}-${cur.idx}.mp4") }
                                .padding(10.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * 单页视频:ExoPlayer + PlayerView(原生控件条,含进度/全屏/倍速)。
 * 播放器随页面组合创建、离开即释放 —— media3 官方推荐模式,翻页不会
 * 残留多个解码器。poster 由 PlayerView 自绘(封面帧 webp)。
 */
@Composable
private fun VideoPage(
    url: String,
    posterUrl: String?,
    contentAlpha: Float,
    onToggleChrome: () -> Unit,
) {
    val context = LocalContext.current
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        val player = remember(url) {
            ExoPlayer.Builder(context).build().apply {
                playWhenReady = false        // 省流量:用户主动点播放
                setMediaItem(MediaItem.fromUri(url))
                prepare()
            }
        }
        DisposableEffect(url) {
            onDispose { player.release() }
        }
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    this.player = player
                    useController = true
                    setShowNextButton(false)
                    setShowPreviousButton(false)
                    controllerAutoShow = true
                }
            },
            modifier = Modifier
                .fillMaxSize()
                .clickableNoRipple(onToggleChrome)
                .graphicsLayerCompat(contentAlpha),
        )
        // 封面帧垫底:播放器首帧就绪前不露黑屏(与 Web 端 poster 属性同语义)
        if (posterUrl != null) {
            coil3.compose.AsyncImage(
                model = posterUrl,
                contentDescription = null,
                contentScale = androidx.compose.ui.layout.ContentScale.Fit,
                modifier = Modifier.fillMaxSize().graphicsLayerCompat(contentAlpha),
            )
        }
    }
}

/** 退出编排的 alpha 透传(本文件两处:视频层与封面垫底;同图片灯箱 graphicsLayer 手法)。 */
private fun Modifier.graphicsLayerCompat(alpha: Float): Modifier = graphicsLayer { this.alpha = alpha }

/** 无涟漪 clickable(设计规范禁 Material 涟漪;同图片灯箱 clickableNoRipple)。 */
private fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier = composed {
    clickable(
        interactionSource = remember { MutableInteractionSource() },
        indication = null,
        onClick = onClick,
    )
}
