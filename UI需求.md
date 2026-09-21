# 写真作品管理与展示 Web 应用

## 产品需求与 UI/UX 设计文档 V1.0

---

# 一、产品定位

## 1. 产品名称

暂定：

**写真作品库 / Photo Collection**

名称后续可调整。

---

## 2. 产品定位

本产品是一款以**模特写真作品展示与管理**为核心的 Web 应用。

核心信息结构：

**模特 → 写真作品 → 照片**

产品同时具备：

* 高质量写真作品展示
* 模特资料展示
* 写真作品管理
* 图片瀑布流浏览
* 全屏大图浏览
* 收藏
* 原图下载
* 批量下载
* 搜索
* 标签筛选
* 精选作品
* 用户个人中心
* 管理员内容管理
* 数据统计

产品不是传统意义上的图片 CMS，而是：

> **一个具有高级时尚视觉体验的数字写真作品库。**

核心体验应该更接近：

**Fashion Editorial / Photography Portfolio / Digital Archive**

而不是传统的：

**后台管理系统 / 图片管理器 / CRM**

---

# 二、目标用户

## 1. 普通用户

主要行为：

* 浏览作品
* 浏览模特
* 搜索内容
* 筛选内容
* 收藏模特
* 收藏写真
* 收藏照片
* 下载照片
* 批量下载写真
* 管理个人收藏

普通用户不能修改平台内容。

---

## 2. 管理员

主要行为：

* 管理模特
* 管理写真
* 上传照片
* 管理标签
* 设置精选作品
* 管理用户权限
* 查看基础数据

管理员负责平台内容维护。

系统暂不考虑多管理员体系。

---

# 三、权限体系

| 功能     | 普通用户 | 管理员 |
| ------ | ---: | --: |
| 登录     |    ✓ |   ✓ |
| 浏览模特   |    ✓ |   ✓ |
| 查看模特详情 |    ✓ |   ✓ |
| 浏览写真   |    ✓ |   ✓ |
| 查看照片   |    ✓ |   ✓ |
| 搜索     |    ✓ |   ✓ |
| 标签筛选   |    ✓ |   ✓ |
| 收藏模特   |    ✓ |   ✓ |
| 收藏写真   |    ✓ |   ✓ |
| 收藏照片   |    ✓ |   ✓ |
| 下载原图   |    ✓ |   ✓ |
| 批量下载   |    ✓ |   ✓ |
| 新增模特   |    — |   ✓ |
| 编辑模特   |    — |   ✓ |
| 删除模特   |    — |   ✓ |
| 新增写真   |    — |   ✓ |
| 编辑写真   |    — |   ✓ |
| 删除写真   |    — |   ✓ |
| 上传照片   |    — |   ✓ |
| 管理标签   |    — |   ✓ |
| 设置精选作品 |    — |   ✓ |
| 用户管理   |    — |   ✓ |
| 数据统计   |    — |   ✓ |
| 采集下载   |    — |   ✓ |

---

# 四、核心内容模型

## 1. 模特

一个模特可以拥有多个写真作品。

```text
Model
│
├── Profile
│
├── Collection 01
│   ├── Photo
│   ├── Photo
│   └── Photo
│
├── Collection 02
│   ├── Photo
│   ├── Photo
│   └── Photo
│
└── Collection 03
    ├── Photo
    ├── Photo
    └── Photo
```

---

# 五、模特信息

模特字段：

* 姓名
* 艺名
* 头像
* 性别
* 年龄
* 身高
* 三围
* 所属公司
* 标签
* 模特简介

## 信息展示规则

所有个人资料字段均为可选。

如果某个字段没有数据：

**前台完全不展示该字段。**

例如：

```text
Yang Chenchen

Female
168 cm
ABC Agency

Fashion
Portrait
Model
```

如果没有填写年龄、三围：

不要显示：

```text
年龄 —
三围 —
```

而是直接隐藏。

---

# 六、写真作品

每套写真作品包含：

* 封面
* 标题
* 模特
* 多张照片
* 日期
* 标签
* 精选状态

建议内部增加：

* 创建时间
* 更新时间
* 发布状态
* 排序权重

---

# 七、写真状态

写真支持以下状态：

### 草稿

管理员正在编辑。

普通用户不可见。

### 已发布

普通用户可以正常访问。

### 隐藏

内容保留，但普通用户无法从公开作品列表中发现。

管理员仍然可以管理。

---

# 八、首页：作品发现页

首页采用：

# **Discovery / 作品发现页**

不使用传统 Dashboard 作为用户首页。

首页重点是：

> **让用户快速发现优秀的模特和写真作品。**

---

## 首页结构

### Header

```text
LOGO

MODELS
COLLECTIONS

SEARCH

♡ Favorites

Profile
```

桌面端可以使用横向导航。

移动端使用：

```text
☰
LOGO
⌕
♡
```

---

# 九、首页视觉结构

## 1. Hero / Featured

首页顶部展示精选写真。

采用大尺寸视觉。

例如：

```text
┌──────────────────────────────────────────┐
│                                          │
│                                          │
│              LARGE IMAGE                 │
│                                          │
│                                          │
│                                          │
│       FEATURED COLLECTION                │
│       Collection Name                    │
│       Model Name                         │
│                                          │
└──────────────────────────────────────────┘
```

图片占据主要视觉区域。

文字尽量少。

---

## 2. Latest Collections

展示最新写真。

采用图片网格 / 不规则布局。

```text
LATEST COLLECTIONS

┌─────────┐ ┌──────────────┐
│         │ │              │
│ Photo   │ │              │
│         │ │              │
└─────────┘ │              │
            └──────────────┘

┌──────────────┐ ┌─────────┐
│              │ │         │
│              │ │ Photo   │
│              │ │         │
└──────────────┘ └─────────┘
```

---

## 3. Featured Models

展示精选/热门模特。

每个模特以代表照片为主。

显示：

* 头像/代表照片
* 姓名或艺名
* 写真数量
* 标签

---

## 4. Explore

可以提供：

* Browse Models
* Browse Collections
* Browse Tags

作为进一步探索入口。

---

# 十、模特列表

URL/页面概念：

**Models**

主要作用：

> 发现和浏览模特。

---

## 模特卡片

推荐采用大图片设计：

```text
┌──────────────┐
│              │
│              │
│     PHOTO    │
│              │
│              │
└──────────────┘
Yang Chenchen
12 Collections
```

Hover 时可以显示：

* 收藏
* 写真数量
* 标签

---

## 筛选

支持：

* 搜索
* 性别
* 标签
* 所属公司
* 排序

排序可以包括：

* 推荐
* 最新
* 名称

---

# 十一、模特详情

模特详情是整个产品的重要页面。

目标：

> **让用户感觉自己正在浏览一本数字时尚杂志中的模特档案。**

---

## 页面结构

### Hero

大尺寸模特照片。

可以采用：

```text
┌──────────────────────────────────────────┐
│                                          │
│                                          │
│               MODEL IMAGE                │
│                                          │
│                                          │
└──────────────────────────────────────────┘

Yang Chenchen
♡
```

---

## Profile

显示存在的数据：

```text
Yang Chenchen

Female
168 cm
ABC Agency

Fashion
Portrait
Editorial

About

Lorem ipsum...
```

不要使用传统表格形式。

---

## Collections

下面展示该模特所有写真。

```text
COLLECTIONS

[Collection 01]
[Collection 02]
[Collection 03]
[Collection 04]
```

每套写真展示：

* 封面
* 标题
* 日期
* 图片数量
* 标签
* 收藏按钮

---

# 十二、写真列表

页面名称：

**Collections**

核心功能：

> 浏览整个作品库。

---

## 展示方式

默认：

**Masonry / 瀑布流**

原因：

写真图片比例可能不同。

相比固定比例卡片，瀑布流更适合摄影作品。

---

## 写真卡片

```text
┌──────────────┐
│              │
│              │
│    COVER     │
│              │
└──────────────┘
Collection Name
Model Name
♡
```

Hover 可以出现：

* 收藏
* 查看
* 图片数量

---

# 十三、写真详情

写真详情以**图片为第一视觉主体**。

页面顶部：

```text
Collection Name

Model Name
2026.09.17

#Fashion #Portrait
```

然后直接进入照片瀑布流。

---

## 照片布局

桌面端：

4～6 列动态布局。

Tablet：

3～4 列。

Mobile：

2 列。

---

# 十四、照片大图浏览

点击任意照片进入 Lightbox。

功能：

* 全屏
* 上一张
* 下一张
* 缩放
* 收藏
* 下载
* 当前序号

例如：

```text
                         ×

             ┌─────────────────┐
             │                 │
             │                 │
             │      PHOTO      │
             │                 │
             │                 │
             └─────────────────┘

                  12 / 128

          ♡ Favorite     ↓ Download
```

支持键盘：

* ← 上一张
* → 下一张
* ESC 关闭

移动端支持：

* 左右滑动
* 双指缩放

---

# 十五、收藏系统

用户可以收藏三种对象：

### 收藏模特

```text
My Favorites
└── Models
```

### 收藏写真

```text
My Favorites
└── Collections
```

### 收藏照片

```text
My Favorites
└── Photos
```

---

# 十六、个人中心

用户个人中心包含：

```text
Profile

My Favorites
├── Models
├── Collections
└── Photos

Settings
Logout
```

不需要复杂的社交系统。

---

# 十七、下载功能

用户支持：

### 单张下载

在照片大图页面下载。

### 批量下载

在写真详情页：

```text
Download Collection
```

下载整套写真。

---

## 下载体验

对于大量图片，不建议浏览器逐张下载。

建议后端生成 ZIP：

```text
Download Collection
        ↓
Preparing...
        ↓
ZIP generated
        ↓
Download
```

大规模写真需要考虑：

* ZIP 生成
* 文件大小
* 超时
* 临时下载地址
* 下载权限
* 存储压力

---

# 十八、搜索

全局搜索入口位于 Header。

支持：

```text
Search...
```

搜索对象：

* 模特
* 艺名
* 写真标题
* 标签
* 所属公司

---

## 搜索结果

建议按照类型分组：

```text
SEARCH RESULTS

Models
────────────
Model A
Model B

Collections
────────────
Collection A
Collection B

Tags
────────────
#Fashion
#Portrait
```

---

# 十九、标签系统

标签可以绑定：

* 模特
* 写真

例如：

```text
Fashion
Portrait
Editorial
Outdoor
Studio
Beach
Cosplay
```

标签页面：

```text
#Fashion

128 Collections
32 Models
```

下面展示相关内容。

---

# 二十、精选作品

系统增加：

**Featured / 精选**

管理员可以将写真设置为精选。

精选作品可以出现在：

* 首页 Hero
* 首页 Featured Collections
* 推荐区域

精选不是新的内容类型，只是一个展示属性。

---

# 二十一、管理员后台

管理员后台与用户端视觉可以保持统一设计语言，但信息密度可以更高。

---

## Dashboard

显示：

```text
MODELS
328

COLLECTIONS
2,481

PHOTOS
126,382

USERS
5,284
```

以及：

* 新增写真
* 新增模特
* 收藏量
* 下载量
* 用户数量
* 内容增长趋势

---

# 二十二、模特管理

管理员：

* 查看
* 搜索
* 新增
* 编辑
* 删除

表格可以展示：

```text
Avatar
Name
Company
Collections
Created
Status
Actions
```

---

# 二十三、新增 / 编辑模特

表单字段：

```text
Name
Stage Name
Avatar

Gender
Age
Height
Measurements
Company

Tags

Bio
```

管理员可以上传头像。

保存后进入模特详情。

---

# 二十四、写真管理

管理员可以：

* 创建写真
* 编辑写真
* 删除写真
* 发布
* 隐藏
* 设置精选
* 修改封面
* 管理照片
* 修改照片顺序

---

# 二十五、新增写真

创建流程：

```text
Step 01
选择模特

↓

Step 02
填写写真信息

Title
Date
Tags

↓

Step 03
上传照片

↓

Step 04
选择封面

↓

Step 05
调整照片顺序

↓

Step 06
保存 / 发布
```

---

# 二十六、图片上传

必须支持：

### 批量上传

一次选择大量照片。

### Drag & Drop

拖拽上传。

### 上传进度

```text
Uploading

████████████░░░░ 78%

124 / 160
```

### 上传后管理

管理员可以：

* 删除
* 排序
* 设置封面
* 查看尺寸
* 查看文件大小

---

# 二十七、用户管理

管理员可以：

* 查看用户
* 创建用户
* 编辑用户
* 禁用用户
* 删除用户
* 修改角色

角色只有：

```text
Admin
User
```

暂不考虑多级管理员。

---

# 二十八、数据统计

管理员 Dashboard 提供基础统计。

统计：

* 模特数量
* 写真数量
* 图片数量
* 用户数量
* 收藏数量
* 下载数量

不记录：

**单张照片浏览次数。**

也不需要复杂的用户行为追踪。

---

# 二十九、写真采集下载（管理员）

管理员后台专属的内容采集模块。系统定时自动采集源站最新写真，自动完成下载、校验、解压、归档；管理员也可以手动提交单个写真详情页链接。

普通用户不可见、不可用（见「三、权限体系」）。

---

## 数据来源

采集源为 buondua.com。写真详情页 URL 形如：

```text
https://buondua.com/<slug>-<序号>
https://buondua.com/yeha-yeha-school-nurse-219-photos-6746d2e27adfd5224746c047dfc7b9fe-56616
```

* URL 末尾数字为站点全局唯一序号
* 序号随发布时间递增，作为增量采集与去重的唯一判据
* 同一写真可能出现不同 slug 变体（含中间哈希段），以序号为准

---

## 两种入口

### 定时自动采集（主要方式）

系统内置调度器，按配置周期抓取站点最新列表：

* 从最新列表页顺序读取，解析详情页 URL 与序号
* 序号不在已处理历史中 → 视为新写真，进入下载队列
* 已处理（完成、跳过、失败）的序号记入历史，不重复排队
* 采集周期可配置，默认每 6 小时；支持手动「立即执行一轮」
* 单轮抓取页数可配置，默认 1 页；整页均为已处理序号时提前停止

### 手动提交（辅助方式）

管理员在后台粘贴单个详情页 URL 提交下载。

* 提交时校验 URL 格式与序号
* 与自动采集共用同一队列、历史与过滤规则

---

## 处理流程

```text
解析详情页（写真标题 / 模特名 / 解压密码 / 网盘短链）
  ↓
标题过滤（白名单 / 黑名单，未通过则跳过并记录）
  ↓
解析网盘短链 → 获取直链
  ↓
下载压缩包（流式，支持断点续传）
  ↓
SHA256 校验
  ↓
解压（密码取自详情页）
  ↓
归档到下载目录
  ↓
删除压缩包
```

---

## 白名单 / 黑名单

对解析出的写真标题做关键词匹配：

```text
黑名单命中        → 拒绝（优先级最高）
白名单非空且未命中 → 拒绝
白名单命中        → 允许
白名单为空        → 不限制
```

* 关键词在后台维护，支持增删，匹配忽略大小写
* 自动采集与手动提交统一执行过滤
* 被过滤的任务标记「已跳过」并记录命中的关键词

---

## 目录规则

```text
<下载目录>/<模特名>/<写真标题>/
└── 001.jpg ... 061.jpg
```

* 模特名与写真标题取自详情页解析结果，路径非法字符替换为 `-`
* 解压校验成功后删除压缩包，不保留原包
* 目标目录已存在同名写真 → 跳过下载，任务标记「已存在」
* 模特名无法解析时 → 归入「未分类」目录（目录名可配置）

---

## 配置项

| 配置 | 说明 | 默认 |
| --- | --- | --- |
| 下载目录 | 归档根目录 | 必填 |
| 白名单 | 标题关键词列表 | 空 |
| 黑名单 | 标题关键词列表 | 空 |
| 采集周期 | 自动采集间隔 | 每 6 小时 |
| 单轮页数 | 每轮最多抓取的列表页数 | 1 |
| 未分类目录名 | 模特名缺失时的归档目录 | `未分类` |

---

## 任务管理

* 任务列表展示：状态、进度、序号、写真标题、模特名、失败原因、时间
* 状态：`排队 / 解析中 / 下载中 / 解压中 / 完成 / 已存在 / 已跳过 / 失败`
* 串行执行：同一时间只运行一个任务，其余按提交顺序排队
* 失败任务支持手动重试；失败不阻塞队列
* 下载进度按已接收字节数实时更新（文件大小来自网盘接口）

---

## 运行约束

* 部署目标为 NAS，无图形界面：采集、下载、解压全程不依赖浏览器
* 对源站保持低频访问：受采集周期与单轮页数约束
* 归档目录为独立素材库；照片入库到平台（模特 / 写真体系）走后续导入流程，不在本章范围

---

# 三十、视觉设计系统

## 核心关键词

**Luxury / Fashion / Editorial / Minimal / Modern / Digital Archive**

---

## 视觉方向

参考：

[Buondua](https://buondua.com/?utm_source=chatgpt.com)

[V2PH 模特页面](https://www.v2ph.com/actor/Yang-Chenchen?hl=zh-Hant&utm_source=chatgpt.com)

但不直接复制参考网站。

目标是在其内容组织和图片浏览基础上，进一步提升：

* 排版
* 间距
* Typography
* 动效
* 交互
* 信息层级
* 响应式体验
* 深浅色主题

---

# 三十一、设计语言

## Light Theme

关键词：

**White / Off-white / Editorial / Clean**

建议：

* 白色背景
* 米白辅助色
* 深色文字
* 细边框
* 极少阴影

---

## Dark Theme

关键词：

**Black / Gallery / Immersive**

建议：

* 黑色/深灰背景
* 浅色文字
* 图片视觉突出
* UI 尽量弱化

---

# 三十二、Typography

建议采用现代无衬线字体作为主要 UI 字体。

标题可以适当加入：

* 高级衬线字体
* Editorial Typography
* 大字号标题

例如：

```text
COLLECTIONS

Photography Archive
```

通过字体对比制造时尚感。

---

# 三十三、UI 特征

避免：

* 大量圆角 Card
* 强烈阴影
* 传统蓝色后台
* 大量按钮
* 过度渐变
* 五颜六色的标签
* 复杂 Dashboard

强调：

* 留白
* 大图
* Typography
* 黑白关系
* 精细网格
* 微交互
* 极简导航

---

# 三十四、动效

整体动画需要：

**克制、快速、自然。**

建议：

### 图片 Hover

轻微：

* Scale
* Opacity
* 信息淡入

### 页面切换

轻微 Fade / Slide。

### Lightbox

使用平滑的：

* Fade
* Scale

避免复杂动画影响图片浏览。

---

# 三十五、响应式设计

## Desktop

主要体验。

建议：

* 4～6 列瀑布流
* 大尺寸 Hero
* 更宽松的留白
* 多栏布局

---

## Tablet

* 3～4 列
* 缩小页面边距
* 保留完整导航

---

## Mobile

* 2 列瀑布流
* Header 简化
* Bottom Navigation 可选
* 模特详情改为纵向布局
* 图片全屏浏览优先

---

# 三十六、性能要求

预计数据规模：

> 几百模特
> 几万～几十万张照片

因此图片系统必须按照大型图片库设计。

---

## 图片处理

至少准备：

```text
Original
    ↓
Large
    ↓
Medium
    ↓
Thumbnail
```

前台默认使用缩略图/适合当前显示尺寸的图片。

只有：

**大图查看 / 下载**

才加载原图。

---

## 必须支持

* Lazy Loading
* Responsive Images
* WebP / AVIF
* CDN
* 浏览器缓存
* 图片压缩
* 图片缩略图
* 分页/无限滚动
* 虚拟列表
* 数据库索引
* 搜索索引

---

# 三十七、安全与访问控制

由于首页内容要求：

> **必须登录后访问**

因此：

未登录：

```text
Login
```

登录后：

```text
Discovery
Models
Collections
Favorites
Profile
```

所有作品、模特、照片页面均需要登录权限。

后台必须进行 Admin Role 权限验证。

---

# 三十八、异常状态

所有核心页面需要设计：

### Loading

图片加载骨架屏。

### Empty

例如：

```text
No collections yet.
```

### Search Empty

```text
No results found.
```

### Error

```text
Something went wrong.
Please try again.
```

### Permission

```text
You don't have permission to access this page.
```

---

# 三十九、页面清单

## 用户端

### Authentication

1. Login

### Discovery

2. Discovery / 首页
3. Search
4. Search Results
5. Tags

### Models

6. Models
7. Model Detail

### Collections

8. Collections
9. Collection Detail
10. Photo Lightbox

### User

11. Favorites
12. Profile
13. Settings

---

## 管理端

14. Admin Dashboard
15. Model Management
16. Create Model
17. Edit Model
18. Collection Management
19. Create Collection
20. Edit Collection
21. Photo Management
22. User Management
23. Tag Management
24. 采集下载

---

# 四十、核心用户流程

## 用户发现作品

```text
Login
 ↓
Discovery
 ↓
Featured / Latest
 ↓
Collection
 ↓
Photo
 ↓
Favorite / Download
```

---

## 用户发现模特

```text
Login
 ↓
Models
 ↓
Model Detail
 ↓
Collections
 ↓
Collection Detail
 ↓
Photo
```

---

## 搜索

```text
Search
 ↓
Keyword
 ↓
Search Results
 ↓
Model / Collection
 ↓
Detail
```

---

## 管理员创建写真

```text
Admin Login
 ↓
Admin Dashboard
 ↓
Collections
 ↓
Create Collection
 ↓
Select Model
 ↓
Input Metadata
 ↓
Upload Photos
 ↓
Set Cover
 ↓
Sort Photos
 ↓
Publish
```

---

---

## 管理员采集写真

```text
Admin Login
 ↓
Admin Harvest
 ↓
Auto Scan / Submit URL
 ↓
Queue（串行）
 ↓
Download → Verify → Extract
 ↓
Archive by Model / Title
```

---

# 四十一、产品设计优先级

按照重要程度排序：

### P0

核心产品体验：

* 登录
* 作品发现页
* 模特列表
* 模特详情
* 写真列表
* 写真详情
* 瀑布流
* 大图浏览
* 搜索
* 收藏
* 下载
* 管理员 CRUD
* 批量上传

### P1

增强体验：

* 精选作品
* 标签系统
* 用户中心
* 深色/浅色主题
* 批量下载
* 图片排序
* 草稿/隐藏状态
* 写真采集下载（管理员）

### P2

后续增强：

* 更丰富的数据统计
* 推荐算法
* 更复杂的内容发现机制
* 高级筛选
* 更多用户个性化功能

---

# 四十二、最终产品体验目标

整个产品应该形成一种明确的视觉和使用感受：

> **打开网站，首先看到的是照片，而不是后台功能。**

> **进入模特页面，感觉像是在浏览一本数字时尚杂志中的模特档案。**

> **进入写真页面，感觉像是在浏览一个高质量摄影展览。**

> **管理功能隐藏在后台，不影响普通用户的视觉体验。**

因此最终设计原则：

**Photo First**

**Minimal UI**

**Editorial Layout**

**Premium Typography**

**Immersive Browsing**

**Fast Search**

**Simple Management**

---

# 四十三、最终设计关键词

```text
Fashion
Editorial
Photography
Minimal
Luxury
Modern
Premium
Digital Archive
Visual First
Immersive
Clean
Elegant
```

最终产品应该是：

**「一个高级的数字写真作品档案馆」**

而不仅仅是：

**「一个写真图片管理后台」**。

---

# 四十四、国际化(i18n)— 简体中文 / 繁體中文

> 状态:已实装(2026-09),全套 87 项 pytest 通过 + 浏览器实测。

## 方案要点

- **混合 msgid**:模板/JS 中的英文原文(或既有中文消息原文)直接作 msgid;`app/i18n.py` 内置 `STRINGS` 翻译表(330+ 条),回退链 `当前语言 → zh-CN → msgid 原文`。
- **语言范围**:`zh-CN`(简体中文,默认)/ `zh-TW`(繁體中文);`normalize_lang` 把 zh-tw / zh-hant / zh-hk 归一为 `zh-TW`,zh / zh-cn / zh-hans / zh-sg / cmn 归一为 `zh-CN`。
- **不译内容**:品牌 "Photo Collection" wordmark;harvest 状态码(queued / parsing / downloading / extracting / failed / skipped)与角色(user / admin);搜索建议 fallback 标签。

## 解析优先级与持久化

1. 登录用户 `users.language`(个人设置,空 = 跟随站点);
2. cookie `pb_lang`(一年,HttpOnly 关闭以便调试);
3. settings 表 `site.language`(管理员在 设置页 的"默认语言"下拉设置);
4. 默认 `zh-CN`。

## 路由与 UI

- `POST /language`(公开路由):表单按钮 `name=lang` + hidden `next`;已登录同时写入 `users.language`。
- 个人中心"语言"设置行、登录页迷你切换器、管理设置页"默认语言"下拉。
- 中间件在请求早期(ContextVar)set_language,模板 `t()` / `lang()` 可用;`PB_BOOT.i18n` 注入全量映射,`PC.t(key, vars)` 供 JS 用(头部/抽屉/页脚/搜索层/lightbox/toast/采集轮询)。

## 实施清单

- `app/i18n.py`:`STRINGS` / `translate` / `tf` / `normalize_lang` / `js_strings` / `t` 别名。
- 中间件语言解析(`app/main.py`);`templating.boot_json` 注入 `lang` + `i18n`;Jinja 全局 `t` / `lang` / `LANGUAGES`。
- 全部 19 个模板 + `app.js`(~50 处)+ `app.css`(`lang-switch` 系列)。
- 服务端消息构造时翻译:登录错误、admin flash(已保存 / 密码至少 6 位 / 用户名已存在 / 不能删除自己 / slug 已存在)、harvest 手动提交与扫描结果;后台 pipeline 错误保持 zh-CN 原文(数据而非 UI)。
- 测试:`tests/test_i18n.py`(normalize、回退链、cookie 切换、公开路由、持久化、boot_json、语言 UI 存在)。
