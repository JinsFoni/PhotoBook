package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.dto.FavoriteRequestDto
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.ui.models.Favorites
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 收藏:GET 结果缓存(离线可用);POST 乐观更新 —— 先改内存,失败回滚并
 * 把异常抛给调用侧(UI 层做一次性提示)。
 */
@Singleton
class FavoritesRepository @Inject constructor(
    private val api: MobileApi,
    @Suppress("unused") private val session: SessionStoreApi,
) {

    private var cache: Favorites? = null

    suspend fun refresh(): Favorites {
        val dto = safeCall { api.favorites() }
        return Favorites(dto.model, dto.collection, dto.photo).also { cache = it }
    }

    /** 当前态(可能未刷新过 → null)。 */
    fun peek(): Favorites? = cache

    /**
     * 乐观切换:本地立即生效;服务端失败时回滚并重抛。
     * @return 操作后的本地态
     */
    suspend fun toggle(type: String, key: String, added: Boolean): Favorites {
        val before = cache ?: Favorites()
        val after = before.toggled(type, key, added)
        cache = after
        return try {
            safeCall { api.toggleFavorite(FavoriteRequestDto(type, key, added)) }
            after
        } catch (e: ApiException) {
            cache = before
            throw e
        }
    }
}
