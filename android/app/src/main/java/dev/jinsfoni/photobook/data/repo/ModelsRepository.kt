package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MediaUrls
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.dto.CollectionCardDto
import dev.jinsfoni.photobook.data.remote.dto.ModelDetailDto
import dev.jinsfoni.photobook.data.remote.dto.ModelDto
import dev.jinsfoni.photobook.data.remote.dto.SearchModelDto
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.ui.models.CollectionCard
import dev.jinsfoni.photobook.ui.models.ModelCard
import dev.jinsfoni.photobook.ui.models.ModelDetail
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 模特列表/详情 —— DTO → UI 模型。avatar/hero 是原始 /media rel,走 thumb(w) 拼
 * /t/{w}x/ 缩略;合集卡与 S2 同构(coverThumb 已是前缀 rel)。
 */
@Singleton
class ModelsRepository @Inject constructor(
    private val api: MobileApi,
    private val session: SessionStoreApi,
) {

    private var listCache: Map<String, List<ModelCard>>? = null

    suspend fun list(featured: Boolean = false, sort: String = "latest"): List<ModelCard> {
        if (!featured) {
            listCache?.get(sort)?.let { return it }
        }
        val dto = safeCall { api.models(if (featured) "1" else null, sort) }
        val base = session.currentBaseUrl()
        val cards = dto.items.map { it.toCard(base) }
        if (!featured) {
            listCache = (listCache ?: emptyMap()) + (sort to cards)
        }
        return cards
    }

    suspend fun detail(slug: String): ModelDetail {
        val dto = safeCall { api.model(slug) }
        val base = session.currentBaseUrl()
        return ModelDetail(
            slug = dto.slug,
            name = dto.name,
            stage = dto.stage,
            // 详情头图全屏铺:900 档发糊 → /t/s2400/ 短边档(同轮播/灯箱 previewUrl)
            heroUrl = (dto.hero ?: dto.avatar)?.let { MediaUrls.thumbShortSide(base, it, 2400) },
            bio = dto.bio.orEmpty(),
            agency = dto.agency.orEmpty(),
            height = dto.height.orEmpty(),
            measurements = dto.measurements.orEmpty(),
            count = dto.count,
            photoCount = dto.photoCount,
            tags = dto.tags,
            collections = dto.collections.map { it.toModel(base) },
        )
    }

    fun clearCache() {
        listCache = null
    }
}

internal fun ModelDto.toCard(base: String) = ModelCard(
    slug = slug,
    name = name,
    stage = stage,
    imageUrl = avatar?.let { MediaUrls.thumb(baseUrl = base, rel = it, width = 900, height = 1350) }, // 2:3 裁切
    count = count,
    photoCount = photoCount,
    featured = featured,
    tags = tags,
)

internal fun SearchModelDto.toSearchCard(base: String) = ModelCard(
    slug = slug,
    name = name,
    stage = stage,
    imageUrl = thumb?.let { MediaUrls.fromPrefixed(base, it) },
    count = count,
    photoCount = 0,
    featured = false,
    tags = tags,
)

internal fun CollectionCardDto.toModel(base: String) = CollectionCard(
    slug = slug,
    title = title,
    modelName = model_name,
    imageUrl = coverThumb?.let { MediaUrls.fromPrefixed(base, it) },
    count = count,
    tags = tags,
)
