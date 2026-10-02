package dev.jinsfoni.photobook.core.design

import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * 排版 —— 标题走衬线(FontFamily.Serif 映射 EB Garamond 气质),
 * 正文无衬线;字号全部对齐 ui.css(design.md:图片是唯一英雄,衬线大标题)。
 */
object PhotoType {
    // Hero 大标题(hero h1 32px)
    val heroTitle = TextStyle(
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Normal,
        fontSize = 32.sp,
        lineHeight = 35.sp,      // 1.1
    )

    // 详情页 H1(detail-head h1 29px)
    val detailTitle = TextStyle(
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Normal,
        fontSize = 29.sp,
        lineHeight = 32.sp,      // 1.12
    )

    // 节标题(section-head h2 20px)
    val sectionTitle = TextStyle(
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Normal,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    )

    // 卡片题(card .t 15px)
    val cardTitle = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,      // 1.3
    )

    // 正文(基准 14px)
    val body = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 21.sp,      // 1.5
    )

    // byline 模特名(.byline .model 15px)
    val byline = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    )

    // 日期/弱化文字(.byline .date 12.5px、chip 12px)
    val caption = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 12.5.sp,
        lineHeight = 17.sp,
    )

    // 卡片副标/计数(card .m 11.5px、count)
    val micro = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 11.5.sp,
        lineHeight = 15.sp,
    )

    // 页码(tab 11px、crumbs 11px、hero kick 11px)
    val tag = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    )

    // 灯箱页码(lb-top .idx 13.5px,tnum 等宽数字)
    val lightboxIndex = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 13.5.sp,
        lineHeight = 18.sp,
        fontFeatureSettings = "tnum",
    )
}
