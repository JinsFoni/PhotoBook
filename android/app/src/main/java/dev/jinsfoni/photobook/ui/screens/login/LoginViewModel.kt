package dev.jinsfoni.photobook.ui.screens.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.jinsfoni.photobook.data.prefs.SessionStore
import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiException
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.data.repo.AuthRepository
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    /** 首次使用(无任何服务器档案)或 S9 添加服务器:显示地址输入。 */
    val addServerMode: Boolean = false,
    /** 地址输入预填:首次用默认地址,添加服务器为空。 */
    val baseUrl: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

/** 登录成功一次性事件(触发导航回 S1 / 回设置页)。 */
sealed interface LoginEvent {
    data object Success : LoginEvent
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val auth: AuthRepository,
    private val session: SessionStoreApi,
) : ViewModel() {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    private val _events = MutableSharedFlow<LoginEvent>(extraBufferCapacity = 1)
    val events: SharedFlow<LoginEvent> = _events.asSharedFlow()

    init {
        // 无有效会话时登录页带地址输入:
        // - 首次使用(无任何档案): 预填默认地址,登录走 addServer 落档
        // - 已登出(401 强登出/手动登出清了 token 但档案还在): 预填该档案的
        //   地址(剥掉 API 前缀只显示 host)——否则登录页只剩用户名/密码,
        //   服务器地址变了(换 IP/端口/实例)时用户没有任何入口可改。
        // 避免"装好 app 只能连编译期写死的服务器"——地址由用户填,登录走 addServer 落档。
        viewModelScope.launch {
            val profiles = session.profiles.first()
            when {
                profiles.isEmpty() -> _state.value = _state.value.copy(
                    addServerMode = true,
                    baseUrl = SessionStore.DEFAULT_BASE_URL,
                )
                session.currentToken().isBlank() -> _state.value = _state.value.copy(
                    addServerMode = true,
                    baseUrl = SessionStore.displayUrl(
                        (profiles.firstOrNull { it.id == session.activeProfileId.first() }
                            ?: profiles.first()).baseUrl),
                )
            }
        }
    }

    fun onUsername(v: String) { _state.value = _state.value.copy(username = v, error = null) }
    fun onPassword(v: String) { _state.value = _state.value.copy(password = v, error = null) }
    fun onBaseUrl(v: String) { _state.value = _state.value.copy(baseUrl = v, error = null) }

    /** 进入 S9「添加服务器」模式(带地址输入)。 */
    fun startAddServer() {
        if (_state.value.addServerMode) return
        _state.value = _state.value.copy(addServerMode = true)
    }

    fun submit() {
        val s = _state.value
        if (s.loading) return
        if (s.addServerMode && s.baseUrl.isBlank()) {
            _state.value = s.copy(error = "请输入服务器地址")
            return
        }
        if (s.username.isBlank() || s.password.isBlank()) {
            _state.value = s.copy(error = "请输入用户名和密码")
            return
        }
        _state.value = s.copy(loading = true, error = null)
        viewModelScope.launch {
            try {
                if (s.addServerMode) {
                    auth.addServer(normalizeBaseUrl(s.baseUrl), s.username.trim(), s.password)
                } else {
                    auth.login(s.username.trim(), s.password)
                }
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

    /** 地址归一:补 scheme;统一落成仓库约定的 baseUrl 形态(含 /api/mobile/ 前缀)。 */
    private fun normalizeBaseUrl(raw: String): String {
        var v = raw.trim().trimEnd('/')
        if (!v.startsWith("http://") && !v.startsWith("https://")) v = "http://$v"
        if (!v.endsWith("/api/mobile")) v = "$v/api/mobile"
        return "$v/"
    }
}
