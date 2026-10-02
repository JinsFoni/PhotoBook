package dev.jinsfoni.photobook.ui.screens.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.repo.AuthRepository
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

/** 登录成功一次性事件(触发导航回 S1)。 */
sealed interface LoginEvent {
    data object Success : LoginEvent
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    private val _events = MutableSharedFlow<LoginEvent>(extraBufferCapacity = 1)
    val events: SharedFlow<LoginEvent> = _events.asSharedFlow()

    fun onUsername(v: String) { _state.value = _state.value.copy(username = v, error = null) }
    fun onPassword(v: String) { _state.value = _state.value.copy(password = v, error = null) }

    fun submit() {
        val s = _state.value
        if (s.loading) return
        // 输入校验(空值就地报错,不发请求)
        if (s.username.isBlank() || s.password.isBlank()) {
            _state.value = s.copy(error = "请输入用户名和密码")
            return
        }
        _state.value = s.copy(loading = true, error = null)
        viewModelScope.launch {
            try {
                auth.login(s.username.trim(), s.password)
                _state.value = _state.value.copy(loading = false)
                _events.emit(LoginEvent.Success)
            } catch (e: ApiException) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = when (e.code) {
                        "invalid_credentials" -> "用户名或密码错误"
                        ApiException.NETWORK -> "无法连接服务器"
                        else -> e.message.ifBlank { "登录失败" }
                    },
                )
            }
        }
    }
}
