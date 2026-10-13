package dev.jinsfoni.photobook.ui.screens.videodetail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.ui.models.VideoAlbumDetail
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VideoAlbumUiState(
    val loading: Boolean = true,
    val detail: VideoAlbumDetail? = null,
    val error: String? = null,
    /** 收藏乐观态(appbar 心形与底栏共用;type = video_album)。 */
    val faved: Boolean = false,
)

/**
 * 视频专辑详情 VM:与 DetailViewModel 平行 —— 同 SWR 语义、同乐观收藏,
 * 只是 repo 调用换成 videoDetail,收藏 type 换成 video_album。
 */
@HiltViewModel
class VideoAlbumViewModel @Inject constructor(
    private val repo: CollectionsRepository,
    private val favorites: FavoritesRepository,
    private val api: MobileApi,
) : ViewModel() {

    private val _state = MutableStateFlow(VideoAlbumUiState())
    val state: StateFlow<VideoAlbumUiState> = _state.asStateFlow()

    private var loadedSlug: String? = null

    fun load(slug: String) {
        if (slug.isBlank()) {
            _state.value = _state.value.copy(loading = false, error = "链接无效,请从列表重新进入")
            return
        }
        if (slug == loadedSlug && _state.value.detail != null) {
            viewModelScope.launch {
                try {
                    val fresh = repo.videoDetail(slug)
                    if (loadedSlug == slug) _state.value = _state.value.copy(detail = fresh)
                } catch (_: ApiException) {
                }
            }
            return
        }
        viewModelScope.launch {
            try {
                val detail = repo.videoDetail(slug)
                loadedSlug = slug
                _state.value = VideoAlbumUiState(loading = false, detail = detail)
                runCatching { favorites.refresh() }
                    .onSuccess { f -> _state.value = _state.value.copy(faved = f.contains("video_album", slug)) }
            } catch (e: ApiException) {
                _state.value = VideoAlbumUiState(loading = false, error = friendly(e))
            }
        }
    }

    fun toggleFavorite() {
        val slug = loadedSlug ?: return
        val cur = _state.value.faved
        _state.value = _state.value.copy(faved = !cur)
        viewModelScope.launch {
            runCatching { favorites.toggle("video_album", slug, added = !cur) }
                .onSuccess { _state.value = _state.value.copy(faved = !cur) }
                .onFailure { _state.value = _state.value.copy(faved = cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
