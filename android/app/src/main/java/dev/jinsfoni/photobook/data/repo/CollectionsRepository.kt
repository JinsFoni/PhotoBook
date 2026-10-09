package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.ApiErrors
import dev.jinsfoni.photobook.data.remote.MediaUrls
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.dto.CollectionCardDto
import dev.jinsfoni.photobook.data.remote.dto.CollectionDto
import dev.jinsfoni.photobook.data.remote.dto.DiscoverDto
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.CollectionDetail
import dev.jinsfoni.photobook.ui.models.DiscoverFeed
import dev.jinsfoni.photobook.ui.models.Stats
import dev.jinsfoni.photobook.ui.models.TagCount
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 缓存目录提供者:隔离 android.content.Context(纯 JVM 单测给临时目录)。
 */
fun interface CacheDirProvider {
    fun cacheDir(): File
}

/** 生产实现:filesDir/cache(应用私有,随应用卸载清理;由 NetworkModule provide)。 */
class AppCacheDirProvider(private val dir: File) : CacheDirProvider {
    override fun cacheDir(): File = dir
}

/**
 * 发现/列表/详情 —— DTO → UI 模型映射;rel 路径在此用 baseUrl 拼全,
 * UI 层只拿绝对 URL。discover 结果两级缓存:内存(二次进入不闪骨架)+
 * 磁盘(按档案分文件的 DTO JSON,冷启动秒开;SWR 仍会后台 revalidate)。
 *
 * 磁盘落 DTO 原始 JSON 而非拼好绝对 URL 的 UI 模型:URL 随档案变,
 * DTO + baseUrl 映射这一步每次读缓存都重做,换服务器永不失效。
 */
@Singleton
class CollectionsRepository @Inject constructor(
    private val api: MobileApi,
    private val session: SessionStoreApi,
    private val cacheDirs: CacheDirProvider,
) {

    private var discoverCache: DiscoverFeed? = null

    /** 当前缓存(可能 null;SWR 决定是否需要后台 revalidate)。 */
    fun cached(): DiscoverFeed? = discoverCache

    /** 作废内存 feed 缓存(切服务器档案/登出时由 RepoCaches 调;磁盘缓存按档案隔离,不用删)。 */
    fun invalidate() {
        discoverCache = null
    }

    suspend fun discover(force: Boolean = false): DiscoverFeed {
        if (!force) {
            discoverCache?.let { return it }
            // 内存未命中 → 读磁盘冷缓存(同步IO放后台线程;文件小,几十 KB)
            diskDiscover()?.let { dto ->
                val feed = dto.toFeed(session.baseUrlSnapshot())
                discoverCache = feed
                return feed
            }
        }
        val dto = safeCall { api.discover() }
        persistDiscover(dto)
        val base = session.currentBaseUrl()
        return dto.toFeed(base).also { discoverCache = it }
    }

    private fun DiscoverDto.toFeed(base: String) = DiscoverFeed(
        featured = featured.map { it.toCard(base) },
        latest = latest.map { it.toCard(base) },
        models = models.map { m ->
            CollectionCard(
                slug = m.slug,
                title = m.name,
                modelName = m.stage,
                imageUrl = m.avatar?.let { MediaUrls.thumb(base, it, 900) },
                count = m.count,
                tags = m.tags,
            )
        },
        tags = tags.map { TagCount(it.name, it.collections, it.models) },
        stats = Stats(stats.collections, stats.models),
    )

    // ---- discover 磁盘缓存(按活动档案分文件)--------------------------------

    private fun discoverFile(): File =
        File(cacheDirs.cacheDir(), "discover_${session.activeProfileIdSnapshot() ?: "none"}.json")

    private suspend fun diskDiscover(): DiscoverDto? = withContext(Dispatchers.IO) {
        runCatching {
            val f = discoverFile()
            if (f.isFile) ApiErrors.json.decodeFromString<DiscoverDto>(f.readText()) else null
        }.getOrNull()   // 损坏/版本不兼容:当作无缓存,走网络重拉
    }

    private suspend fun persistDiscover(dto: DiscoverDto) = withContext(Dispatchers.IO) {
        runCatching {
            discoverFile().apply { parentFile?.mkdirs() }.writeText(ApiErrors.json.encodeToString(dto))
        }
    }

    suspend fun collections(
        tag: String? = null,
        page: Int = 1,
        pageSize: Int = 20,
        sort: String = "latest",
    ): Pair<List<CollectionCard>, Int> {
        val dto = safeCall { api.collections(tag, page, pageSize, sort) }
        val base = session.currentBaseUrl()
        return dto.items.map { it.toCard(base) } to dto.total    }

    suspend fun detail(slug: String): CollectionDetail {
        val dto = safeCall { api.collection(slug) }
        val base = session.currentBaseUrl()
        return CollectionDetail(
            slug = dto.slug,
            title = dto.title,
            date = dto.date,
            tags = dto.tags,
            count = dto.count,
            // 详情 payload 无 heroCoverThumb;coverThumb 已是 "t/900x/x.webp" 形式
            heroUrl = dto.coverThumb?.let { MediaUrls.fromPrefixed(base, it) }
                ?: dto.cover?.let { MediaUrls.original(base, it) },
            modelName = dto.model?.name ?: dto.model_name,
            modelSlug = dto.model?.slug ?: dto.model_slug,
            photos = dto.photos.map { p ->
                dev.jinsfoni.photobook.ui.models.PhotoItem(
                    idx = p.idx,
                    thumbUrl = MediaUrls.thumb(base, p.file, 900),
                    fullUrl = MediaUrls.original(base, p.file),
                    previewUrl = MediaUrls.thumbShortSide(base, p.file, 2400),
                    width = p.w,
                    height = p.h,
                )
            },
        )
    }

    private fun CollectionDto.toCard(base: String) = CollectionCard(
        slug = slug,
        title = title,
        modelName = model_name,
        // coverThumb 服务端已是 "t/900/x.webp" 前缀 rel,直拼即可(与 web 网格同档)
        imageUrl = coverThumb?.let { MediaUrls.fromPrefixed(base, it) },
        // hero 轮播全屏宽,900 缩略图拉伸会糊 → /t/s2400/ 短边档(同灯箱 previewUrl)
        heroUrl = cover?.let { MediaUrls.thumbShortSide(base, it, 2400) },
        count = count,
        tags = tags,
    )

    private fun CollectionCardDto.toCard(base: String) = CollectionCard(
        slug = slug,
        title = title,
        modelName = model_name,
        // S2 列表卡的 coverThumb 同为 "t/900/…webp" 前缀 rel,直拼(origin 根)
        imageUrl = coverThumb?.let { MediaUrls.fromPrefixed(base, it) },
        // hero 轮播全屏宽 → /t/s2400/ 短边档(同灯箱 previewUrl)
        heroUrl = cover?.let { MediaUrls.thumbShortSide(base, it, 2400) },
        count = count,
        tags = tags,
    )
}
