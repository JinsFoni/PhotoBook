package dev.jinsfoni.photobook.ui.screens.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.ui.models.CollectionDetail
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class DetailUiState(
    val loading: Boolean = true,
    val detail: CollectionDetail? = null,
    val error: String? = null,
    /** 收藏乐观态(appbar 心形与底栏共用)。 */
    val faved: Boolean = false,
)

@HiltViewModel
class DetailViewModel @Inject constructor(
    private val repo: CollectionsRepository,
    private val favorites: FavoritesRepository,
    private val api: MobileApi,
) : ViewModel() {

    private val _state = MutableStateFlow(DetailUiState())
    val state: StateFlow<DetailUiState> = _state.asStateFlow()

    private var loadedSlug: String? = null

    fun load(slug: String) {
        if (slug.isBlank()) {
            // 空 slug 是路由误入:请求 GET collections/ 会被 307 重定向到列表接口,
            // 详情 DTO 解码列表 JSON 抛 MissingFieldException 直接崩 — 拦在入口
            _state.value = _state.value.copy(loading = false, error = "链接无效,请从列表重新进入")
            return
        }
        if (slug == loadedSlug && _state.value.detail != null) return
        viewModelScope.launch {
            try {
                val detail = repo.detail(slug)
                loadedSlug = slug
                _state.value = DetailUiState(loading = false, detail = detail)
                // 收藏态异步拉取(失败静默,乐观态兜底)
                runCatching { favorites.refresh() }
                    .onSuccess { f -> _state.value = _state.value.copy(faved = f.contains("collection", slug)) }
            } catch (e: ApiException) {
                _state.value = DetailUiState(loading = false, error = friendly(e))
            }
        }
    }

    /** 收藏切换:乐观更新,失败回滚。 */
    fun toggleFavorite() {
        val slug = loadedSlug ?: return
        val cur = _state.value.faved
        _state.value = _state.value.copy(faved = !cur)
        viewModelScope.launch {
            // toggle 成功 → after(=!cur 语义);失败回滚抛 ApiException → 恢复原态
            runCatching { favorites.toggle("collection", slug, added = !cur) }
                .onSuccess { _state.value = _state.value.copy(faved = !cur) }
                .onFailure { _state.value = _state.value.copy(faved = cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
