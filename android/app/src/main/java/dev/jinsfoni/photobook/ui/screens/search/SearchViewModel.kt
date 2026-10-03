package dev.jinsfoni.photobook.ui.screens.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.SearchRepository
import dev.jinsfoni.photobook.ui.models.SearchResults
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SearchUiState(
    val q: String = "",
    val searching: Boolean = false,
    val results: SearchResults? = null,
    val error: String? = null,
    /** true = 一次都没搜过(显示引导)。 */
    val pristine: Boolean = true,
)

/** S10 搜索:300ms 防抖,空 query 清结果。 */
@OptIn(FlowPreview::class)
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val repo: SearchRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()

    private var job: Job? = null

    fun onQueryChange(q: String) {
        _state.value = _state.value.copy(q = q)
        job?.cancel()
        if (q.isBlank()) {
            _state.value = _state.value.copy(searching = false, results = null, error = null, pristine = true)
            return
        }
        job = viewModelScope.launch {
            delay(300)
            doSearch(q)
        }
    }

    fun retry() {
        val q = _state.value.q
        if (q.isNotBlank()) {
            job?.cancel()
            job = viewModelScope.launch { doSearch(q) }
        }
    }

    private suspend fun doSearch(q: String) {
        _state.value = _state.value.copy(searching = true, error = null, pristine = false)
        try {
            val results = repo.search(q)
            // 竞态守卫:响应回来时 query 已变 → 丢弃
            if (_state.value.q == q) {
                _state.value = _state.value.copy(searching = false, results = results)
            }
        } catch (e: ApiException) {
            if (_state.value.q == q) {
                _state.value = _state.value.copy(
                    searching = false,
                    error = when (e.code) {
                        ApiException.NETWORK -> "无法连接服务器"
                        else -> e.message.ifBlank { "搜索失败" }
                    },
                )
            }
        }
    }
}
