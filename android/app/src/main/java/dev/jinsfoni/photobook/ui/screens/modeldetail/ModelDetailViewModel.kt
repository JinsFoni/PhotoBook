package dev.jinsfoni.photobook.ui.screens.modeldetail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.data.repo.ModelsRepository
import dev.jinsfoni.photobook.ui.models.ModelDetail
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ModelDetailUiState(
    val loading: Boolean = true,
    val detail: ModelDetail? = null,
    val error: String? = null,
    /** 模特收藏乐观态。 */
    val faved: Boolean = false,
)

@HiltViewModel
class ModelDetailViewModel @Inject constructor(
    private val repo: ModelsRepository,
    private val favorites: FavoritesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ModelDetailUiState())
    val state: StateFlow<ModelDetailUiState> = _state.asStateFlow()

    private var loadedSlug: String? = null

    fun load(slug: String) {
        if (slug.isBlank()) {
            _state.value = _state.value.copy(loading = false, error = "链接无效")
            return
        }
        if (slug == loadedSlug && _state.value.detail != null) return
        viewModelScope.launch {
            try {
                val detail = repo.detail(slug)
                loadedSlug = slug
                _state.value = ModelDetailUiState(loading = false, detail = detail)
                runCatching { favorites.refresh() }
                    .onSuccess { f -> _state.value = _state.value.copy(faved = f.contains("model", slug)) }
            } catch (e: ApiException) {
                _state.value = ModelDetailUiState(loading = false, error = friendly(e))
            }
        }
    }

    fun toggleFavorite() {
        val slug = loadedSlug ?: return
        val cur = _state.value.faved
        _state.value = _state.value.copy(faved = !cur)
        viewModelScope.launch {
            runCatching { favorites.toggle("model", slug, added = !cur) }
                .onSuccess { _state.value = _state.value.copy(faved = !cur) }
                .onFailure { _state.value = _state.value.copy(faved = cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
