package dev.jinsfoni.photobook.core.design

import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color

/**
 * PhotoBook 三主题色彩 token —— 严格对齐 docs/android-design/ui/ui.css:
 * Light / Dark / Blur(虚化)。Blur 主题的「垫底代表图 blur(42px)+saturate(1.12)」
 * 由内容层用真实图片实现,这里提供面板半透明色与垫底基色。
 */
@Immutable
data class PhotoColors(
    // 页面底色(blur 主题为垫底基色 #101114,内容面板再用半透明色)
    val paper: Color,
    // 面板/卡片底色(dark 与 blur 用半透明面板色 paper2/paper3)
    val paper2: Color,
    val paper3: Color,
    // 主墨色 / 次级 / 弱化
    val ink: Color,
    val ink2: Color,
    val ink3: Color,
    // 绯红点缀
    val accent: Color,
    val onAccent: Color,
    // 分隔线
    val line: Color,
    val line2: Color,
    // 不透明纸色(选中态文字/反白用)
    val paperSolid: Color,
    // 选中胶囊底
    val pill: Color,
    // 玻璃条底色(hazeEffect tint 用)与高光/暗部描边
    val barBg: Color,
    val glassHi: Color,
    val glassLo: Color,
    val glassGlow: Color,
    // 底栏斜向流光两端(ui.css --sheen-a/-b)
    val sheenA: Color,
    val sheenB: Color,
)

fun lightColors(): PhotoColors = PhotoColors(
    paper = Color(0xFFFFFFFF),
    paper2 = Color(0xFFF1F1EF),
    paper3 = Color(0xFFE8E8E6),
    ink = Color(0xFF0C0D0F),
    ink2 = Color(0xFF565656),
    ink3 = Color(0xFF8E8E8E),
    accent = Color(0xFFB01B2E),
    onAccent = Color(0xFFFFFFFF),
    line = Color(0xFFE3E3E1),
    line2 = Color(0xFFCFCFCD),
    paperSolid = Color(0xFFFFFFFF),
    pill = Color(0x120C0D0F),       // rgba(12,13,15,.07)
    barBg = Color(0x66FFFFFF),      // rgba(255,255,255,.40)
    glassHi = Color(0xD9FFFFFF),    // rgba(255,255,255,.85)
    glassLo = Color(0x33FFFFFF),    // rgba(255,255,255,.20)
    glassGlow = Color(0x1FFFFFFF),  // rgba(255,255,255,.12)
    sheenA = Color(0x73FFFFFF),     // rgba(255,255,255,.45)
    sheenB = Color(0x1FFFFFFF),     // rgba(255,255,255,.12)
)

fun darkColors(): PhotoColors = PhotoColors(
    paper = Color(0xFF0C0D0F),
    paper2 = Color(0xFF16181B),
    paper3 = Color(0xFF1E2124),
    ink = Color(0xFFF7F7F5),
    ink2 = Color(0xFFA0A3A8),
    ink3 = Color(0xFF6E7276),
    accent = Color(0xFFE0455A),
    onAccent = Color(0xFFFFFFFF),
    line = Color(0xFF24262A),
    line2 = Color(0xFF33363B),
    paperSolid = Color(0xFF0C0D0F),
    pill = Color(0x1AFFFFFF),       // rgba(255,255,255,.10)
    barBg = Color(0x7A16181B),      // rgba(22,24,27,.48)
    glassHi = Color(0x3DFFFFFF),    // rgba(255,255,255,.24)
    glassLo = Color(0x0DFFFFFF),    // rgba(255,255,255,.05)
    glassGlow = Color(0x0DFFFFFF),
    sheenA = Color(0x0FFFFFFF),     // rgba(255,255,255,.06) 暗背景上左端泛白,减半
    sheenB = Color(0x08FFFFFF),     // rgba(255,255,255,.03)
)

fun blurColors(): PhotoColors = PhotoColors(
    paper = Color(0xFF101114),      // 垫底基色(ui.css .screen.blur background)
    paper2 = Color(0xB80C0D0F),     // rgba(12,13,15,.72)
    paper3 = Color(0xB816181B),     // rgba(22,24,27,.72)
    ink = Color(0xFFF7F7F5),
    ink2 = Color(0xFFB3B6BB),
    ink3 = Color(0xFF7D8186),
    accent = Color(0xFFE0455A),
    onAccent = Color(0xFFFFFFFF),
    line = Color(0x24FFFFFF),       // rgba(255,255,255,.14)
    line2 = Color(0x38FFFFFF),      // rgba(255,255,255,.22)
    paperSolid = Color(0xFF0C0D0F),
    pill = Color(0x1AFFFFFF),
    barBg = Color(0x6B0C0D0F),      // rgba(12,13,15,.42)
    glassHi = Color(0x4DFFFFFF),    // rgba(255,255,255,.30)
    glassLo = Color(0x0FFFFFFF),    // rgba(255,255,255,.06)
    glassGlow = Color(0x0FFFFFFF),
    sheenA = Color(0x10FFFFFF),     // rgba(255,255,255,.06) 暗背景上左端泛白,减半
    sheenB = Color(0x0AFFFFFF),     // rgba(255,255,255,.04)
)
