# Photo Collection Android — 系统架构与技术栈 V1

> UI 规格见 `design.md`。本文档定义安卓客户端的分层、技术选型与服务端配套改动,
> 是工程搭建的直接依据。技术栈版本为成稿时的稳定线,以 `libs.versions.toml` 实际解析为准。

## 0. 现状与约束(设计依据)

- 服务端已存在且不可大改:FastAPI + SQLAlchemy(SQLite)+ Jinja SSR,`/media` 原图与 `/t/{w}x{h}` 缩略图管线完善(信号量限并发)
- 认证是 **Cookie Session**(`pb_session`,HttpOnly,argon2 密码,session 表已存 token_urlsafe)——浏览器友好,移动端不适用
- 已有 JSON API:`/api/favorites`(读写)、`/api/search`(登录);其余页面全是 SSR
- `photos` 表有 `width/height`(可空)、`published_at` 是字符串、`source_serial` 供浏览器联动
- 单人自托管场景:用户个位数,内网/VPN 访问为主;无匿名浏览,全部内容需登录

由此推出的核心结论:**客户端薄、服务端增一层薄移动 API,不引入任何新基础设施**(不加 Redis、不加队列、不上传协议)。

## 1. 总览

```
┌────────────────────────── Android App (Kotlin) ──────────────────────────┐
│  ui/        Compose 屏幕 ×10 + PhotoTheme(light/dark/blur)+ 悬浮玻璃导航  │
│    │  UiState(StateFlow)↑↓ 事件(UDF,单向数据流)                        │
│  data/      ViewModel ↔ Repository(内存缓存 + 乐观更新)                  │
│    │                        │                                            │
│  core/network   Retrofit + OkHttp(Bearer 拦截器,401 统一处理)           │
│  core/img       Coil 3(自定义 ImageLoader:鉴权头 + 磁盘缓存)           │
│  core/storage   DataStore(服务器地址/token/语言/主题,多服务器档案)       │
└────────────┬─────────────────────────┬───────────────────────────────────┘
      JSON /api/mobile/*            图片 /t/*、/media/*
┌────────────┴─────────────────────────┴───────────────────────────────────┐
│  FastAPI 服务端:新增 routers/mobile_api.py(薄层,复用现有 ORM/服务)      │
│  认证:复用 sessions 表,token = session id,走 Authorization: Bearer      │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. 技术栈

| 层 | 选型 | 理由 / 落选者 |
|---|---|---|
| 语言 | Kotlin 2.x,Coroutines + Flow | 唯一理性选项;Flow 承载 UDF |
| UI | Jetpack Compose(BOM 最新稳定)+ Material3 基件 | design.md 已定;M3 只作基件,视觉完全走自研 PhotoTheme(禁动态取色) |
| 导航 | navigation-compose 2.8+,**类型安全路由**(kotlinx.serialization) | 编译期路由参数;过渡动画对应 design.md 共享轴 X |
| 依赖注入 | Hilt(KSP) | 与 ViewModel/Compose 一等集成,编译期校验;备选手动 AppContainer,规模大了再迁不迟 |
| 网络 | Retrofit + OkHttp + kotlinx.serialization | 官方 converter-kotlinx-serialization;DTO 与路由共用 `@Serializable` |
| 图片 | Coil 3 + **telephoto**(zoomable-image-coil3) | Coil 复用 OkHttp 鉴权头与磁盘缓存;telephoto 提供灯箱子采样(大图 tile 解码)+ 缩放手势,Immich 同类方案 |
| 背景虚化/玻璃 | Modifier.blur(RenderEffect,API 31+);**haze**(chrisbanes)做"背后内容实模糊";AGSL RuntimeShader 做 API 33+ 折射增强 | design.md 玻璃三要素:折射/磨砂/边缘光,对应三条实现路径 |
| 本地存储 | DataStore(Proto) | 服务器档案、token、主题、语言;**V1 不引入 Room**(见 §8 YAGNI) |
| 下载 | DownloadManager + HTTP 头带 token | 系统级通知/断点,零后台代码;不引 WorkManager |
| 测试 | JUnit + Turbine + MockWebServer;Compose 规则做冒烟 | 先覆盖 Repository/DTO 与 ViewModel 状态机 |
| 构建 | Gradle KTS + version catalog;ktfmt | 单模块 |

**SDK 定位:minSdk 31(Android 12),target 最新。**
理由:虚化主题与玻璃效果依赖 RenderEffect(31+)/AGSL(33+),design.md 的核心视觉就是这些;
31 已覆盖 2021 年末以来设备,个人自托管 App 无需为老设备牺牲主视觉。
若未来需 minSdk 29:玻璃退化为半透明胶囊 + 投影,blur 主题退化为静态色块,架构不变(见 §7 渐进增强)。

## 3. 工程结构(单模块,按层分包)

```
app/src/main/kotlin/dev/jinsfoni/photobook/
├── PhotoBookApp.kt            # @HiltAndroidApp:全局 ImageLoader、通知渠道
├── MainActivity.kt            # enableEdgeToEdge + PhotoTheme + NavHost
├── core/
│   ├── design/                # ← design.md 的直接映射
│   │   ├── theme/             # PhotoColorScheme(light/dark/blur)、Type、Shape
│   │   ├── glass/             # GlassSurface(haze 底栏/顶栏)、RefractionModifier(AGSL)
│   │   └── components/        # CollectionCard、ModelCard、TagChip、FavoriteButton、骨架屏…
│   ├── network/
│   │   ├── Api.kt             # Retrofit 接口(@Serializable DTO 同文件内聚)
│   │   ├── AuthInterceptor.kt # 注入 Bearer;401 → 发 AuthEvent
│   │   └── ServerManager.kt   # 当前服务器档案 → 动态 baseUrl(Retrofit 多实例缓存)
│   ├── img/                   # Coil ImageLoader:磁盘缓存 256MB、crossfade(120ms)、鉴权头
│   └── storage/               # DataStore:ServerProfile(id,baseUrl,token)/ 语言 / 主题
├── data/
│   └── repo/                  # AuthRepo、CollectionsRepo、ModelsRepo、FavoritesRepo、SearchRepo
│                              # 返回 Result<T>;统一 AppError(Network/Auth/Server/Parse)
└── ui/
    ├── nav/                   # @Serializable 路由 + NavHost + 过渡
    └── explore/ … search/     # 每屏:Screen.kt(纯函数)+ ViewModel.kt + UiState.kt
```

要点:

- **ui 层零业务**:Screen 只接 `UiState` + lambda;ViewModel 只调 Repo;IO 全部在 Repo(Dispatchers.IO)
- **数据流单向**:服务端是唯一事实源;FavoritesRepo 持有 `StateFlow<Set<FavKey>>` 内存缓存,收藏点击乐观更新 + 失败回滚并提示(不引入离线队列)
- 401 统一处理:拦截器广播 → 导航回 S8 登录并清 token,业务层无感知

## 4. 服务端配套:`app/routers/mobile_api.py`(薄层)

复用现有 ORM、`auth.create_session/verify_password`、`services.media.thumb_url`,预计 <400 行:

| 端点 | 说明 |
|---|---|
| `POST /api/mobile/auth/login` | `{username,password}` → `{token, user}`;token 即 sessions.id,TTL 沿用 `session_ttl_hours`(14 天);`POST /auth/logout` 销毁 |
| `GET /api/mobile/discover` | 发现页一次取全:featured 轮播 + 最新写真 + featured 模特 + 统计(对齐 `_collection_payload/_model_payload`) |
| `GET /api/mobile/collections` | `limit/offset/tag/model/sort`;返回卡片 + total |
| `GET /api/mobile/collections/{slug}` | 详情 + `photos[]`(idx、w、h、placeholder、favKey) |
| `GET /api/mobile/models`、`/models/{slug}` | 列表 / 详情(含该模特写真卡列) |
| `GET /api/mobile/search?q=` | 复用 search_api 逻辑,加 Bearer 支持 |
| `GET/POST /api/mobile/favorites` | 现有 favorites_api 泛化:`require_login` 拆出 Bearer 变体 |

约束(接口纪律,见 api-and-interface-design):

- **统一错误体** `/api/mobile/*` 一律 `{"error":{"code","message"}}` + 正确状态码(401 未认证 / 403 非公开内容 / 404 / 422 / 500),全局 exception handler 落地;code 机器可读(`AUTH_FAILED`、`NOT_FOUND`…)
- **列表必带分页参数**,响应 `{data, total, limit, offset}`;字段只加不改(可加性)
- photo 增 `placeholder`:16×9 微缩 WebP data-URI(Pillow 入库时生成,~300B,Coil 占位图)——替代 thumbhash,零客户端解码库依赖
- `width/height` 入库时补全(现可空),灯箱/瀑布流布局依赖
- 移动 API **只读**(除登录/收藏/登出);写操作仍归 Web 管理端
- 媒体复用 `/t/*` 与 `/media/*`(公开路径,现有中间件已放行);若未来收紧,Coil 请求自动带 Bearer 头

## 5. 认证与多服务器

- **ServerProfile**:`{id, baseUrl, token, username, avatar}`;支持添加/切换/删除多个服务器(对齐 S8/S9 设计)
- `ServerManager` 为每个 baseUrl 惰性建 Retrofit/OkHttp/Coil ImageLoader 三元组(缓存 2-3 个实例);切换服务器 = 切换依赖集 + 清内存缓存,Coil 磁盘缓存按 URL 天然隔离
- token 存 DataStore(应用私有目录);自托管场景不引入 Keystore 加密层,文档注明风险与缓解(设备锁屏 + 不 root)
- 明文 HTTP:自托管内网常见 `http://192.168.x.x`,networkSecurityConfig 允许 cleartext;对外部署建议反代 HTTPS(README 说明)
- 登录流程:S8 输入地址 → `GET /api/mobile/ping`(200 即可达,防错写端口)→ login → 存档 → 进 S1

## 6. 图片管线(与 design.md §8 对齐)

| 场景 | URL | 说明 |
|---|---|---|
| 卡片/列表 | `/t/400/{path}.webp` | placeholder data-URI 占位 → crossfade |
| 详情照片墙 | `/t/800` | 2 列瀑布,`w/h` 算宽高比占位,零跳动 |
| 灯箱 fit | `/t/1800` | telephoto 显示 |
| 灯箱放大 | `/media/{path}` 原图 | telephoto 子采样 tile 解码,4GB 上限图片可控内存 |

- Coil `ImageLoader` 全局单例:鉴权头拦截器、磁盘缓存 256MB、`respectCacheHeaders(false)`(缩略图内容寻址,永不失效)、内存缓存默认
- 内存压力:灯箱打开时列表自动停驻加载(Coil 生命周期天然支持)

## 7. 主题与玻璃效果实现路径

| 设计元素 | 实现 |
|---|---|
| PhotoTheme(light/dark/blur) | `PhotoColorScheme` 三实例;blur 主题 = haze 场景:代表图 `Modifier.blur(42.dp·px 等效) + scale(1.35f)`(design.md 教训:必须盖住 blur 边缘渐隐)+ 深纱渐变 |
| 悬浮胶囊导航玻璃 | **haze** `hazeSource(根内容) + hazeEffect(胶囊)`:背后内容真模糊(blur 3dp 等效 + 饱和),叠 sheen 渐变;浅色薄白/深·虚深烟材质按主题切换 |
| AGSL 折射(API 33+ 增强) | `RefractionModifier`:RuntimeShader 实现位移扰动(feDisplacementMap 对应),`Build.VERSION` 门控;31-32 只有磨砂+流光,不影响布局 |
| 状态栏三类(design.md §4) | `enableEdgeToEdge`;普通页 `WindowInsets.statusBars` padding;媒体头部/灯箱全出血 + 白字 + 轻纱 |

## 8. 明确不做(V1 YAGNI)

- **Room/离线浏览**:自托管 + VPN 常在线;Coil 磁盘缓存已兜住图片,JSON 列表体量小
- Paging3:单库写真数百级,`limit/offset` 参数先占位,数据量到了再加
- 多模块化:单模块 + 包分层,规模(万行)未到拆分收益点
- WorkManager、推送、云端同步、Wire/GraphQL、动态取色
- 加密存储(Keystore):个人自托管场景暂不需要

## 9. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M0 骨架 | 工程 + version catalog + PhotoTheme/组件 + 玻璃底栏壳(haze) | 空壳 App 跑通三主题切换 |
| M1 主链路 | mobile_api.py(登录/discover/collections/detail)+ S8→S1→S2→S3→S4 | 登录后浏览 + 灯箱缩放收藏全通 |
| M2 内容闭环 | models/detail + favorites(S7 读写同步)+ search(S10) | 收藏三段 Tab 与 Web 端一致 |
| M3 体验补全 | settings(S9 多服务器/语言/主题)+ DownloadManager 下载 + 骨架屏/空态 | 全 10 屏可用 |
| M4 增强 | AGSL 折射、缓存/内存调优、ktfmt/CI(assemble + 单测) | API 33 真机玻璃折射可见 |

## 10. 测试策略

- DTO/Retrofit:MockWebServer 契约测试(错误体、分页、401 路径)
- ViewModel:Turbine 断言 UiState 流(加载/空态/错误/乐观回滚)
- Repository:假 Api 手写 Fake(不引 mockk 全家桶,接口少)
- Compose:每屏 `createComposeRule` 冒烟(渲染不崩 + 关键节点存在);像素级验证靠设计稿阶段已完成的 Playwright 流程,不在端上重复
