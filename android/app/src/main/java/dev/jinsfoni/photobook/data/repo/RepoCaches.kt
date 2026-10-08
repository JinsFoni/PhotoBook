package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 进程级数据缓存的统一失效入口。
 *
 * discover/models/favorites 的缓存散在各自 @Singleton Repository 里,而
 * 「切换活动服务器档案」必须把它们全部作废(缓存的是旧服务器的 feed/收藏态),
 * 这里集中订阅 SessionStore.activeProfileId,变化即清理——UI 层无需逐处记得调。
 */
@Singleton
class RepoCaches @Inject constructor(
    session: SessionStoreApi,
    private val collections: CollectionsRepository,
    private val models: ModelsRepository,
    private val favorites: FavoritesRepository,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    init {
        // drop(1):启动读初始值不算切换;distinctUntilChanged:写回同值不抖动
        scope.launch {
            session.activeProfileId.drop(1).distinctUntilChanged().collect {
                invalidate()
            }
        }
    }

    /** 全部失效(切档案自动触发;登出/401 强登出也可显式调用)。 */
    fun invalidate() {
        collections.invalidate()
        models.clearCache()
        favorites.invalidate()
    }
}
