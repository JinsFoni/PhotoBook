# Photo Collection Android — UI 设计规格 V1

> 继承 Web 端设计基因:Editorial / Minimal / Digital Archive。
> 本文档是 Compose 实现的直接依据,token 名与 `app/static/app.css` 一一对应。

## 0. 设计原则(从 Web 端继承)

1. **图片是唯一的英雄**,UI 永远退后:无阴影、无渐变装饰、hairline 分隔
2. **刊头式排版**:大标题用衬线(EB Garamond → Compose 用 `FontFamily.Serif` + 备选思源宋体),正文用系统无衬线
3. **全站 2/3 竖幅卡片**,列表/推荐/头像统一,减少封面裁切
4. **绯红只做点缀**:选中态、收藏心形、焦点环,大面积永不使用
5. 深色主题是"画廊模式":纯黑底、UI 弱化到近乎消失

## 1. 色彩 Token(→ Compose `PhotoColorScheme`)

### Light(白磁 / Editorial Clean)

| Token | 值 | Compose 映射 |
|---|---|---|
| paper | `#FFFFFF` | background / surface |
| paper2 | `#F1F1EF` | surfaceVariant |
| paper3 | `#E8E8E6` | surfaceContainerHigh |
| ink | `#0C0D0F` | onBackground / onSurface |
| ink2 | `#565656` | onSurfaceVariant(次级文字)|
| ink3 | `#8E8E8E` | outline / 弱化文字 |
| accent | `#B01B2E` | primary |
| accentInk | `#FFFFFF` | onPrimary |
| line | `#E3E3E1` | outlineVariant |
| line2 | `#CFCFCD` | 边框强调 |

### Dark(黑 galerie / Immersive)

| Token | 值 |
|---|---|
| paper | `#0C0D0F` |
| paper2 | `#16181B` |
| paper3 | `#1E2124` |
| ink | `#F7F7F5` |
| ink2 | `#A0A3A8` |
| ink3 | `#6E7276` |
| accent | `#E0455A`(暗底下提亮)|
| line | `#24262A` |
| line2 | `#33363B` |

### 灯箱 / 沉浸层(两种主题下相同)

- 底色 `#000000`, scrim `rgba(8,9,10,0.72→0.66)` 渐变
- 图注文字 `#F7F7F5`,操作图标 `#FFFFFF`,禁用态 40% 透明
- **blur 主题下的灯箱**：当前照片放大模糊压暗垫在整个灯箱后面（含顶/底栏），顶/底栏透出同一片虚化——与 Web 端灯箱氛围模式同构

### Blur 虚化主题（Web data-theme=blur 同源移植）

| Token | 值 | 说明 |
|---|---|---|
| 垫底基色 | `#101114` | canvas 淡入前的底色，避免闪黑 |
| 垫底图 | 代表图 `blur(42px) saturate(1.12) scale(1.15)` | 每屏选一张氛围代表图 |
| 深色纱 | `linear-gradient(rgba(8,9,10,.78) → .66)` | 保证前景对比度 |
| paper | `rgba(12,13,15,.28)` | 面板基色半透明 |
| paper2/3 | `rgba(12,13,15,.72)` / `rgba(22,24,27,.72)` | 霜玻璃面板 |
| ink / ink2 / ink3 | `#F7F7F5` / `#B3B6BB` / `#7D8186` | 与暗色主题同源，阅读对比不变 |
| line / line2 | `rgba(255,255,255,.14)` / `.22` | hairline 变为白透明 |
| accent | `#E0455A` | 同暗色 |

- **顶栏/底栏霜玻璃**：`blur(20px) saturate(140%)` + `rgba(12,13,15,.55/.62)` 底（Web 同源参数）
- **主题切换为三态循环**：浅色 → 深色 → 虚化 → 浅色（与 Web 端顶栏钮一致）
- **Compose 实现要点**：垫底层用 `Modifier.blur`/`RenderEffect`（API 31+）或预模糊位图；霜玻璃面板 API 31+ 用 `RenderEffect`，低版本回退半透明色 + 深色纱；垫底图从当前页代表图（collection 首图）解码 64px 小图后放大模糊，内存可控

不使用 Material 动态取色(Material You):品牌一致性优先于系统壁纸。

## 2. 字体(→ Compose `Typography`)

| 角色 | 字体 | 字号/行高 | 用途 |
|---|---|---|---|
| display | Serif(EB Garamond / Noto Serif SC)| 34sp / 1.08, ls -1.5% | 发现页刊头、写真详情标题 |
| headline | Serif | 24sp / 1.12 | 页面标题(写真/模特/收藏)|
| title | Serif | 17sp / 1.2 | 卡片标题、App 栏词标 |
| body | Sans(Roboto / 思源黑体)| 15sp / 1.55 | 简介正文 |
| meta | Sans | 13sp / 1.5, ink2 | 日期、张数、标签行 |
| micro | Sans | 11sp / 1.4, ls +2% | 底栏标签、计数、状态 |

衬线仅用于标题层;数字(计数、序号)用 Sans + `FontFeature.tabularFigures`。

## 3. 形状与间距

- 圆角:卡片 **2dp**(近乎直角,editorial),按钮/输入框 2dp,Chip 全圆角(胶囊,同 Web 标签胶囊)
- 无阴影 elevation=0;分层靠 hairline 边框(line)与 paper2 色阶
- 间距基准 4dp:页面水平边距 16dp,卡片间距 12dp(2 列网格),区块间距 32dp
- 触控目标 ≥48dp;底栏 80dp 高

## 4. 导航结构

悬浮胶囊导航栏(主流悬浮式):左右 14dp、距底 20dp、高 64dp、全圆角胶囊;
**液态玻璃材质**(Liquid Glass,四层叠加):
1. 背景折射:SVG `feDisplacementMap` 让玻璃后的内容产生透镜扭曲(Compose 对应 `RenderEffect` + RuntimeShader)
2. 基础磨砂:`blur(12px) saturate(170%) brightness(1.05)`
3. 边缘光:多层 inset 阴影(顶部高光/底部暗反/内发光)+ 1px 内描亮环
4. 镜面流光:115° 对角渐变 sheen(左上入光 → 右下回收)

激活态 = 10% 墨/白胶囊底 + 绯红图标 + 展开标签,未激活仅图标(ink3);按压 0.94 spring 回弹。

```
发现(Explore)  写真(Collections)  模特(Models)  收藏(Favorites)
```

- 「发现」「写真」页顶栏：透明 → 滚动后 paper + hairline 底线；词标 "Photo Collection" 衬线 17sp
- 模特/写真详情、灯箱为全屏推入(无导航栏)；详情页滚动到底部收起顶栏
- 列表内容底部预留 112dp(栏 64 + 底距 20 + 呼吸),滚动到底不被遮挡
- Compose 落地:API 33+ 用 `RuntimeShader`(AGSL)写折射+磨砂+边缘光;API 31+ 退化为 `RenderEffect` blur + 静态渐变 sheen;更低版本退化为半透明胶囊 + 投影

## 5. 页面清单与状态

| # | 页面 | 关键状态 |
|---|---|---|
| S1 | 发现 Explore | 精选轮播(hero)+ 最新写真 2 列流;空态/加载骨架(色块脉冲)|
| S2 | 写真列表 Collections | 2 列瀑布(StaggeredGrid)+ 筛选行(标签/模特/排序 Chip)+ 计数;筛选抽屉 BottomSheet |
| S3 | 写真详情 | 刊头(标题衬线 + 模特名 + 日期 + 标签胶囊)→ 2 列照片墙;收藏按钮 AppBar |
| S4 | 灯箱 Lightbox | 全屏黑、左右滑动、双指缩放、双击放大;顶栏 ×+序号,底栏 收藏/下载/写真名;点按切换 chrome 显隐 |
| S5 | 模特列表 Models | 2/3 头像 2 列 + 姓名 + 写真数 |
| S6 | 模特详情 | 顶部 2/3 大头像 + 简介 → 该模特写真横向卡列 |
| S7 | 收藏 Favorites | 三段 Tab(模特/写真/照片);照片段 3 列方图 |
| S8 | 登录 / 添加服务器 | 服务器地址 + 账密;衬线刊头;错误内联提示 |
| S9 | 设置 | 服务器管理、主题三态循环（浅/深/虚化）、语言（zh-CN/zh-TW）、下载位置 |
| S10 | 搜索 | 顶栏内嵌输入 + 热门标签 + 结果 2 列流(复用 S2 卡片)|

主题第四态「虚化」（Web 端 blur 主题）已纳入 V1：三态循环切换，实现要点见 Blur 虚化主题一节。

## 6. 核心组件

| 组件 | 规格 |
|---|---|
| CollectionCard | 2/3 图 + 下方 标题(Serif 15sp)+ meta(张数 · 日期 11sp ink3);按压态:图上 8% ink 蒙层 |
| ModelCard | 2/3 头像 + 姓名(Serif 15sp)+ "N 个写真"(micro)|
| TagChip | 胶囊 hairline 边框,`#Fashion` 形式,选中=ink 底 paper 字 |
| SectionHeader | 标题(Serif 20sp)+ 右侧 "查看全部 →" 文字链(accent)|
| FavoriteButton | 心形 24dp,描边 ink2 → 实心 accent,缩放 0.85→1 spring 动效 |
| EmptyState | 居中衬线标题 + meta 说明 + 文字按钮;配图用 1px 线框占位框 |
| 骨架屏 | paper2 色块,无 shimmer(编辑感,静默脉冲 1.2s)|

## 7. 动效(克制,单次编排)

- 页面切换:共享轴 X(forward/back),280ms,标准曲线
- 灯箱进入:从缩略图位置 fade-through;chrome 显隐 180ms fade + 8dp 位移
- 收藏:心形 spring(dampingRatio = MediumBouncy)
- 列表进入不逐卡入场(避免通用 AI 感),仅首屏一次 120ms 淡入

## 8. 图片加载策略(与 Web 端一致)

- 列表/卡片:`/t/400`(2/3 裁切)+ thumbhash 占位
- 详情照片墙:`/t/800`
- 灯箱 fit:`/t/1800`,双指放大时切换原图 `/media/...`
- Coil 全局 `ImageLoader`:附加 Auth 头、磁盘缓存 256MB、crossfade(120ms)

## 9. 明确不做(YAGNI)

- 管理端(仪表盘/采集控制台)——继续用 Web
- 平板双栏布局(V2 再说)
- 动态取色、Material You 图标
