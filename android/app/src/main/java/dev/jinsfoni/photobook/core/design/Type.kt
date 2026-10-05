package dev.jinsfoni.photobook.core.design

import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import dev.jinsfoni.photobook.R

/**
 * 字体对齐 web 设计稿(assets/app.css):
 *   --display: "Bodoni Moda", serif   → 标题衬线
 *   --ui: "Archivo", sans-serif       → 正文/UI
 * 中文无对应字形,回退系统字体(与 web 的字体栈行为一致)。
 */
// Bodoni Moda 是可变字体(opsz 6..96),资源里只带了 wght 400 一份;
// 用 FontVariation 把光学尺寸固定到大字号的展示端(96),气质对齐 web 大标题。
@OptIn(ExperimentalTextApi::class)
val PhotoSerif = FontFamily(
    Font(
        resId = R.font.bodoni_moda_regular,
        variationSettings = FontVariation.Settings(
            FontVariation.weight(400),
            FontVariation.Setting("opsz", 96f),
        ),
    ),
)

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

    // 卡片题(card .t 15px)
    val cardTitle = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,      // 1.3
    )

    // 正文(基准 14px)
    val body = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 21.sp,      // 1.5
    )

    // byline 模特名(.byline .model 15px)
    val byline = TextStyle(
        fontFamily = PhotoSans,
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // 日期/弱化文字(.byline .date 12.5px、chip 12px)
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
