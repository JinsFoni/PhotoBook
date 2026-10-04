package dev.jinsfoni.photobook.data.remote.dto

import kotlinx.serialization.Serializable

/** 服务端统一错误体 {"error":{"code","message"}}。 */
@Serializable
data class ErrorEnvelopeDto(val error: ErrorBodyDto)

@Serializable
data class ErrorBodyDto(val code: String, val message: String)

// ---- auth -----------------------------------------------------------------

@Serializable
data class LoginRequestDto(val username: String, val password: String)

@Serializable
data class LoginResponseDto(val token: String, val expires_at: String)

@Serializable
data class MeDto(val username: String, val role: String)

// ---- discover -------------------------------------------------------------

@Serializable
data class DiscoverDto(
    val featured: List<CollectionDto>,
    val latest: List<CollectionDto>,
    val models: List<ModelDto>,
    val tags: List<TagCountDto>,
    val stats: StatsDto,
)

@Serializable
data class TagCountDto(val name: String, val collections: Int, val models: Int)

@Serializable
data class StatsDto(val collections: Int, val models: Int)

// ---- collection(卡片/详情两级)---------------------------------------------

/** 完整合集载荷(discover featured/latest 与详情共用,详情额外有 model);coverThumb 详情版为 t/900x 前缀 rel。 */
@Serializable
data class CollectionDto(
    val id: Int,
    val slug: String,
    val title: String,
    val date: String = "",
    val featured: Boolean = false,
    val model_slug: String = "",
    val model_name: String = "",
    val cover: String? = null,
    val coverThumb: String? = null,
    val photos: List<PhotoDto> = emptyList(),
    val tags: List<String> = emptyList(),
    val count: Int = 0,
    val heroCoverThumb: String? = null,
    val model: ModelRefDto? = null,
)

/** 列表卡片(_collection_card)。 */
@Serializable
data class CollectionCardDto(
    val id: Int,
    val slug: String,
    val title: String,
    val model_slug: String = "",
    val model_name: String = "",
    val cover: String? = null,
    val coverThumb: String? = null,
    val count: Int = 0,
    val tags: List<String> = emptyList(),
)

@Serializable
data class PhotoDto(val idx: Int, val file: String, val w: Int, val h: Int)

@Serializable
data class ModelRefDto(val slug: String, val name: String)

@Serializable
data class CollectionsPageDto(
    val items: List<CollectionCardDto>,
    val total: Int,
    val page: Int,
    val pageSize: Int,
)

// ---- model(列表/详情)-----------------------------------------------------

/** /models 响应(items 与 discover.models 同形)。 */
@Serializable
data class ModelsPageDto(val items: List<ModelDto>, val total: Int)

/** /models/{slug}:payload + 该模特写真卡列。 */
@Serializable
data class ModelDetailDto(
    val id: Int,
    val slug: String,
    val name: String,
    val stage: String = "",
    val avatar: String? = null,
    val gender: String = "",
    val age: Int? = null,
    val height: String? = null,
    val measurements: String? = null,
    val agency: String? = null,
    val bio: String? = null,
    val since: String = "",
    val featured: Boolean = false,
    val latest: String = "",
    val tags: List<String> = emptyList(),
    val count: Int = 0,
    val photoCount: Int = 0,
    val hero: String? = null,
    val collections: List<CollectionCardDto> = emptyList(),
)

// ---- search -----------------------------------------------------------------

@Serializable
data class SearchModelDto(
    val slug: String,
    val name: String,
    val stage: String = "",
    val avatar: String? = null,
    val thumb: String? = null,
    val count: Int = 0,
    val tags: List<String> = emptyList(),
)

@Serializable
data class SearchResultDto(
    val q: String,
    val models: List<SearchModelDto> = emptyList(),
    val collections: List<CollectionCardDto> = emptyList(),
    val tags: List<String> = emptyList(),
)

// ---- model ----------------------------------------------------------------

@Serializable
data class ModelDto(
    val id: Int,
    val slug: String,
    val name: String,
    val stage: String = "",
    val avatar: String? = null,
    val gender: String = "",
    val age: Int? = null,
    val height: String? = null,      // 库里存展示字符串(如 "171 cm")
    val measurements: String? = null,
    val agency: String? = null,
    val bio: String? = null,
    val since: String = "",
    val featured: Boolean = false,
    val latest: String = "",
    val tags: List<String> = emptyList(),
    val count: Int = 0,
    val photoCount: Int = 0,
)

// ---- favorites -------------------------------------------------------------

@Serializable
data class FavoritesDto(
    val model: List<String> = emptyList(),
    val collection: List<String> = emptyList(),
    val photo: List<String> = emptyList(),
)

@Serializable
data class FavoriteRequestDto(val type: String, val key: String, val added: Boolean)

@Serializable
data class FavoriteResultDto(val ok: Boolean, val type: String, val key: String, val added: Boolean)

/** GET /favorites/resolve:三段实体(S7 直接渲染)。 */
@Serializable
data class FavoritesResolveDto(
    val models: List<ModelDto> = emptyList(),
    val collections: List<CollectionCardDto> = emptyList(),
    val photos: List<FavPhotoDto> = emptyList(),
)

@Serializable
data class FavPhotoDto(
    val key: String,
    val slug: String,
    val idx: Int,
    val file: String,
    val title: String = "",
    val thumb: String? = null,
    val w: Int? = null,
    val h: Int? = null,
)
