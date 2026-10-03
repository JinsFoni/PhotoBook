package dev.jinsfoni.photobook.data.remote

/** 服务端错误(统一 {"error":{"code","message"}})或网络层失败,面向 UI 的单一异常。 */
class ApiException(
    val code: String,
    override val message: String,
    val httpStatus: Int? = null,
    cause: Throwable? = null,
) : Exception(message, cause) {

    val isAuth: Boolean get() = code == "unauthorized" || code == "invalid_credentials"
    val isNotFound: Boolean get() = code == "not_found"

    companion object {
        const val NETWORK = "network"
        const val SERVER = "server"
    }
}
