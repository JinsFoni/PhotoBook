package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.ui.models.CollectionDetail
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LightboxUiState(
    val loading: Boolean = true,
    val detail: CollectionDetail? = null,
    val error: String? = null,
    val faved: Boolean = false,
)

@HiltViewModel
class LightboxViewModel @Inject constructor(
    private val repo: CollectionsRepository,
    private val favorites: FavoritesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(LightboxUiState())
    val state: StateFlow<LightboxUiState> = _state.asStateFlow()

    private var slug: String? = null

    fun load(slug: String) {
        if (slug == this.slug && _state.value.detail != null) return
        viewModelScope.launch {
            try {
                val detail = repo.detail(slug)
                this@LightboxViewModel.slug = slug
                _state.value = LightboxUiState(loading = false, detail = detail)
                runCatching { favorites.refresh() }
                    .onSuccess { f -> _state.value = _state.value.copy(faved = f.contains("collection", slug)) }
            } catch (e: ApiException) {
                _state.value = LightboxUiState(loading = false, error = friendly(e))
            }
        }
    }

    /** 当前 photo key 的收藏态(peek 缓存;未刷新过 → false)。 */
    fun isPhotoFaved(key: String): Boolean = favorites.peek()?.contains("photo", key) ?: false

    /** 底栏收藏(按 photo key),乐观更新 + 失败回滚。 */
    fun togglePhotoFavorite(key: String) {
        val cur = isPhotoFaved(key)
        _state.value = _state.value.copy(faved = !cur)
        viewModelScope.launch {
            runCatching { favorites.toggle("photo", key, added = !cur) }
                .onSuccess { _state.value = _state.value.copy(faved = !cur) }
                .onFailure { _state.value = _state.value.copy(faved = cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
