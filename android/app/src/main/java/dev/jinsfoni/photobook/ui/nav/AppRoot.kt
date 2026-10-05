package dev.jinsfoni.photobook.ui.nav

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.core.design.ThemeState
import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.ui.screens.MainShell
import dev.jinsfoni.photobook.ui.screens.detail.DetailScreen
import dev.jinsfoni.photobook.ui.screens.lightbox.LightboxScreen
import dev.jinsfoni.photobook.ui.screens.lightbox.PhotoDownloader
import dev.jinsfoni.photobook.ui.screens.login.LoginScreen
import dev.jinsfoni.photobook.ui.screens.modeldetail.ModelDetailScreen
import dev.jinsfoni.photobook.ui.screens.search.SearchScreen
import dev.jinsfoni.photobook.ui.screens.settings.SettingsScreen
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.rememberHazeState
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * M1 主链路导航:登录(未登录)→ 主壳(S1/S2,横滑)→ 详情(S3)→ 灯箱(S4)。
 * 登录态由 SessionStore.token 驱动;nav routes:shell / detail/{slug} / lightbox/{slug}/{idx}。
 */
@HiltViewModel
class AppRootViewModel @Inject constructor(
    private val session: SessionStoreApi,
) : ViewModel() {
    val loggedIn = session.token
        .map { !it.isNullOrBlank() }
        .stateIn(viewModelScope, SharingStarted.Eagerly, initialValue = null)

    /** 启动:把持久化主题/液态玻璃开关灌入 ThemeState(内存单例),变更写回。 */
    fun restoreTheme() {
        viewModelScope.launch {
            ThemeState.mode = session.theme.first()
            ThemeState.liquidGlass = session.liquidGlass.first()
        }
    }

    fun setTheme(mode: ThemeMode) {
        ThemeState.mode = mode
        viewModelScope.launch { session.saveTheme(mode) }
    }
}

@Composable
fun AppRoot(downloader: PhotoDownloader, vm: AppRootViewModel = hiltViewModel()) {
    val loggedIn by vm.loggedIn.collectAsState()
    val nav = rememberNavController()

    LaunchedEffect(Unit) { vm.restoreTheme() }

    when (loggedIn) {
        null -> Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color(8, 9, 10))) // 启动闪屏底色
        false -> LoginScreen(onLoggedIn = { /* token 落库 → loggedIn 翻 true 自动切壳 */ })
        true -> {
            // 页面切换语义:页面是"卡片",前进 = 新页整幅不透明自右滑入盖在旧页上(旧页不动);
            // 返回 = 当前页整幅向右滑出,露出下面原位的上一页。280ms 单曲线。
            // 两侧都不掺 fade:滑入掺 fadeIn 会半透明露底,滑出掺 fadeOut 会中途变花。
            NavHost(
                navController = nav,
                startDestination = "shell",
                enterTransition = {
                    slideInHorizontally(tween(280)) { it }
                },
                // 旧页保持原位:滑入的新页盖在上面,退出方不需要动(省一层重绘)
                exitTransition = { ExitTransition.KeepUntilTransitionsFinished },
                // 返回时上一页原地显现:不做任何动画,全程垫在滑出的页面下面
                popEnterTransition = { EnterTransition.None },
                popExitTransition = {
                    slideOutHorizontally(tween(280)) { it }
                },
                // targetSdk 37 手势返回默认走 predictive back,NavHost 用 predictivePop* 转场
                // (系统默认 scaleOut+fadeIn)而完全绕过上面的 popExit——必须覆写成同款右滑,
                // 手势预览和提交才都是"当前页右滑出、上一页原地不动"。
                // 注:lambda 参数必须显式标 _:Int,用 { _, _ -> } 会让 NavHost 重载解析整体失败
                predictivePopEnterTransition = { _: Int -> EnterTransition.None },
                predictivePopExitTransition = { _: Int -> slideOutHorizontally(tween(280)) { it } },
            ) {
            composable("shell") {
                val hazeState = rememberHazeState()
                MainShell(
                    hazeState = hazeState,
                    onOpenSettings = { nav.navigate("settings") },
                    onOpenCollection = { slug -> nav.navigate("detail/$slug") },
                    onOpenModel = { slug -> nav.navigate("model/$slug") },
                    onOpenPhoto = { slug, idx -> nav.navigate("lightbox/$slug/$idx") },
                    onOpenSearch = { nav.navigate("search") },
                )
            }
            composable(
                "model/{slug}",
                arguments = listOf(navArgument("slug") { }),
            ) { entry ->
                val slug = entry.arguments?.getString("slug").orEmpty()
                ModelDetailScreen(
                    slug = slug,
                    onBack = { nav.popBackStack() },
                    onOpenCollection = { s -> nav.navigate("detail/$s") },
                )            }
            composable("settings") {
                SettingsScreen(
                    onBack = { nav.popBackStack() },
                    onAddServer = { nav.navigate("login?add=1") },
                    onLoggedOut = {
                        nav.navigate("login") { popUpTo("shell") { inclusive = true } }
                    },
                )
            }
            composable(
                "login?add={add}",
                arguments = listOf(navArgument("add") { defaultValue = "0" }),
            ) { entry ->
                LoginScreen(
                    onLoggedIn = { /* token 落库 → loggedIn 翻 true 自动切壳 */ },
                    onBack = { nav.popBackStack() },
                    startInAddServerMode = entry.arguments?.getString("add") == "1",
                )
            }
            composable("search") {
                SearchScreen(
                    onBack = { nav.popBackStack() },
                    onOpenModel = { slug -> nav.navigate("model/$slug") },
                    onOpenCollection = { slug -> nav.navigate("detail/$slug") },
                    onOpenTag = { tag ->
                        // 标签点回 S2 列表:清搜索栈到 shell(简化:直接返回上一层)
                        nav.popBackStack()
                    },
                )
            }
            composable(
                "detail/{slug}",
                arguments = listOf(navArgument("slug") { }),
            ) { entry ->
                val slug = entry.arguments?.getString("slug").orEmpty()
                DetailScreen(
                    slug = slug,
                    onBack = { nav.popBackStack() },
                    onOpenPhoto = { s, idx -> nav.navigate("lightbox/$s/$idx") },
                )
            }
            // 灯箱是"浮层"语义:退出动画由 LightboxScreen 屏内自编排(黑底/chrome 先撤,
            // 只留图片溶解)。pop 用 340ms "隐形"淡出占位:让本页在导航过渡期间保持挂载
            // 340ms(屏内两段动画 120+240-20 错峰的总窗),几乎不变的 1→0.999 曲线
            // 保证可见效果全部由屏内编排驱动,页面不会提前被清场
            composable(
                "lightbox/{slug}/{idx}",
                arguments = listOf(navArgument("slug") { }, navArgument("idx") { }),
                enterTransition = { fadeIn(tween(200)) },
                exitTransition = { ExitTransition.KeepUntilTransitionsFinished },
                popEnterTransition = { EnterTransition.None },
                popExitTransition = { fadeOut(tween(340), targetAlpha = 0.999f) },
            ) { entry ->
                val slug = entry.arguments?.getString("slug").orEmpty()
                val idx = entry.arguments?.getString("idx")?.toIntOrNull() ?: 0
                LightboxScreen(
                    slug = slug,
                    initialIdx = idx,
                    onBack = { nav.popBackStack() },
                    downloader = downloader,
                )
            }
        }
    }
}
}