package dev.jinsfoni.photobook.data.remote

/**
 * 媒体 URL 拼装 —— 与服务端 app/services/media.py 约定一致:
 * 原图 /media/{rel};缩略图 /t/{w}x{h}/{rel}.webp(h 省略 → 等比)。
 * DTO 只存 rel 路径,展示时经此拼全 URL。
 */
object MediaUrls {

    fun original(baseUrl: String, rel: String): String =
        "${baseUrl.trimEnd('/')}/media/$rel"

    /** 宽度等比缩略图(/t/{w}/{rel}.webp;服务端保留原扩展名再追加 .webp)。 */
    fun thumb(baseUrl: String, rel: String, width: Int): String =
        "${baseUrl.trimEnd('/')}/t/$width/$rel.webp"

    /** 宽×高裁切缩略图(/t/{w}x{h}/{rel}.webp)。 */
    fun thumb(baseUrl: String, rel: String, width: Int, height: Int): String =
        "${baseUrl.trimEnd('/')}/t/${width}x$height/$rel.webp"

    /**
     * 服务端已生成带 /t/ 前缀的缩略 rel(如 "t/900x/cover.webp"),
     * 直拼即可,不能再经 thumb() 二次加前缀。
     */
    fun fromPrefixed(baseUrl: String, rel: String): String =
        "${baseUrl.trimEnd('/')}/$rel"
}
