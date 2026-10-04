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
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.ModelCard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** 三段 Tab(原型 s7:照片/写真/模特,照片段默认选中)。 */
enum class FavTab { PHOTOS, COLLECTIONS, MODELS }

data class FavPhotoItem(
    val slug: String,
    val idx: Int,
    val thumbUrl: String,
    /** 服务端提供的原图宽高(缺失时按 2:3 竖版处理)。 */
    val aspect: Float = 2f / 3f,
)

data class FavoritesUiState(
    val tab: FavTab = FavTab.PHOTOS,
    val loading: Boolean = true,
    val models: List<ModelCard> = emptyList(),
    val collections: List<CollectionCard> = emptyList(),
    val photos: List<FavPhotoItem> = emptyList(),
    val error: String? = null,
) {
    fun countText(): String = when (tab) {
        FavTab.MODELS -> "${models.size} 位"
        FavTab.COLLECTIONS -> "${collections.size} 本"
        FavTab.PHOTOS -> "${photos.size} 张"
    }

    /** Tab 内联计数(原型 .seg .s .n):纯数字,选中态由 UI 变色。 */
    fun countFor(tab: FavTab): String = when (tab) {
        FavTab.MODELS -> models.size.toString()
        FavTab.COLLECTIONS -> collections.size.toString()
        FavTab.PHOTOS -> photos.size.toString()
 }

    fun isEmpty(): Boolean = when (tab) {
        FavTab.MODELS -> models.isEmpty()
        FavTab.COLLECTIONS -> collections.isEmpty()
        FavTab.PHOTOS -> photos.isEmpty()
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
            _state.value.photos.isEmpty()
        _state.value = _state.value.copy(loading = first, error = null)
        viewModelScope.launch {
            try {
                val dto = safeCall { api.favoritesResolve() }
                val base = session.currentBaseUrl()
                _state.value = FavoritesUiState(
                    tab = _state.value.tab,
                    loading = false,
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
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = when (e.code) {
                        ApiException.NETWORK -> "无法连接服务器"
                        else -> e.message.ifBlank { "加载失败" }
                    },
                )
            }
        }
    }
}
