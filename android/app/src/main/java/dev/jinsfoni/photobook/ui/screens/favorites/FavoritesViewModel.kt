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

/** 三段 Tab(design.md S7:模特/写真/照片)。 */
enum class FavTab(val label: String) { MODELS("模特"), COLLECTIONS("写真"), PHOTOS("照片") }

data class FavPhotoItem(val slug: String, val idx: Int, val thumbUrl: String)

data class FavoritesUiState(
    val tab: FavTab = FavTab.COLLECTIONS,
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
                        FavPhotoItem(
                            slug = p.slug,
                            idx = p.idx,
                            thumbUrl = MediaUrls.fromPrefixed(base, p.thumb ?: ""),
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
