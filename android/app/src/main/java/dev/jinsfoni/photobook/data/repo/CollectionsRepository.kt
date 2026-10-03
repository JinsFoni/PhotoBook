package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MediaUrls
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.dto.CollectionCardDto
import dev.jinsfoni.photobook.data.remote.dto.CollectionDto
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.CollectionDetail
import dev.jinsfoni.photobook.ui.models.DiscoverFeed
import dev.jinsfoni.photobook.ui.models.Stats
import dev.jinsfoni.photobook.ui.models.TagCount
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 发现/列表/详情 —— DTO → UI 模型映射;rel 路径在此用 baseUrl 拼全,
 * UI 层只拿绝对 URL。discover 结果做内存缓存(S1 二次进入不闪骨架)。
 */
@Singleton
class CollectionsRepository @Inject constructor(
    private val api: MobileApi,
    private val session: SessionStoreApi,
) {

    private var discoverCache: DiscoverFeed? = null

    suspend fun discover(force: Boolean = false): DiscoverFeed {
        if (!force) discoverCache?.let { return it }
        val dto = safeCall { api.discover() }
        val base = session.currentBaseUrl()
        return DiscoverFeed(
            featured = dto.featured.map { it.toCard(base) },
            latest = dto.latest.map { it.toCard(base) },
            models = dto.models.map { m ->
                CollectionCard(
                    slug = m.slug,
                    title = m.name,
                    modelName = m.stage,
                    imageUrl = m.avatar?.let { MediaUrls.thumb(base, it, 600) },
                    count = m.count,
                    tags = m.tags,
                )
            },
            tags = dto.tags.map { TagCount(it.name, it.collections, it.models) },
            stats = Stats(dto.stats.collections, dto.stats.models),
        ).also { discoverCache = it }
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
                    thumbUrl = MediaUrls.thumb(base, p.file, 600),
                    fullUrl = MediaUrls.original(base, p.file),
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
        // coverThumb 服务端已是 "t/600x/x.webp" 前缀 rel,直拼即可
        imageUrl = coverThumb?.let { MediaUrls.fromPrefixed(base, it) },
        count = count,
        tags = tags,
    )

    private fun CollectionCardDto.toCard(base: String) = CollectionCard(
        slug = slug,
        title = title,
        modelName = model_name,
        imageUrl = coverThumb?.let { MediaUrls.thumb(base, it, 600) },
        count = count,
        tags = tags,
    )
}
