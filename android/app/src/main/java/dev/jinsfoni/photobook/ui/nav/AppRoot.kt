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
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
        true -> NavHost(
            navController = nav,
            startDestination = "shell",
            enterTransition = { fadeIn(tween(220)) },
            exitTransition = { fadeOut(tween(180)) },
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
            composable(
                "lightbox/{slug}/{idx}",
                arguments = listOf(navArgument("slug") { }, navArgument("idx") { }),
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
