package dev.jinsfoni.photobook.ui.screens.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.ui.models.CollectionCard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CollectionsUiState(
    val loading: Boolean = true,       // 首载骨架
    val loadingMore: Boolean = false,  // 追加页
    val refreshing: Boolean = false,   // 下拉刷新(带指示器;与 loading 互斥)
    val items: List<CollectionCard> = emptyList(),
    val total: Int = 0,
    val tag: String? = null,
    val sort: String = "latest",       // latest | oldest
    val error: String? = null,
    val endReached: Boolean = false,
) {
    val countText: String get() = "$total 张"
}

@HiltViewModel
class CollectionsViewModel @Inject constructor(
    private val repo: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(CollectionsUiState())
    val state: StateFlow<CollectionsUiState> = _state.asStateFlow()

    private var page = 0
    private val pageSize = 20

    /** 进入时带初始 tag(可为 null = 全部)。 */
    fun start(tag: String?) {
        if (page > 0 || _state.value.items.isNotEmpty()) return
        _state.value = _state.value.copy(tag = tag)
        loadFirst()
    }

    fun setTag(tag: String?) {
        if (tag == _state.value.tag) return
        _state.value = _state.value.copy(tag = tag)
        loadFirst()
    }

    fun toggleSort() {
        _state.value = _state.value.copy(sort = if (_state.value.sort == "latest") "oldest" else "latest")
        loadFirst()
    }

    fun retry() = loadFirst()

    /**
     * 下拉刷新:指示器 + 强制拉第一页。与 loadFirst 的区别是不清空已有
     * 列表(保滚动位置),失败也只收指示器、不顶掉现有内容。
     */
    fun refresh() {
        val s = _state.value
        if (s.refreshing || s.loading || s.items.isEmpty()) return
        _state.value = s.copy(refreshing = true, error = null)
        viewModelScope.launch {
            try {
                val st = _state.value
                val (items, total) = repo.collections(st.tag, 1, pageSize, st.sort)
                page = 1
                _state.value = _state.value.copy(
                    refreshing = false, items = items, total = total,
                    endReached = items.size >= total, error = null,
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(refreshing = false)
            }
        }
    }

    private fun loadFirst() {
        page = 1
        _state.value = _state.value.copy(loading = true, error = null, items = emptyList(), endReached = false)
        viewModelScope.launch {
            try {
                val s = _state.value
                val (items, total) = repo.collections(s.tag, 1, pageSize, s.sort)
                _state.value = _state.value.copy(
                    loading = false, items = items, total = total,
                    endReached = items.size >= total,
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(loading = false, error = friendly(e))
            }
        }
    }

    /** 滚动接近尾部时追加下一页。 */
    fun loadMore() {
        val s = _state.value
        if (s.loading || s.loadingMore || s.refreshing || s.endReached || s.error != null) return
        _state.value = s.copy(loadingMore = true)
        viewModelScope.launch {
            try {
                val next = page + 1
                val (items, total) = repo.collections(s.tag, next, pageSize, s.sort)
                page = next
                _state.value = _state.value.copy(
                    loadingMore = false,
                    items = _state.value.items + items,
                    total = total,
                    endReached = _state.value.items.size + items.size >= total || items.isEmpty(),
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(loadingMore = false, error = friendly(e))
            }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
