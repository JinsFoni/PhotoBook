package dev.jinsfoni.photobook.ui.screens.lightbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.CollectionsRepository
import dev.jinsfoni.photobook.data.repo.FavoritesRepository
import dev.jinsfoni.photobook.ui.models.CollectionDetail
import dev.jinsfoni.photobook.ui.models.Favorites
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LightboxUiState(
    val loading: Boolean = true,
    val detail: CollectionDetail? = null,
    val error: String? = null,
)

@HiltViewModel
class LightboxViewModel @Inject constructor(
    private val repo: CollectionsRepository,
    private val favorites: FavoritesRepository,
    session: SessionStoreApi,
) : ViewModel() {

    private val _state = MutableStateFlow(LightboxUiState())
    val state: StateFlow<LightboxUiState> = _state.asStateFlow()

    private var slug: String? = null

    /** 灯箱原图开关(设置页「查看大图 → 加载原图」;false = 2400px 预览图)。 */
    val loadOriginal: StateFlow<Boolean> = session.loadOriginal
        .stateIn(viewModelScope, SharingStarted.Eagerly, false)

    fun load(slug: String) {
        if (slug == this.slug && _state.value.detail != null) return
        viewModelScope.launch {
            try {
                val detail = repo.detail(slug)
                this@LightboxViewModel.slug = slug
                _state.value = LightboxUiState(loading = false, detail = detail)
                runCatching { favorites.refresh() }
            } catch (e: ApiException) {
                _state.value = LightboxUiState(loading = false, error = friendly(e))
            }
        }
    }

    /**
     * 收藏仓库状态流(可观察;null = 尚未拉取)。UI 按当前 photo key 从中
     * 派生红心态 —— 必须订阅流而非读一次性快照,否则 toggle 后没有状态
     * 变化驱动重组,红心看起来"点了没反应"。
     */
    val favoritesState: StateFlow<Favorites?> = favorites.state

    /** 底栏收藏(按 photo key),乐观更新 + 失败回滚都在仓库层。 */
    fun togglePhotoFavorite(key: String) {
        viewModelScope.launch {
            val cur = favorites.peek()?.contains("photo", key) ?: false
            runCatching { favorites.toggle("photo", key, added = !cur) }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
