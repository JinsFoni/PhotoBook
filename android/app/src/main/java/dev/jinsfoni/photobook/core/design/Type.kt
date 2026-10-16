package dev.jinsfoni.photobook.core.design

import android.content.Context
import android.graphics.Typeface
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import dev.jinsfoni.photobook.R

/**
 * 字体对齐 Android 设计稿(docs/android-design/ui/ui.css):
 *   .serif: Georgia,"Songti SC","Noto Serif SC" → 标题衬线;
 *           Georgia 是商业字体不能打包,用 Google 开源的度量兼容替代 Gelasio;
 *           中文走 Noto Serif SC(= 设计稿栈里的 Noto Serif SC),打包 400 一档 ——
 *           系统中文回退链在多数机型上指向黑体,衬线中文必须自带。
 *   正文/UI:系统无衬线(设计稿 -apple-system/"PingFang SC")→ Archivo 对齐 web --ui。
 *
 * 字体风格三选一(与 Web 端 pc.font.v1/data-font 对齐,见 app/static/fonts/packs.css):
 *   cute(默认)  = 玩酷体(拉丁+汉字+假名) × Gamja Flower(谚文/缺字兜底)
 *   minimal      = Neucha(拉丁) × 霞鹜漫黑(汉字) × Poor Story(谚文)
 *   modern       = Gelasio/Times(拉丁衬线) × 思源宋体 SC(汉字),全衬线
 * 三包共用同一字号阶梯(PhotoType),仅字体族不同;切换走 ThemeState.fontPack。
 */
enum class FontPack { CUTE, MINIMAL, MODERN }

// Gelasio 是静态字体,按设计稿正文/标题都是 400 常规;带 500/600 备 UI 加粗用。
// 中文标题要衬线:Compose 的 FontFamily 多字体只按字重选一个、不做逐字符回退,
// Gelasio 没有中文会直接掉到系统黑体。用平台 Typeface.CustomFallbackBuilder 组链
// ( Gelasio → Noto Serif SC → 系统 serif ),中文落到思源宋体 ——
// 即设计稿 .serif 栈 "Georgia, Songti SC, Noto Serif SC" 的 Android 对应物。
val PhotoSerif: FontFamily by lazy {
    val ctx: Context = dev.jinsfoni.photobook.PhotoBookApp.instance
    val gelasio = android.graphics.fonts.Font.Builder(ctx.resources, R.font.gelasio_regular).build()
    val notoSerifSc = android.graphics.fonts.Font.Builder(ctx.resources, R.font.noto_serif_sc_regular).build()
    val platform = Typeface.CustomFallbackBuilder(
        android.graphics.fonts.FontFamily.Builder(gelasio).build(),
    )
        .addCustomFallback(android.graphics.fonts.FontFamily.Builder(notoSerifSc).build())
        .setSystemFallback("serif")
        .build()
    FontFamily(typeface = platform)
}

val PhotoSans = FontFamily(
    Font(R.font.archivo_regular, FontWeight.Normal),
    Font(R.font.archivo_medium, FontWeight.Medium),
    Font(R.font.archivo_semibold, FontWeight.SemiBold),
)

// 品牌词标专字体:Web static/fonts/wordmark-serif.woff2(思源宋 KR 拉丁
// 子集)wght 600 实例化成 ttf;"Photo Collection" 全拉丁无回退需求,
// 若将来放中文,CustomFallbackBuilder 链上系统 serif 即可。
val WordmarkBrandFamily: FontFamily by lazy {
    val ctx: Context = dev.jinsfoni.photobook.PhotoBookApp.instance
    val face = android.graphics.fonts.Font.Builder(ctx.resources, R.font.wordmark_serif).build()
    val platform = Typeface.CustomFallbackBuilder(
        android.graphics.fonts.FontFamily.Builder(face).build(),
    )
        .setSystemFallback("serif")
        .build()
    FontFamily(typeface = platform)
}

// 玩酷体没有中文标点/谚文,链到 Gamja Flower(谚文+拉丁兜底),再落系统 sans;
// 对应 Web 端 G7 栈 "G7 WanKu, G7 GamjaFlower, PingFang SC"。
private val CuteDisplay: FontFamily by lazy {
    val ctx: Context = dev.jinsfoni.photobook.PhotoBookApp.instance
    val wanku = android.graphics.fonts.Font.Builder(ctx.resources, R.font.wanku_regular).build()
    val gamja = android.graphics.fonts.Font.Builder(ctx.resources, R.font.gamjaflower_regular).build()
    val platform = Typeface.CustomFallbackBuilder(
        android.graphics.fonts.FontFamily.Builder(wanku).build(),
    )
        .addCustomFallback(android.graphics.fonts.FontFamily.Builder(gamja).build())
        .setSystemFallback("sans-serif")
        .build()
    FontFamily(typeface = platform)
}

// minimal 包:Neucha 只有 78 个拉丁字形,汉字/假名走霞鹜漫黑,谚文走 Poor Story。
private val MinimalDisplay: FontFamily by lazy {
    val ctx: Context = dev.jinsfoni.photobook.PhotoBookApp.instance
    val neucha = android.graphics.fonts.Font.Builder(ctx.resources, R.font.neucha_regular).build()
    val marker = android.graphics.fonts.Font.Builder(ctx.resources, R.font.marker_gothic_regular).build()
    val poorStory = android.graphics.fonts.Font.Builder(ctx.resources, R.font.poorstory_regular).build()
    val platform = Typeface.CustomFallbackBuilder(
        android.graphics.fonts.FontFamily.Builder(neucha).build(),
    )
        .addCustomFallback(android.graphics.fonts.FontFamily.Builder(marker).build())
        .addCustomFallback(android.graphics.fonts.FontFamily.Builder(poorStory).build())
        .setSystemFallback("sans-serif")
        .build()
    FontFamily(typeface = platform)
}

// modern 包与 PhotoSerif 同一套(Gelasio × 思源宋体 SC 全衬线),直接复用。
private val ModernDisplay: FontFamily by lazy { PhotoSerif }

/** 当前生效的字体风格包(内存态,启动灌入/设置页切换,与 ThemeState.mode 同机制)。 */
object FontPackState {
    var pack by mutableStateOf(FontPack.CUTE)
}

/** 按当前风格包解析标题/展示字体族;正文 UI 字体随之(三包 display/ui 同族)。 */
val PhotoDisplayFamily: FontFamily
    get() = when (FontPackState.pack) {
        FontPack.CUTE -> CuteDisplay
        FontPack.MINIMAL -> MinimalDisplay
        FontPack.MODERN -> ModernDisplay
    }

/**
 * 排版 —— 字体族来自当前风格包(PhotoDisplayFamily),
 * 字号阶梯对齐 ui.css(design.md:图片是唯一英雄,衬线大标题)。
 */
object PhotoType {
    // Hero 大标题(hero h1 32px)
    val heroTitle: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 32.sp,
        lineHeight = 35.sp,      // 1.1
    )

    // 详情页 H1(detail-head h1 29px)
    val detailTitle: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 29.sp,
        lineHeight = 32.sp,      // 1.12
    )

    // 节标题(section-head h2 20px)
    val sectionTitle: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    )

    // 卡片题(card .t 15px,.t.serif → 衬线)
    val cardTitle: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,      // 1.3
    )

    // appbar 词标(.appbar .wordmark 18px,.wordmark.serif)
    val wordmark: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 18.sp,
        lineHeight = 23.sp,
        letterSpacing = 0.2.sp,
    )

    // 品牌词标(Web 端 .wordmark 19px):衬线专字体(思源宋 KR 拉丁子集
    // wght 600,= Web static/fonts/wordmark.css 的 PB Wordmark,不随
    // 风格包切换)。纯拉丁文本用;中文回退系统 serif(与 Web 栈一致)
    val wordmarkBrand: TextStyle get() = TextStyle(
        fontFamily = WordmarkBrandFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 19.sp,
        lineHeight = 19.sp,      // 1.0
        letterSpacing = 0.19.sp, // 0.01em
    )

    // 详情/模型 hero 榜下模特名(.byline .model 15px,.model.serif → 衬线)
    val bylineModel: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // byline 通用(返回箭头、seg 页签等 15px 无衬线场景)
    val byline: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // 正文(基准 14px)
    val body: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 21.sp,      // 1.5
    )

    // byline 日期等弱化文字(.byline .date 12.5px、chip 12px)
    val caption: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 12.5.sp,
        lineHeight = 17.sp,
    )

    // 卡片副标/计数(card .m 11.5px、count)
    val micro: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 11.5.sp,
        lineHeight = 15.sp,
    )

    // 页码/crumbs/hero kick(11px)
    val tag: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    )

    // 底栏 tab 标签(11px、letter-spacing 0.2px)
    val tabLabel: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        lineHeight = 15.sp,
        letterSpacing = 0.2.sp,
    )

    // 底栏选中 tab(600 字重,原型 .tab.active span)
    val tabLabelActive: TextStyle get() = TextStyle(
        fontFamily = PhotoDisplayFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 11.sp,
        lineHeight = 15.sp,
        letterSpacing = 0.2.sp,
    )

    // 灯箱页码(lb-top .idx 13.5px,tnum 等宽数字)
    val lightboxIndex = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 13.5.sp,
        lineHeight = 18.sp,
        fontFeatureSettings = "tnum",
    )
}
