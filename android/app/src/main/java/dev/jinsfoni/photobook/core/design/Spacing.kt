package dev.jinsfoni.photobook.core.design

import androidx.compose.ui.unit.dp

/**
 * 版心与卡片间距(与 Web 端 `app/static/app.css` 的手机窄屏变量一一对应)。
 *
 * 各屏原本各自写死同一个数, 改一次要动二十多处, 容易漏。这里收成常量:
 * 间距要对齐只改本文件 —— CSS 那边对应改 `--pad / --gutter / --row-gap /
 * --wall-gap` 四个变量即可。
 *
 * - [Gutter]:页面左右留白(appbar / 筛选行 / 网格 contentPadding / 骨架屏)。
 * - [CardGap] / [CardGapY]:卡片网格的列间距 / 行间距(行比列松, 给标题留呼吸)。
 * - [WallGap]:照片墙(瀑布流)间距, 行列同值。
 * - [Form]:设置页、登录页这类表单页的左右留白(比列表流宽一档)。
 */
object PhotoSpacing {
    val Gutter = 12.dp
    val CardGap = 12.dp
    val CardGapY = 16.dp
    val WallGap = 10.dp
    val Form = 24.dp
}
