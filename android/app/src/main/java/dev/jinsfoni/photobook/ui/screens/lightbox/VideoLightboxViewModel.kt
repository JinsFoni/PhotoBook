package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.ui.models.Favorites
import dev.jinsfoni.photobook.ui.models.VideoAlbumDetail
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VideoLightboxUiState(
    val loading: Boolean = true,
    val detail: VideoAlbumDetail? = null,
    val error: String? = null,
)

/**
 * 视频灯箱 VM:只负责按 album slug 拉一次专辑(含全部视频),
 * 收藏 toggle 直接走 FavoritesRepository(与图片灯箱同一事实源)。
 */
@HiltViewModel
class VideoLightboxViewModel @Inject constructor(
    private val repo: CollectionsRepository,
    private val favorites: FavoritesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(VideoLightboxUiState())
    val state: StateFlow<VideoLightboxUiState> = _state.asStateFlow()

    fun load(slug: String) {
        viewModelScope.launch {
            try {
                val detail = repo.videoDetail(slug)
                _state.value = VideoLightboxUiState(loading = false, detail = detail)
                runCatching { favorites.refresh() }
            } catch (e: ApiException) {
                _state.value = VideoLightboxUiState(loading = false, error = friendly(e))
            }
        }
    }

    val favoritesState: StateFlow<Favorites?> = favorites.state

    /** 底栏收藏(按 video key "slug:v{idx}"),乐观更新 + 失败回滚。 */
    fun toggleVideoFavorite(key: String) {
        viewModelScope.launch {
            val cur = favorites.peek()?.contains("video", key) ?: false
            runCatching { favorites.toggle("video", key, added = !cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
