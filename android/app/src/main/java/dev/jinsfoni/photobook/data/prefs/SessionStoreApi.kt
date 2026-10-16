package dev.jinsfoni.photobook.data.prefs

import dev.jinsfoni.photobook.core.design.FontPack
import dev.jinsfoni.photobook.core.design.GlassMaterial
import dev.jinsfoni.photobook.core.design.ThemeMode
import kotlinx.coroutines.flow.Flow

/** 会话/服务器存储抽象(生产 = DataStore;单测 = 内存桩)。 */
interface SessionStoreApi {
    val token: Flow<String?>
    val username: Flow<String?>
    val baseUrl: Flow<String>

    /** 全部服务器档案(添加顺序)。 */
    val profiles: Flow<List<ServerProfile>>

    /** 活动档案 id(首个档案缺省)。 */
    val activeProfileId: Flow<String?>

    /** 主题三态(light/dark/blur)。 */
    val theme: Flow<ThemeMode>

    /** 底栏玻璃材质(三态,持久化;旧布尔键 liquid_glass 读取时迁移)。 */
    val glassMaterial: Flow<GlassMaterial>

    /** 灯箱加载原图开关(false = 2400px webp 预览图,省流量加载快)。 */
    val loadOriginal: Flow<Boolean>

    /** 语言标签("zh-CN"/"zh-TW";空 = 跟随系统)。 */
    val locale: Flow<String>

    /** 字体风格三选一(cute/minimal/modern,与 Web 端字体包对齐)。 */
    val fontPack: Flow<FontPack>

    suspend fun currentBaseUrl(): String

    /** 活动 baseUrl 的内存快照(拦截器每请求读取用,免 runBlocking 开销)。 */
    fun baseUrlSnapshot(): String

    /** 活动 token 的内存快照(空串 = 无 token;拦截器每请求读取用)。 */
    fun tokenSnapshot(): String

    /** 活动档案 id 的内存快照(null = 无档案;磁盘缓存分文件等同步读用)。 */
    fun activeProfileIdSnapshot(): String?

    /** 活动档案的 token(与 [token] 同源;无档案时空)。 */
    suspend fun currentToken(): String

    suspend fun saveSession(token: String, username: String)

    /** 服务端滑动续期:替换活动档案的 token(不涉及 username)。 */
    suspend fun renewToken(token: String)
    suspend fun clearSession()
    suspend fun saveBaseUrl(url: String)

    /** 登录成功后落新档案并激活(S9 添加服务器复用 S8)。 */
    suspend fun addProfile(baseUrl: String, token: String, username: String): ServerProfile

    /** 切换活动档案(token/会话随之切换)。 */
    suspend fun setActiveProfile(id: String)

    /** 删除档案;删活动档案时顺延到相邻档案(至少保留 0 个:删光=登出态)。 */
    suspend fun removeProfile(id: String)

    suspend fun saveTheme(mode: ThemeMode)
    suspend fun saveGlassMaterial(material: GlassMaterial)
    suspend fun saveLoadOriginal(enabled: Boolean)
    suspend fun saveLocale(tag: String)
    suspend fun saveFontPack(pack: FontPack)
}
