package dev.jinsfoni.photobook.ui.nav

import androidx.compose.animation.AnimatedContentScope
import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.ExperimentalSharedTransitionApi
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.animation.SharedTransitionScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf

/**
 * SharedTransitionLayout 的根 scope 需要在 NavHost 的 composable 内容里可取:
 * AppRoot 用 AppRootSharedScopeCarrier 把它带下来。
 */
@OptIn(ExperimentalSharedTransitionApi::class)
val LocalAppRootSharedScope = staticCompositionLocalOf<AppRootSharedScopeHolder?> { null }

@OptIn(ExperimentalSharedTransitionApi::class)
class AppRootSharedScopeHolder(val scope: SharedTransitionScope)

/**
 * 灯箱共享元素动画所需的两个 scope(由 AppRoot 的 SharedTransitionLayout + NavHost 提供):
 * - sharedScope:声明 sharedElement/sharedBounds 的根;
 * - navScope:当前 NavBackStackEntry 的 AnimatedContentScope(NavHost composable 的 receiver)。
 * 详情页缩略图与灯箱页各取这两个 scope 标记同一个 sharedKey,即可跨页飞行。
 */
@OptIn(ExperimentalSharedTransitionApi::class)
class SharedTransitionScopes(
    val sharedScope: SharedTransitionScope,
    val navScope: AnimatedContentScope,
)

@OptIn(ExperimentalSharedTransitionApi::class)
val LocalSharedScopes = staticCompositionLocalOf<SharedTransitionScopes?> { null }

/** 灯箱大图与来源缩略图约定的共享 key(双方用同一个 key 才能配对)。 */
fun photoSharedKey(slug: String, idx: Int) = "photo-$slug-$idx"

/**
 * NavHost destination 内容的包装:把 SharedTransitionLayout 的根 scope 和当前页面的
 * AnimatedContentScope 灌进 LocalSharedScopes,页面内部(缩略图/灯箱大图)自取。
 */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun androidx.compose.animation.AnimatedContentScope.WithSharedScopes(content: @Composable () -> Unit) {
    val appScope = LocalAppRootSharedScope.current ?: return
    CompositionLocalProvider(
        LocalSharedScopes provides SharedTransitionScopes(appScope.scope, this),
        content = content,
    )
}
