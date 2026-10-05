package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.rememberTransition
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import me.saket.telephoto.zoomable.coil3.ZoomableAsyncImage
import me.saket.telephoto.zoomable.rememberZoomableImageState
import dev.jinsfoni.photobook.core.design.LocalThemeMode
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.ui.components.BlurBackdrop
import dev.jinsfoni.photobook.ui.icons.DownloadIcon
import dev.jinsfoni.photobook.ui.icons.HeartIcon
import dev.jinsfoni.photobook.ui.icons.StrokeIcon
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
    val loadOriginal by vm.loadOriginal.collectAsState()
    LaunchedEffect(slug) { vm.load(slug) }

    // 退出编排(与导航 pop 并行):onBackKey 立刻 popBackStack,让详情页马上进组合垫在
    // 下面——否则黑底淡出后露出的是 NavHost 后面的深色底(黑洞),图片像在黑洞上溶解。
    // 导航层 popExit 为 KeepUntilTransitionsFinished,本页在过渡期间保持挂载:
    //   1) 黑底与 chrome 先撤(120ms);
    //   2) 只留图片本身溶解(240ms,错峰 100ms),完场时页面恰好随导航过渡移除。
    val leaving = remember { androidx.compose.animation.core.MutableTransitionState(false) }
    val exitTransition = rememberTransition(leaving, label = "lb-exit")
    val backdropAlpha by exitTransition.animateFloat(
        transitionSpec = { tween(durationMillis = 120) },
        label = "backdrop",
    ) { if (it) 0f else 1f }
    val imageAlpha by exitTransition.animateFloat(
        transitionSpec = { tween(durationMillis = 240, delayMillis = 100) },
        label = "image",
    ) { if (it) 0f else 1f }
    val onBackKey = {
        if (!leaving.currentState) {
            leaving.targetState = true
            onBack()
        }
        Unit
    }
    // 系统返回键/手势也要走上面的编排(否则只触发导航 pop,屏内动画全程不跑,
    // 图片会以全亮状态叠在黑底上直接消失)
    androidx.activity.compose.BackHandler(enabled = !leaving.currentState) { onBackKey() }

    val detail = state.detail

    // 虚化主题:黑底换成虚化垫底,与详情页同一张 hero 图——开合灯箱时两层背景
    // 完全一致,转场无缝;其他主题保持全出血纯黑。退出编排里虚化层随
    // backdropAlpha 淡出,图片本身仍走 imageAlpha 错峰溶解,分层不变。
    val blurTheme = LocalThemeMode.current == ThemeMode.BLUR
    Box(Modifier.fillMaxSize()) {
        if (blurTheme) {
            Box(Modifier.fillMaxSize().graphicsLayer { alpha = backdropAlpha }) {
                BlurBackdrop(state.detail?.heroUrl ?: state.detail?.photos?.firstOrNull()?.thumbUrl)
            }
        } else {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color(8, 9, 10, (backdropAlpha * 255).toInt()))
            )
        }
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

        var chromeVisible by remember { mutableStateOf(true) }

        val photos = detail.photos
        val pagerState = rememberPagerState(
            initialPage = initialIdx.coerceIn(0, (photos.size - 1).coerceAtLeast(0)),
        ) { photos.size }

        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
            // 设置开「加载原图」走 /media/ 原图,否则 2400px webp 预览
            val photo = photos[page]
            val url = if (loadOriginal) photo.fullUrl else photo.previewUrl
            PhotoPage(url, imageAlpha, onToggleChrome = { chromeVisible = !chromeVisible })
        }
        LaunchedEffect(pagerState.currentPage, chromeVisible) {
            if (chromeVisible) {
                delay(6000)   // 原型 600ms → 实机 6s 更合理(记录偏差)
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
                        .clickableNoRipple { onBackKey() }
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
            visible = chromeVisible && !leaving.targetState,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(180)),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(110.dp)
                    // 消费落空 tap:不透传给下面的图片(否则误触发 chrome 显隐)
                    .pointerInput(Unit) { detectTapGestures { } }
                    .background(
                        Brush.verticalGradient(0f to Color(8, 9, 10, 0), 1f to Color(8, 9, 10, 132))
                    ),
            ) {
                val cur = photos.getOrNull(pagerState.currentPage)
                // 收藏态订阅仓库流(可观察),点击后红心立即变色
                val favorites by vm.favoritesState.collectAsState()
                Row(
                    horizontalArrangement = Arrangement.spacedBy(56.dp),
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(bottom = 20.dp),
                ) {
                    if (cur != null) {
                        val key = "${detail.slug}:${cur.idx}"
                        val faved = favorites?.contains("photo", key) ?: false
                        StrokeIcon(
                            HeartIcon,
                            size = 24.dp,
                            tint = if (faved) Color(0xFFE0455A) else Color(0xFFF7F7F5),
                            filled = faved,
                            // 24dp 图标太小,补 10dp 命中区(44dp 目标)
                            modifier = Modifier
                                .clickableNoRipple { vm.togglePhotoFavorite(key) }
                                .padding(10.dp),
                        )
                        StrokeIcon(
                            DownloadIcon,
                            size = 24.dp,
                            tint = Color(0xFFF7F7F5),
                            modifier = Modifier
                                .clickableNoRipple {
                                    downloader.download(cur.fullUrl, "PhotoBook-${detail.slug}-${cur.idx}.jpg")
                                }
                                .padding(10.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun PhotoPage(url: String, imageAlpha: Float, onToggleChrome: () -> Unit) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        val zoomState = rememberZoomableImageState()
        ZoomableAsyncImage(
            model = url,
            contentDescription = "Photo",
            state = zoomState,
            contentScale = ContentScale.Fit,
            onClick = { onToggleChrome() },
            modifier = Modifier.fillMaxSize().graphicsLayer { alpha = imageAlpha },
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
