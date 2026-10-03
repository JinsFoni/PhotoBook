package dev.jinsfoni.photobook.data.remote

/**
 * 媒体 URL 拼装 —— 与服务端 app/services/media.py 约定一致:
 * 原图 /media/{rel};缩略图 /t/{w}x{h}/{rel}.webp(h 省略 → 等比)。
 * DTO 只存 rel 路径,展示时经此拼全 URL。
 */
object MediaUrls {

    /** 媒体永远挂在服务 origin 根(/media、/t),与 API 前缀无关;截掉 baseUrl 的 path 部分。 */
    private fun origin(baseUrl: String): String =
        baseUrl.trimEnd('/').let { b ->
            val m = Regex("^(https?://[^/]+)").find(b)
            m?.value ?: b
        }

    fun original(baseUrl: String, rel: String): String =
        "${origin(baseUrl)}/media/$rel"

    /** 宽度等比缩略图(/t/{w}/{rel}.webp;服务端保留原扩展名再追加 .webp)。 */
    fun thumb(baseUrl: String, rel: String, width: Int): String =
        "${origin(baseUrl)}/t/$width/$rel.webp"

    /** 宽×高裁切缩略图(/t/{w}x{h}/{rel}.webp)。 */
    fun thumb(baseUrl: String, rel: String, width: Int, height: Int): String =
        "${origin(baseUrl)}/t/${width}x$height/$rel.webp"

    /**
     * 服务端已生成带 /t/ 前缀的缩略 rel(如 "t/900x/cover.webp"),
     * 直拼即可,不能再经 thumb() 二次加前缀。
     */
    fun fromPrefixed(baseUrl: String, rel: String): String =
        "${origin(baseUrl)}/$rel"
}
