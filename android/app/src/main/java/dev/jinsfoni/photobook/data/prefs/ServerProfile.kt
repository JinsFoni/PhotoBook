package dev.jinsfoni.photobook.data.prefs

import kotlinx.serialization.Serializable

/**
 * 服务器档案(S9 多服务器):每个自托管实例一条。
 * token 随档案存——切换档案即切换会话,互不覆盖。
 */
@Serializable
data class ServerProfile(
    val id: String,
    val baseUrl: String,
    val label: String = "",
    val username: String = "",
    val token: String = "",
)
