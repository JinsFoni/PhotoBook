package dev.jinsfoni.photobook.core.design

import android.content.Context
import android.graphics.Typeface
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
 */
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

/**
 * 排版 —— 标题衬线(Bodoni Moda),正文无衬线(Archivo);
 * 字号全部对齐 ui.css(design.md:图片是唯一英雄,衬线大标题)。
 */
object PhotoType {
    // Hero 大标题(hero h1 32px)
    val heroTitle = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 32.sp,
        lineHeight = 35.sp,      // 1.1
    )

    // 详情页 H1(detail-head h1 29px)
    val detailTitle = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 29.sp,
        lineHeight = 32.sp,      // 1.12
    )

    // 节标题(section-head h2 20px)
    val sectionTitle = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    )

    // 卡片题(card .t 15px,.t.serif → 衬线)
    val cardTitle = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,      // 1.3
    )

    // appbar 词标(.appbar .wordmark 18px,.wordmark.serif)
    val wordmark = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 18.sp,
        lineHeight = 23.sp,
        letterSpacing = 0.2.sp,
    )

    // 详情/模型 hero 榜下模特名(.byline .model 15px,.model.serif → 衬线)
    val bylineModel = TextStyle(
        fontFamily = PhotoSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // byline 通用(返回箭头、seg 页签等 15px 无衬线场景)
    val byline = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // 正文(基准 14px)
    val body = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 21.sp,      // 1.5
    )

    // byline 日期等弱化文字(.byline .date 12.5px、chip 12px)
    val caption = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 12.5.sp,
        lineHeight = 17.sp,
    )

    // 卡片副标/计数(card .m 11.5px、count)
    val micro = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 11.5.sp,
        lineHeight = 15.sp,
    )

    // 页码/crumbs/hero kick(11px)
    val tag = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    )

    // 底栏 tab 标签(11px、letter-spacing 0.2px)
    val tabLabel = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        lineHeight = 15.sp,
        letterSpacing = 0.2.sp,
    )

    // 底栏选中 tab(600 字重,原型 .tab.active span)
    val tabLabelActive = TextStyle(
        fontFamily = PhotoSans,
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
