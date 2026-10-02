package dev.jinsfoni.photobook.ui.screens.explore

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.DiscoverFeed
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ExploreUiState(
    val loading: Boolean = true,      // 首载骨架屏
    val refreshing: Boolean = false,  // 下拉刷新
    val feed: DiscoverFeed? = null,
    val error: String? = null,
)

@HiltViewModel
class ExploreViewModel @Inject constructor(
    private val repo: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ExploreUiState())
    val state: StateFlow<ExploreUiState> = _state.asStateFlow()

    init { load(force = false) }

    /** 首载/重试:显示骨架屏。 */
    fun retry() = load(force = true, showSkeleton = true)

    fun refresh() {
        if (_state.value.refreshing) return
        _state.value = _state.value.copy(refreshing = true)
        viewModelScope.launch {
            try {
                repo.discover(force = true)
                _state.value = _state.value.copy(feed = repo.discover(), refreshing = false, error = null)
            } catch (e: ApiException) {
                _state.value = _state.value.copy(refreshing = false, error = friendly(e))
            }
        }
    }

    private fun load(force: Boolean, showSkeleton: Boolean = false) {
        viewModelScope.launch {
            if (showSkeleton) _state.value = _state.value.copy(loading = true, error = null)
            try {
                val feed = repo.discover(force)
                _state.value = ExploreUiState(loading = false, feed = feed)
            } catch (e: ApiException) {
                _state.value = ExploreUiState(loading = false, error = friendly(e), feed = _state.value.feed)
            }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器,下拉重试"
        else -> e.message.ifBlank { "加载失败" }
    }
}
