package dev.jinsfoni.photobook.ui.models

/** UI 层模型(与服务端 DTO 解耦;URL 已拼全)。 */

data class DiscoverFeed(
    val featured: List<CollectionCard>,
    val latest: List<CollectionCard>,
    val models: List<CollectionCard>,
    val tags: List<TagCount>,
    val stats: Stats,
    /** 写真视频是平行模块:发现页视频段(封面帧卡,与写真卡同型)。 */
    val videoAlbums: List<CollectionCard> = emptyList(),
)

data class TagCount(val name: String, val collections: Int, val models: Int)

data class Stats(val collections: Int, val models: Int, val videoAlbums: Int = 0)

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

/** 单条视频(写真视频模块,与 PhotoItem 平行)。 */
data class VideoItem(
    val idx: Int,
    /** 播放源(/video/{rel};服务端 FileResponse 原生 Range,拖动进度条可用)。 */
    val videoUrl: String,
    /** 封面帧 webp(/t/s900/{poster}.webp);ffmpeg 缺失时为 null,播放器黑屏兜底。 */
    val posterUrl: String?,
    val durationSec: Double?,
    val width: Int?,
    val height: Int?,
)

/** 视频专辑详情(与 CollectionDetail 平行)。 */
data class VideoAlbumDetail(
    val slug: String,
    val title: String,
    val date: String,
    val tags: List<String>,
    val count: Int,
    val heroUrl: String?,
    val modelName: String,
    val modelSlug: String,
    val videos: List<VideoItem>,
)

/** 收藏集合(key 列表):model slug / collection slug / photo "slug:idx" /
 *  video_album slug / video "album_slug:v{idx}"(v 前缀与照片键区分)。 */
data class Favorites(
    val model: List<String> = emptyList(),
    val collection: List<String> = emptyList(),
    val photo: List<String> = emptyList(),
    val videoAlbum: List<String> = emptyList(),
    val video: List<String> = emptyList(),
) {
    fun contains(type: String, key: String): Boolean = when (type) {
        "model" -> key in model
        "collection" -> key in collection
        "photo" -> key in photo
        "video_album" -> key in videoAlbum
        "video" -> key in video
        else -> false
    }

    fun toggled(type: String, key: String, added: Boolean): Favorites {
        fun apply(list: List<String>): List<String> =
            (if (added) list + key else list - key).distinct()
        return when (type) {
            "model" -> copy(model = apply(model))
            "collection" -> copy(collection = apply(collection))
            "photo" -> copy(photo = apply(photo))
            "video_album" -> copy(videoAlbum = apply(videoAlbum))
            "video" -> copy(video = apply(video))
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
    // 写真视频是平行模块:模特详情另一段视频专辑卡列
    val videoAlbums: List<CollectionCard> = emptyList(),
    val videoAlbumCount: Int = 0,
    val videoCount: Int = 0,
)

/** S10 搜索三段结果(URL 已拼全)。 */
data class SearchResults(
    val q: String,
    val models: List<ModelCard>,
    val collections: List<CollectionCard>,
    val tags: List<String>,
    val videoAlbums: List<CollectionCard> = emptyList(),
)
