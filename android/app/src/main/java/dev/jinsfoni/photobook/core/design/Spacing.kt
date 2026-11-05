package dev.jinsfoni.photobook.core.design

import androidx.compose.ui.unit.dp

/**
 * 版心左右留白(屏幕两侧间距)。
 *
 * 各屏「appbar / 筛选行 / 网格 contentPadding / 骨架屏」原本各自写死同一个数值,
 * 改一次要动二十多处,容易漏。这里收成常量,间距要调只改本文件。
 *
 * - [Gutter]:列表流页(发现 / 写真集 / 模特 / 收藏 / 搜索 / 详情)的左右留白。
 * - [Form]:设置页、登录页这类表单页的左右留白(比列表流宽一档)。
 */
object PhotoSpacing {
    val Gutter = 14.dp
    val Form = 24.dp
}
