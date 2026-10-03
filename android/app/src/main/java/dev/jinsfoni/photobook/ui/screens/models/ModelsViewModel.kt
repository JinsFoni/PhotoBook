package dev.jinsfoni.photobook.ui.screens.models

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.ModelsRepository
import dev.jinsfoni.photobook.ui.models.ModelCard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ModelsUiState(
    val loading: Boolean = true,
    val items: List<ModelCard> = emptyList(),
    val error: String? = null,
)

/** S5 模特列表(featured 优先已由服务端排序;列表内存缓存防重复进入闪骨架)。 */
@HiltViewModel
class ModelsViewModel @Inject constructor(
    private val repo: ModelsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ModelsUiState())
    val state: StateFlow<ModelsUiState> = _state.asStateFlow()

    private var started = false

    fun start() {
        if (started && _state.value.items.isNotEmpty()) return
        started = true
        load()
    }

    fun retry() = load()

    private fun load() {
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            try {
                val items = repo.list()
                _state.value = ModelsUiState(loading = false, items = items)
            } catch (e: ApiException) {
                _state.value = ModelsUiState(loading = false, error = friendly(e))
            }
        }
    }

    private fun friendly(e: ApiException) = when (e.code) {
        ApiException.NETWORK -> "无法连接服务器"
        else -> e.message.ifBlank { "加载失败" }
    }
}
