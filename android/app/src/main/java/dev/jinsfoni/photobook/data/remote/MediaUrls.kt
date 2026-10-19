package dev.jinsfoni.photobook.data.remote

/**
 * 媒体 URL 拼装 —— 与服务端 app/services/media.py 约定一致:
 * 原图 /media/{rel};缩略图 /t/{w}x{h}/{rel}(h 省略 → 等比)或
 * /t/s{w}/{rel}(短边钳制,竖图钳宽、横图钳高,等比不裁)。
 *
 * 尾段 rel 必须保留源文件真实后缀(jpg/png/webp),**不得再附加 .webp** ——
 * 服务端从 1.8.x 起按「最后一段后缀即源文件后缀」解析,拼成 x.jpg.webp 会
 * 被当成名为 x.jpg.webp 的源文件而 404(表现:详情页照片墙/发现页轮播全空,
 * 卡片却正常 —— 卡片用的是服务端下发的 coverThumb 前缀路径,不受影响)。
 * 缩略图输出格式恒为 WebP,由响应 Content-Type 标明,与 URL 后缀无关。
 */
object MediaUrls {

    /** 媒体永远挂在服务 origin 根(/media、/t),与 API 前缀无关;截掉 baseUrl 的 path 部分。 */
    private fun origin(baseUrl: String): String =
        baseUrl.trimEnd('/').let { b ->
            val m = Regex("^(https?://[^/]+)").find(b)
            m?.value ?: b
        }

    /** 历史 payload 里 rel 有的带前导 /,统一去掉,避免拼出 //media 双斜杠。 */
    private fun path(rel: String): String = rel.trimStart('/')

    fun original(baseUrl: String, rel: String): String =
        "${origin(baseUrl)}/media/${path(rel)}"

    /** 宽度等比缩略图(/t/{w}/{rel})。 */
    fun thumb(baseUrl: String, rel: String, width: Int): String =
        "${origin(baseUrl)}/t/$width/${path(rel)}"

    /** 宽×高裁切缩略图(/t/{w}x{h}/{rel})。 */
    fun thumb(baseUrl: String, rel: String, width: Int, height: Int): String =
        "${origin(baseUrl)}/t/${width}x$height/${path(rel)}"

    /** 短边钳制缩略图(/t/s{w}/{rel}):竖图钳宽、横图钳高,等比不裁。 */
    fun thumbShortSide(baseUrl: String, rel: String, shortSide: Int): String =
        "${origin(baseUrl)}/t/s$shortSide/${path(rel)}"

    /**
     * 服务端已生成带 /t/ 前缀的缩略 rel(如 "t/s900/cover.jpg"),
     * 直拼即可,不能再经 thumb() 二次加前缀。
     */
    fun fromPrefixed(baseUrl: String, rel: String): String =
        "${origin(baseUrl)}/${path(rel)}"
}
