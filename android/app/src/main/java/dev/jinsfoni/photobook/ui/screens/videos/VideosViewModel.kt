package dev.jinsfoni.photobook.ui.screens.videos

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

/** 视频专辑列表排序(与写真同四档;服务端 videos 端点同参)。 */
enum class VideoAlbumSort(val apiValue: String) {
    PUBLISHED_LATEST("latest"),
    PUBLISHED_OLDEST("oldest"),
    ADDED_LATEST("added_latest"),
    ADDED_OLDEST("added_oldest"),
}

data class VideosUiState(
    val loading: Boolean = true,
    val loadingMore: Boolean = false,
    val refreshing: Boolean = false,
    val items: List<CollectionCard> = emptyList(),
    val total: Int = 0,
    val tag: String? = null,
    val sort: VideoAlbumSort = VideoAlbumSort.PUBLISHED_LATEST,
    val error: String? = null,
    val endReached: Boolean = false,
) {
    val countText: String get() = "$total 部"
}

/**
 * 写真视频列表 VM:与 CollectionsViewModel 完全平行(分页/下拉/SWR 语义一致),
 * 只把 repo 调用换成 videos 端点 —— 视频是独立模块,列表互不影响。
 */
@HiltViewModel
class VideosViewModel @Inject constructor(
    private val repo: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(VideosUiState())
    val state: StateFlow<VideosUiState> = _state.asStateFlow()

    private var page = 0
    private val pageSize = 20

    fun start(tag: String?) {
        if (page > 0 || _state.value.items.isNotEmpty()) return
        _state.value = _state.value.copy(tag = tag)
        loadFirst()
    }

    fun setSort(sort: VideoAlbumSort) {
        if (sort == _state.value.sort) return
        _state.value = _state.value.copy(sort = sort)
        loadFirst()
    }

    fun retry() = loadFirst()

    fun refresh() {
        val s = _state.value
        if (s.refreshing || s.loading || s.items.isEmpty()) return
        _state.value = s.copy(refreshing = true, error = null)
        viewModelScope.launch {
            try {
                val st = _state.value
                val (items, total) = repo.videos(st.tag, 1, pageSize, st.sort.apiValue)
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
                val (items, total) = repo.videos(s.tag, 1, pageSize, s.sort.apiValue)
                _state.value = _state.value.copy(
                    loading = false, items = items, total = total,
                    endReached = items.size >= total,
                )
            } catch (e: ApiException) {
                _state.value = _state.value.copy(loading = false, error = friendly(e))
            }
        }
    }

    fun loadMore() {
        val s = _state.value
        if (s.loading || s.loadingMore || s.refreshing || s.endReached || s.error != null) return
        _state.value = s.copy(loadingMore = true)
        viewModelScope.launch {
            try {
                val next = page + 1
                val (items, total) = repo.videos(s.tag, next, pageSize, s.sort.apiValue)
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
