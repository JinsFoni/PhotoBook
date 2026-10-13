package dev.jinsfoni.photobook.ui.screens.favorites

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.MediaUrls
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.data.remote.dto.CollectionCardDto
import dev.jinsfoni.photobook.data.remote.dto.ModelDto
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.data.repo.toModel
import dev.jinsfoni.photobook.data.repo.toCard
import dev.jinsfoni.photobook.data.repo.toVideoCard
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.ModelCard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** 五段 Tab(写真视频两个 tab 与写真平行,追加在最右)。 */
enum class FavTab { COLLECTIONS, MODELS, PHOTOS, VIDEO_ALBUMS, VIDEOS }

data class FavPhotoItem(
    val slug: String,
    val idx: Int,
    val thumbUrl: String,
    /** 服务端提供的原图宽高(缺失时按 2:3 竖版处理)。 */
    val aspect: Float = 2f / 3f,
)

/** 收藏的单条视频:thumbUrl 为封面帧(ffmpeg 缺失时为空 → 播放器黑屏兜底)。 */
data class FavVideoItem(
    val slug: String,
    val idx: Int,
    val posterUrl: String?,
    val aspect: Float = 16f / 9f,
)

data class FavoritesUiState(
    val tab: FavTab = FavTab.COLLECTIONS,
    val loading: Boolean = true,
    val refreshing: Boolean = false,   // 下拉刷新指示器(已有数据时的刷新;与 loading 互斥)
    val models: List<ModelCard> = emptyList(),
    val collections: List<CollectionCard> = emptyList(),
    val photos: List<FavPhotoItem> = emptyList(),
    val videoAlbums: List<CollectionCard> = emptyList(),
    val videos: List<FavVideoItem> = emptyList(),
    val error: String? = null,
) {
    fun countText(): String = when (tab) {
        FavTab.MODELS -> "${models.size} 位"
        FavTab.COLLECTIONS -> "${collections.size} 本"
        FavTab.PHOTOS -> "${photos.size} 张"
        FavTab.VIDEO_ALBUMS -> "${videoAlbums.size} 部"
        FavTab.VIDEOS -> "${videos.size} 段"
    }

    /** Tab 内联计数(原型 .seg .s .n):纯数字,选中态由 UI 变色。 */
    fun countFor(tab: FavTab): String = when (tab) {
        FavTab.MODELS -> models.size.toString()
        FavTab.COLLECTIONS -> collections.size.toString()
        FavTab.PHOTOS -> photos.size.toString()
        FavTab.VIDEO_ALBUMS -> videoAlbums.size.toString()
        FavTab.VIDEOS -> videos.size.toString()
    }

    fun isEmpty(): Boolean = when (tab) {
        FavTab.MODELS -> models.isEmpty()
        FavTab.COLLECTIONS -> collections.isEmpty()
        FavTab.PHOTOS -> photos.isEmpty()
        FavTab.VIDEO_ALBUMS -> videoAlbums.isEmpty()
        FavTab.VIDEOS -> videos.isEmpty()
    }
}

/**
 * 收藏页 VM:GET /favorites/resolve 一次拿三段实体(服务端反查,免客户端拼凑);
 * 之后详情/灯箱的乐观 toggle 会实时反映(favorites 流同一事实源)。
 */
@HiltViewModel
class FavoritesViewModel @Inject constructor(
    private val favoritesRepo: FavoritesRepository,
    private val api: MobileApi,
    private val session: SessionStoreApi,
) : ViewModel() {

    private val _state = MutableStateFlow(FavoritesUiState())
    val state: StateFlow<FavoritesUiState> = _state.asStateFlow()

    val favorites = favoritesRepo.state

    fun selectTab(tab: FavTab) {
        _state.value = _state.value.copy(tab = tab)
    }

    fun refresh() {
        val first = _state.value.models.isEmpty() && _state.value.collections.isEmpty() &&
            _state.value.photos.isEmpty() && _state.value.videoAlbums.isEmpty() &&
            _state.value.videos.isEmpty()
        _state.value = _state.value.copy(loading = first, refreshing = !first, error = null)
        viewModelScope.launch {
            try {
                val dto = safeCall { api.favoritesResolve() }
                val base = session.currentBaseUrl()
                _state.value = FavoritesUiState(
                    tab = _state.value.tab,
                    loading = false,
                    refreshing = false,
                    models = dto.models.map { it.toCard(base) },
                    collections = dto.collections.map { it.toModel(base) },
                    photos = dto.photos.map { p ->
                        val w = p.w ?: 2
                        val h = p.h ?: 3
                        FavPhotoItem(
                            slug = p.slug,
                            idx = p.idx,
                            thumbUrl = MediaUrls.fromPrefixed(base, p.thumb ?: ""),
                            aspect = if (w > 0 && h > 0) w.toFloat() / h else 2f / 3f,
                        )
                    },
                    // 写真视频两段(与写真段平行)
                    videoAlbums = dto.videoAlbums.map { it.toVideoCard(base) },
                    videos = dto.videos.map { v ->
                        val w = v.w ?: 16
                        val h = v.h ?: 9
                        FavVideoItem(
                            slug = v.slug,
                            idx = v.idx,
                            posterUrl = v.thumb?.let { MediaUrls.fromPrefixed(base, it) },
                            aspect = if (w > 0 && h > 0) w.toFloat() / h else 16f / 9f,
                        )
                    },
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(
                    loading = false,
                    refreshing = false,
                    // 已有内容时下拉失败不打断现状,只收指示器;空态才显示错误
                    error = if (first) when (e.code) {
                        ApiException.NETWORK -> "无法连接服务器"
                        else -> e.message.ifBlank { "加载失败" }
                    } else null,
                )
            }
        }
    }
}
