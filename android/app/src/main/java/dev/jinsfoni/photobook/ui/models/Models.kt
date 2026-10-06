package dev.jinsfoni.photobook.ui.models

/** UI 层模型(与服务端 DTO 解耦;URL 已拼全)。 */

data class DiscoverFeed(
    val featured: List<CollectionCard>,
    val latest: List<CollectionCard>,
    val models: List<CollectionCard>,
    val tags: List<TagCount>,
    val stats: Stats,
)

data class TagCount(val name: String, val collections: Int, val models: Int)

data class Stats(val collections: Int, val models: Int)

data class CollectionCard(
    val slug: String,
    val title: String,
    val modelName: String,
    val imageUrl: String?,
    /** 大图场景(发现页 hero 轮播)用的原图 URL;小卡只看 imageUrl。 */
    val heroUrl: String? = null,
    val count: Int,
    val tags: List<String>,
)

data class CollectionDetail(
    val slug: String,
    val title: String,
    val date: String,
    val tags: List<String>,
    val count: Int,
    val heroUrl: String?,
    val modelName: String,
    val modelSlug: String,
    val photos: List<PhotoItem>,
)

data class PhotoItem(
    val idx: Int,
    val thumbUrl: String,
    /** 原图(/media/,可能是几 MB 的 JPEG)。 */
    val fullUrl: String,
    /** 大图预览(/t/2400/,webp;灯箱默认用它,设置开「加载原图」才走 fullUrl)。 */
    val previewUrl: String,
    val width: Int,
    val height: Int,
)

/** 收藏集合(key 列表):model slug / collection slug / photo "slug:idx"。 */
data class Favorites(
    val model: List<String> = emptyList(),
    val collection: List<String> = emptyList(),
    val photo: List<String> = emptyList(),
) {
    fun contains(type: String, key: String): Boolean = when (type) {
        "model" -> key in model
        "collection" -> key in collection
        "photo" -> key in photo
        else -> false
    }

    fun toggled(type: String, key: String, added: Boolean): Favorites {
        fun apply(list: List<String>): List<String> =
            (if (added) list + key else list - key).distinct()
        return when (type) {
            "model" -> copy(model = apply(model))
            "collection" -> copy(collection = apply(collection))
            "photo" -> copy(photo = apply(photo))
            else -> this
        }
    }
}

/** S5/S6 模特卡/详情(URL 已拼全)。 */
data class ModelCard(
    val slug: String,
    val name: String,
    val stage: String,
    val imageUrl: String?,
    val count: Int,
    val photoCount: Int,
    val featured: Boolean,
    val tags: List<String>,
)

data class ModelDetail(
    val slug: String,
    val name: String,
    val stage: String,
    val heroUrl: String?,
    val bio: String,
    val agency: String,
    val height: String,
    val measurements: String,
    val count: Int,
    val photoCount: Int,
    val tags: List<String>,
    val collections: List<CollectionCard>,
)

/** S10 搜索三段结果(URL 已拼全)。 */
data class SearchResults(
    val q: String,
    val models: List<ModelCard>,
    val collections: List<CollectionCard>,
    val tags: List<String>,
)
