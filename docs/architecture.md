# PhotoBook 前后端架构设计

> 版本 v1.0.0 · 依据《UI需求.md》43 章、现有静态 UI 设计稿(8 页面 + 设计系统)、NAS 部署约束

## 一、总体架构

单体应用 + 内嵌采集 Worker,单容器部署:

```
┌─────────────────────────────────────────────────┐
│                 NAS (Docker 容器)                 │
│                                                 │
│   FastAPI (uvicorn)                             │
│   ├─ 用户端页面 ──── Jinja2 SSR(复用现有设计系统)   │
│   ├─ 管理端页面 ──── Jinja2 SSR + fetch 局部增强    │
│   ├─ JSON API /api/* ── 收藏/管理操作/任务进度      │
│   ├─ 媒体服务 /media/* ─ 原图 + 按需缩略图缓存      │
│   └─ 静态资源 ──────── app.css + JS 模块          │
│                                                 │
│   Harvest Worker(后台线程,串行)                   │
│   ├─ APScheduler 定时扫描 buondua 列表            │
│   ├─ curl_cffi 采集(已验证链路)                   │
│   └─ 7zz 解压 + SHA256 校验 + 归档                │
│                                                 │
│   SQLite (WAL) ── 业务数据 + 任务队列 + 配置        │
└─────────────────────────────────────────────────┘
     │              │                │
   /data         /library         /media
   SQLite文件    采集归档库         平台图片库+缩略图缓存
              (模特/写真/照片)
```

## 二、技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | Python 3.12 + FastAPI + Uvicorn | 采集核心 curl_cffi 是 Python 生态独有(TLS 指纹模拟),换语言 = 重做已验证链路;异步原生,自动 OpenAPI |
| 模板 | Jinja2 | 现有静态 HTML 直接参数化移植,设计系统 1:1 保留 |
| 数据库 | SQLite(WAL)+ SQLAlchemy 2.0 | 单机个人库,百万行元数据在舒适区;零运维,备份 = 拷一个文件;将来迁 PostgreSQL 只换连接串 |
| 配置 | Pydantic Settings | 下载目录/黑白名单/采集周期,类型安全,支持 .env 覆盖 |
| 调度 | APScheduler | 进程内定时器 + 串行队列足够,不引 Celery/Redis |
| 采集 HTTP | curl_cffi(外网)+ httpx(内网) | 外网采集必须 TLS 指纹模拟;内部请求用标准异步库 |
| 解压 | 7zz 子进程(容器内装 p7zip) | 实测唯一能正确处理 RAR 加密头的工具 |
| 图像处理 | Pillow | 需求 §36 要求服务端裁剪到版位尺寸、多档 srcset |
| 密码哈希 | argon2-cffi | 现代标准 |
| 前端 | 无框架、无构建链,ES Modules + JSDoc | 见第四节 |
| 部署 | Docker Compose(python:3.12-slim + p7zip) | NAS Container Manager 直接跑;数据全部走 volume |

### 否决项及原因

- **Django**:自带 admin 的 UI 与设计语言冲突,ORM/认证之外的重量(迁移体系、中间件)对单人项目是负担;采集 worker 仍要自己写
- **Node/Go 后端**:没有 curl_cffi 等价物,TLS 指纹模拟是硬需求
- **PostgreSQL / MySQL**:多一个服务多一份运维;SQLite 上限远未到
- **Celery + Redis/RabbitMQ**:任务就是 SQLite 一张表,单 worker 串行,消息队列是杀鸡用牛刀
- **SPA(Vue/React)**:导航流畅度优势在公网高延迟下才明显,NAS 局域网里 SSR 整页跳转 ~100–300ms 可感知但不难受;SPA 要重建 13+ 页视图层和 1679 行设计系统、引入 Vite 构建链,收益/成本不成比例

## 三、前端路线

**SSR + 局部增强,无构建链。**

- 现有 8 个页面 + `app.css`(设计系统)+ `app.js`(灯箱/抽屉/收藏/搜索/主题)是成品资产:静态 HTML → Jinja2 模板,`data.js` 演示数据替换为模板变量,其余结构不动
- 动态交互走 `/api/*` + fetch 局部更新:
  - 瀑布流「加载更多」:fetch 下一页 JSON → 追加 DOM(消除整页刷新卡顿点)
  - 管理端任务进度:2 秒轮询局部更新(单管理员场景比 SSE/WebSocket 简单可靠)
  - 收藏:登录后服务端存储,游客仍可用 localStorage
- **TypeScript:不引入编译工具链**,用 ES Modules + JSDoc 类型标注 + `jsconfig.json` checkJs(`tsc --noEmit` 只检查不编译)。类型安全重点是 fetch 边界——手写 JSDoc `typedef` 覆盖 API 响应形状;将来可选用 openapi-typescript 从 FastAPI schema 生成 `.d.ts`,契约自动同步
- 升级路径:Jinja2 模板粒度便于将来渐进迁移 SPA,路没有堵死

**虚化背景的图源规则**(`templating._blur_src`, 2026-10-24 定稿):

| 页面 | 垫底图 |
|---|---|
| `/` 首页 | **跟轮播同一本** —— 精选(featured)合集优先, 没有精选才最新入库; 前端 `pc:hero-bg` 事件再把轮播当前那张(2400 档)同步上墙, SSR 这张只管首帧 |
| `/collections/<slug>` | 本合集 `sort_order` 最小的那张 |
| `/models/<slug>` | 模特头像; 没头像 → 该模特**发布日期最新**合集的第一张(跟详情页网格第一张同本) |
| 其余(写真列表/模特列表/收藏/个人中心) | **最新入库(created_at), 不受 featured 影响** |

两条规矩:①「最新」一律指入库时间 `created_at`, 不是源站发布日期
`published_at`(老站转载的旧作今天刚入库, 按发布日期永远排后面);②精选是首页
的编辑推荐位, 只许影响首页与轮播, 不许改浏览页观感。

**模特列表「排序: 最新」**(`/models`, `web._model_payload` / `models.html`):按该
模特**最新入库那本写真**的时间倒序 —— `created_at` 精确到微秒, 同刻用合集 id 兜底
(`latestAt` / `latestCid` 两个字段), 即「最新入库写真对应的模特」。粒度不能只到
「天」:一次采集会灌进几十个模特, 生产上单日并列 46-48 个, 旧的日期键让组内顺序
退回 SQL 的 `name` 序, 实测榜单前 10 名成了字母序(与真·入库序重合仅 2 条)。
`latest`(日期)字段保留给展示与手机端, 不改语义。

**手机端同一个语义**(`mobile_api.mobile_models`):`/api/mobile/models` 原来按
`Model.created_at`(模特行建立时间 = 首次收录时间)排, 与 web 的「最新入库写真」不是
一回事; 现在两端口径统一, `sort=latest|oldest` 只负责翻方向。没有已发布作品的模特
两个方向都垫底(没有时间可比)。Android 客户端不做任何本地排序(直接渲染服务端顺序),
因此**客户端无需改动、也不用发新 APK**。

**模特详情页的作品网格 = 源站发布日期序**(`web._works_by_published` /
`mobile_api.mobile_model_detail`):按 `published_at` 新→旧, 同日按合集 id 兜底,
没填日期沉到最后 —— 与写真列表 `/collections`(`_published_collections`)同一把尺子。
详情页是「这个人的作品目录」, 读者按发行时间线看, 转载旧作该待在该待的年份上;
「最新入库」只属于浏览排序(写真列表的 `added_latest`、`/models` 的「排序: 最新」、
首页轮播), 不进详情页。两端口径一致, 客户端同样无需改动。对应的虚化兜底
(`/models/<slug>` 无头像分支)也跟着改发布日期序, 保证背景恒等于网格第一张。

**列表页页头 = 统计信息**(`/collections` / `/models`, 2026-10-24):页头那行主题句
(`.page-head__sub` + `data-sub`, 原来给虚化模式做淡出)换成两段数字 ——
「`{n} 个写真集` / `{n} 位模特` + `{n} 张照片`」, 由 `web.collections_page` /
`web.models_page` 传 `stats` 进模板, 复用页面本来就算好的 `_photo_counts` 一遍
`GROUP BY`, 不额外查库。照片总数口径 = **各已发布写真集的照片数之和**(`photos` 表
没有发布状态字段, 这就是全部照片), 因此两个页面算出的照片总数必然一致。
样式 `.page-head__stats` 只加了 `display:flex; flex-wrap:wrap; gap:var(--s6)`;
数字用 `.num`(tabular-nums), 窄屏自动换行。同时删掉排序栏右侧那个「xxx 个写真集 /
xxx 位模特」计数(`.filters__count` + `[data-count]` + render() 里两行赋值),
它会跟着筛选实时变, 跟页头的总量混淆, 且让排序栏挤成左右两头。

**顶栏服务端直出**(`_header.html`, 2026-10-24):顶栏原来是空壳
`<header data-header></header>`, 由 `app.js` 在 `DOMContentLoaded` 里 `innerHTML`
塞进去。问题在首屏排版: 空壳高度是 0, 浏览器先按「顶栏 0 高」把内容从页面顶端
排下来, 脚本一到顶栏变成 68px(移动端 56px), 整页往下**跳一格** —— 刷新时最明显
(先用 CDP 量过: 250ms 延迟下 0→68px 的空窗约 350ms)。现在站名/导航/搜索/收藏/
主题钮/头像全部由 Jinja 直出(`_shell.html` 与后台模板都 include 同一个 partial), 样式类 `header header--immersive` 也一起直出(原来
由 JS 加, 首帧会先白后黑), 导航高亮按 `request.url.path` 前缀在模板里算, 与
`activeKey()` 同一把尺子(详情页归到所属列表项)。`app.js` 只剩
`tabbar / drawer / search / footer` 这些**不参与首屏排版**的壳, 顶栏的按钮由
`bindChrome()` 照常绑定; 主题按钮图标仍由 `applyTheme()` 填(主题存 localStorage,
服务端不知道), 收藏小红点仍由 `syncAll()` 控制。
顶栏标记收在**一个** partial 里(`_header.html`), 用 `{% include '_header.html' %}`
引入: `_shell.html`(前台 7 个页面) + `admin/*.html` 11 个页面 + `notfound.html`。
后台模板走 `base.html` 自己手写 `.shell`/`<main>`, 原来各自带一份空壳
`<header data-header></header>`, 靠同一段 JS 填 —— 所以「顶栏改直出」第一次只改了
`_shell.html`, 后台 11 个页面的顶栏当场变空白(已修: 12 处空壳统一换成 include)。
partial 里的用户从 `user` 变量取, 没有就回落 `request.state.user`(后台路由不传
`user`); 导航高亮对后台路径不匹配任何一项, 与旧 JS 的 `activeKey()` 行为一致。
`app.js` 那份建头部的代码已删, 别再往回加 —— 两处必然漂移。
另外 `<main>` 里的照片墙仍是 JS 按窗口构建的(首屏 900px → 全量 47k px), 从页面
顶部刷新时看不出位移, 但如果**滚到中间再刷新**, 浏览器恢复的滚动位置会随卡片
补进而抖动; 那是瀑布流分页/定位的话题, 与顶栏无关。

## 四、后端模块划分

```
app/
├── main.py                 # FastAPI 入口,挂路由/静态/启动 worker
├── config.py               # Pydantic Settings(下载目录、黑白名单、周期)
├── db.py + models/         # SQLAlchemy 表定义
├── deps.py                 # 认证依赖:require_login / require_admin
├── routers/
│   ├── auth.py             # 登录/登出
│   ├── discovery.py        # 首页(Hero/印样条/编辑网格)
│   ├── models_web.py       # 模特列表/详情
│   ├── collections_web.py  # 写真列表/详情
│   ├── favorites_api.py    # 收藏 JSON API
│   └── admin/              # dashboard、模特/写真/照片/标签/用户 CRUD、采集任务页、设置页
├── services/
│   ├── harvest/            # 需求 §29 采集子系统(独立包)
│   │   ├── net.py          #   列表/详情页解析、短链解析、流式下载
│   │   ├── pipeline.py     #   解压 → 归档 → 删包
│   │   ├── worker.py       #   扫描 → 入队 → 串行消费 → 过滤 → 归档 → 自动导入
│   │   └── filters.py      #   黑白名单(标题+标签) + 模特名排除词
│   ├── media.py            # 缩略图生成/裁剪/缓存
│   ├── library_import.py   # (M4)归档库 → 平台入库(移动文件 + 建库)
│   └── settings_store.py   # settings 表键值(默认值/类型/即时生效)
└── templates/ + static/    # 从静态设计稿移植
```

采集子系统边界刻意收窄:对内只暴露 `scan_once()` / `enqueue(url)` / 状态查询三个口;网络与文件系统操作集中在 pipeline 单文件,测试时 mock,不需要真联网。

## 五、数据模型(12 张表)

数据库只存元数据,图片文件本体在磁盘 volume,库里存相对路径。

```
── 用户与权限 ──
users(id, username, password_hash, role[user|admin], created_at)
sessions(id, user_id, expires_at)

── 内容库(需求 §4–7)──
models(id, slug, name, stage_name, avatar_path, gender, age, height,
       measurements, company, bio, status, created_at)
collections(id, slug, model_id→models, title, cover_photo_id, published_at,
            status[draft|published|hidden], featured, sort_weight,
            created_at, updated_at)
photos(id, collection_id, filename, width, height, sort_order, created_at)
tags(id, name, slug)
model_tags(model_id, tag_id)
collection_tags(collection_id, tag_id)

── 用户行为 ──
favorites(user_id, target_type[model|collection|photo], target_id, created_at)

── 采集子系统(需求 §29)──
harvest_jobs(id, serial, url, title, model_name, status, bytes_done,
             bytes_total, error, created_at, started_at, finished_at)
harvest_history(serial UNIQUE, status, title, processed_at)

── 配置 ──
settings(key, value)
```

- `harvest_jobs` 即队列本体(worker 轮询取最早排队任务),状态:排队/解析中/下载中/解压中/完成/已存在/已跳过/失败
- `harvest_history` 以序号 UNIQUE 保证同一写真永不重复处理——与 §29 的增量判据一一对应
- `settings` 存下载目录、白/黑名单、采集周期、单轮页数、未分类目录名;管理员后台修改即时生效

明确不进数据库:原图与解压产物(`/library`)、平台图片库与缩略图(`/media`)。

## 六、媒体与存储

- **两个存储根分离**:`/library` = 采集下载暂存区(`模特/写真/照片` 目录结构);`/media` = 平台图片库(入库后)+ 缩略图缓存。M4 导入管线(`app/services/library_import.py`)把图片**移动**到 `/media` 并建 photos 记录,library 侧随之后腾空(详见 §十一「归档库导入」)
- 缩略图按需生成:首次访问裁剪到版位尺寸(WebP),存缓存目录,URL 带尺寸参数配 srcset——满足 §36「服务端裁剪、无重排」
- RAR 内混有视频时(实测存在 `-3-videos` 条目),归档照存;导入时跳过视频(留在 library,用户确认暂不做视频)

## 七、安全(对齐需求 §37)

- 全站登录墙:middleware 未登录重定向 `/login`;`require_admin` 守卫全部 `/admin/*`
- Session:服务端 session 表 + HttpOnly Cookie,SameSite=Lax;密码 argon2id
- 采集模块专项:提交 URL 白名单校验(仅 buondua.com 域)、归档路径非法字符清洗(防目录穿越)、单文件下载大小上限

## 八、Docker 部署

```yaml
# docker-compose.yml(示意)
services:
  photobook:
    build: .
    ports: ["8777:8777"]
    volumes:
      - ./data:/data        # SQLite(db.sqlite3 / WAL 文件)
      - ./library:/library  # 采集归档库
      - ./media:/media      # 平台图片 + 缩略图缓存
    environment:
      - DATA_DIR=/data
      - LIBRARY_DIR=/library
      - MEDIA_DIR=/media
    restart: unless-stopped
```

- 基础镜像 `python:3.12-slim`,apt 装 `p7zip-full`(提供 7zz)
- 全部持久数据走 volume:容器可随意重建,数据不受影响
- 备份策略:拷贝 `/data/db.sqlite3`(WAL 模式建议用 `sqlite3 .backup` 或先停写)+ `/library` 即完整备份
- NAS 无需 Python 环境,只需 Container Manager / Docker Compose

## 九、实施分期

| 阶段 | 内容 | 对应优先级 |
|---|---|---|
| **M1 骨架** | FastAPI + 登录 + 用户端 8 页 SSR 化(复用设计系统)+ 媒体服务 | P0 |
| **M2 管理端** | Admin 后台框架 + 模特/写真/照片/标签/用户 CRUD + 上传 | P0 |
| **M3 采集** | 需求 §29 全量:扫描器/队列/管线/黑白名单/设置页/任务页 | P1 |
| **M4 打通** | 归档库→平台库导入管线 + 统计 + 收藏服务端化收尾 | P1/P2 |

M1/M2 与 M3 几乎无耦合(采集只依赖 settings + 两张表 + 管理员登录),若想先见采集效果,M3 可提前并行。

---

## 十、国际化(i18n)实现

### 数据流

```
请求 → 中间件(解析 user.language → cookie pb_lang → settings site.language → zh-CN)
     → ContextVar set_language → handler / Jinja t() / lang()
     → boot_json 注入 PB_BOOT.i18n(全量映射)→ 前端 PC.t(key, vars)
```

### 关键决策

| 决策 | 取舍 |
| --- | --- |
| 混合 msgid(英文/既有中文原文) | 无构建链下成本最低;缺条目静默回退原文不崩溃 |
| ContextVar 而非 request 传参 | 模板与任意深层函数零改动;BaseHTTPMiddleware 在 `call_next` 前 set 即传播 |
| boot_json 全量注入(~7KB) | JS 无需再发请求;模板内联脚本同样可用 |
| 服务端消息构造时翻译 | flash / 错误是响应的一部分,进入响应前定稿 |
| 后台 pipeline 错误不翻译 | job.error 是数据,存储时无请求上下文;查看时按站点语言属未来增强 |
| users.language(String(8), ""=跟随站点) | 个人偏好覆盖站点默认;cookie 作为未登录 fallback |

### 语言解析优先级

`user.language` → cookie `pb_lang` → settings `site.language` → `DEFAULT_LANG(zh-CN)`

`normalize_lang`:zh-tw/zh-hant/zh-hk/zh-hant-tw → `zh-TW`;zh/zh-cn/zh-hans/zh-sg/cmn → `zh-CN`;其他 → None(视为未设置)。

### 路由

- `POST /language`(公开):设 cookie 一年 + 已登录写 users.language,303 回 `next`。
- `POST /admin/settings`:可选字段 `site.language`(校验后入 settings 表)。

## 十一、采集链路维护记录(2026-09)

### 故障:批量任务 "短链解析失败"

三个独立原因叠加(逐个验证并修复):

1. **ouo.io 改为两段式跳转**:第三步 POST 后落地 `ouo.io/<新短码>`(仍是短链页),
   需把同样的三步流程对新短码再走一遍才到达 MediaFire(最多 `max_hops=3` 轮)。
   → `net.resolve_ouo` 重构为 `_ouo_step`(单轮)+ 循环;落地 URL 缺尾部路径时
   (`.../file/<key>` 无 `/文件名/file`)从响应体找完整链接。
2. **MF_KEY_RE 过严**:落地 URL 尾部无 `/` 时提取不到 quick_key。
   → 正则改为 `mediafire\.com/file/([a-z0-9]+)(?:/|$)`。
3. **curl_cffi 0.16.3 Response 不支持 with 语句**:`download_stream` 的
   `with cr.get(...) as r` 直接 TypeError。→ 手动 `r.close()` + try/finally。

### 后续发现的两个坑(实测暴露)

- **RAR5 "Unsupported Method"**:7zz 26.03 对部分 RAR5 压缩方式(如 v6:m5:16M)
  报 Unsupported Method,密码正确也解不出。→ `pipeline.extract_archive` 改为
  7zz → unar 两级回退(unar 实测可完整解出);unar 输出会套一层归档名目录,自动上提。
- **密码多候选**:详情页原文 "Password: misskon.com or mrcong.com",实际加密用
  哪个取决于发布站点(MissKON 包用 misskon.com)。→ parse 保留多候选原文,
  extract_archive 按 " or " 拆开逐个尝试,每次失败后清理半截产物再试下一个。

### 故障:"无法从 URL 提取 quick_key"(2026-10-20)

misskon.com 两条任务(93694 / 92684)在解析阶段就失败,报错里带着落地 URL:

```
无法从 URL 提取 quick_key: https://www.mediafire.com/file/lff2y9wctjycelj?action=check
```

MediaFire 改了落地行为:`/file/<key>/` 现在 302 到 `/file/<key>/?action=check`
(拦截/检查页),ouo 短链的最终 URL 因此带上了查询串,而 `MF_KEY_RE` 只认 key 后跟
`/` 或行尾 → 提取不到 quick_key,任务在"还没开始下载"时就判死。

- 正则放宽为 `mediafire\.com/file/([a-z0-9]+)(?:[/?#]|$)`;
- `?action=check` 页本身仍含 `download####.mediafire.com` 直链,`mediafire_direct_url`
  无需改动(`get_info.php` 返回的 `normal_download` 页同样可用);
- 回归用例:`test_mf_key_re_accepts_query_string`、`test_mediafire_info_from_action_check_url`。

同类问题第二次出现(2026-09 是 key 后无 `/`),可见 MediaFire 的 URL 形态还会变;
下次再报这个错,先打印落地 URL 再动正则。

### 重启后任务卡在 downloading(2026-10-20)

热补丁重启容器后,#585 停在 `downloading` 5.7% 不动,看门狗也"认为健康"。

`_recover_and_watchdog` 把两种场景合在一个阈值里:

| 场景 | 该用的判据 |
|---|---|
| 启动时恢复上次残留 | 无条件重置——新进程里不可能有任务在跑 |
| 运行中看门狗 | `updated_at` 超过 `STALE_SECONDS`(30 分钟)才重置 |

用错判据的后果:重启前 2 秒刚写过进度的任务被判"健康",要等满 30 分钟才恢复。
→ 加 `at_startup` 参数,`start_worker` 传 True 跳过时间判断;运行中看门狗不变。
PikPak 侧此前已按同样方式修过(`_recover_and_watchdog(at_startup=True)`),
这次把采集侧对齐,回归用例见 `tests/test_harvest_recovery.py`。

### PikPak 预检把 `.part` 当成「已存在」(2026-10-22)

P41 / P42 / P43(斗圣美杜莎 201p、云韵 160p+1V、南宫仙儿 110p)提交后 0.1 秒就
`done`,error 是「→ 已存在,跳过」,一张图都没下。目标目录确实存在,但里面只有
10-18 那轮中断留下的 `*.part` 碎片 —— 恰恰是「没下完」的证据。

`_skip_if_imported` 的目录预检 `_album_has_content` 只排除 `.` 开头的文件和
`Thumbs.db`,把 `download_stream` 的 `.part` 也算成了内容:

- 三元组 `(job.started_at is None)` 决定 `resumed`;这三个任务是 10-21 重新推送的
  新行,`started_at` 为空 → 走「首次运行」分支 → 撞上旧 `.part` → 直接跳过
- 跳过还顺手把文件行全标 `done`(`_settle_pending_files`),所以就算手动重试,
  文件行也会被当成已完成,必须连 `PikPakFile.status` 一起重置才会真下

→ `_album_has_content` 现在排除 `*.part`;重试时除任务状态外还要把文件行改回
`queued`、`files_done` 归零。回归用例
`tests/test_pikpak_recovery.py::test_part_only_album_is_not_existing`。

### MediaFire 前置 Cloudflare 抽检 —— 下载/解析阶段随机 403(2026-10-22)

任务 596 两次重排都在同一处死掉,bytes 始终 0:

```
HTTP 403 for https://www.mediafire.com/file/y22i4h46mcvyae7?action=check
```

不是 URL 坏了,是 **Cloudflare 对无 cookie 的客户端按频率抽检**。容器内实测:

| 请求形态 | 结果 |
|---|---|
| `?action=check` 冷请求(每次新建连接) | 8 次里 3 次 403 + `cf-mitigated: challenge` |
| 裸 `/file/<key>/` 冷请求 | 6 次里 1 次 403 |
| 同一 Session:先裸页(拿 `__cf_bm`/`ukey`)再取目标页 | 4/4 通过 |

采集链路每个 mediafire 调用都是独立 `cr.get`,天然拿不到 cookie,一次 403 就被
判成终态失败(下载阶段原本没有任何重试)。修法两层:

1. **取页面/API**:`net.mediafire_page()` 每轮新建 Session,先打裸页
   `/file/<key>/` 预热再打目标页;被盾则换 Session 退避重试(2s/5s,共 3 轮),
   仍不行抛 `MediaFire 页面取不到(HTTP 403 (cf challenge))`。
   `mediafire_folder_files` / `mediafire_info_from_url` 的 API 调用统一走
   `_mf_api_get()`(同样退避重试)。盾页识别 `is_cf_challenge()`:看
   `cf-mitigated: challenge` 响应头,或正文前 4KB 的 `Just a moment` 等特征
   (盾页有时用 200 返回,状态码不能作前提)。
2. **下载阶段**:`pipeline.download_stream(retries=3)` 对 403/408/425/429/5xx
   和连接中断退避重试,`.part` 走 Range 续传,不白下;404/410、超过
   `max_bytes`、SHA 不符仍是终态失败,不重试。

TeraBox 卷同样受益(直链抖动能续上),代价是 dlink 真过期时多试两次、多等 7 秒。

3. **代理出口对大文件流不友好**(同一次实测挖出来的第二层):过了 CF 之后,
   `http://192.168.0.102:7890` 读 MediaFire CDN 到 **12MB 就被对端断流**
   (`curl: (56) Connection closed abruptly`,18s),同一 dlink **直连 17MB/s**
   正常(200MB/12s 无中断)。任务 596 因此连挂 3 次、停在 75MB。

   结论:`harvest.proxy` 只该用于「页面 / 短链 / API」过 Cloudflare,**大文件流
   必须直连**。`download_stream` 因此按 host 决定出口(`pipeline._EGRESS`):

   | host | 默认 | 连接层失败后 |
   |---|---|---|
   | `*.mediafire.com`(CDN) | 直连 | 翻面走代理并记住 |
   | 其他(含 terabox) | 跟随 `harvest.proxy` | 翻面直连并记住 |

   记住是进程内的(worker 常驻,重启即清空);403/5xx 这类不翻面,只退避重试。
   **TeraBox 例外**:dlink 签名绑定解析出口 IP,`terabox.download_file` 传
   `proxy_fallback=False`,只认 `use_proxy` 指定的那一边,绝不换出口
   (`test_download_file_uses_same_egress_as_resolve` 守着这条)。

回归用例:`test_is_cf_challenge_by_header_and_body`、`test_mediafire_page_primes_session_then_gets_page`、
`test_mediafire_page_retries_challenge_then_succeeds`、`test_mediafire_page_gives_up_with_clear_error`、
`test_mf_api_get_retries_challenge`、`test_download_stream_retries_403_then_succeeds`、
`test_download_stream_resumes_on_retry`、`test_download_stream_does_not_retry_404`、
`test_download_stream_gives_up_after_retries`。

### 换代理节点后整批 failed —— 页面 403 也是抽检, 不是确定答复(2026-10-29)

用户换了代理节点(`harvest.proxy` 地址不变, Clash 上游换线), `/admin/harvest?status=failed`
上堆了 4 条:`932/935` 报 `HTTP 403 for https://buondua.com/…`,`931/933` 报
`短链解析失败: https://ouo.io/…`。**同一个 URL 几分钟后在容器里是 200**
(五个 200 / 一个 403), 403 的正文是 Cloudflare 的「Attention Required!」拦页 ——
按**出口 IP 声誉**抽检, 新节点的 IP 更容易被抽中。

两处「只试一次」把概率事件变成了终态失败:

1. `net.fetch_html` 把 403 当「站点确定答复」, 一次就抛 —— 于是十来次抓页里
   只要撞上一次拦页, 整个任务就死。现在 `RETRY_STATUS = {403, 408, 425, 429,
   5xx}` 与 CF 盾页(含 200 的盾页)都按 `FETCH_RETRY_BACKOFF`(1s/3s)重试,
   **404/410 仍是一次就报**。实测同一 URL 冷请求 1/6 撞 403、隔一秒即 200。
2. `net.resolve_ouo` 的 3 轮换会话之间**没有退避** —— 被盾时三个会话 3 秒内
   三连 403 白试(931 的短链就这么 `None` 的, 而 933 的短链 24s 正常落地)。
   现在换成 `OUO_RETRY_PAUSES = (2.0, 6.0)`。

顺带把 `is_cf_challenge` 的响应头读取包进 try:打桩/非常规响应拿不到
`.headers` 时以前直接 `return False`, 连正文里的 `Just a moment` 都不看。

### 同一个链接, 页面要代理、短链要直连 —— 出口偏好分开记(2026-10-29)

上一修上线后仍 failed:`ouo.io` 的三个短链 `resolve_ouo` 全返回 None。逐跳取证:

| 请求 | 直连(家宽出口) | 经 `harvest.proxy`(新节点) |
|---|---|---|
| `ouo.io/SsLlC8` | **200**, 有 `_token`, 无盾页 | 403 + `cf-mitigated: challenge`(「Just a moment…」) |
| `buondua.com/` | 超时(curl 28) | **200** |
| `download2341.mediafire.com`(签名直链) | **33 MB/s** | 对端不回完整 body |

也就是说 **ouo 的 CF 盾按出口 IP 声誉判, 与页面正好相反**:页面必须走代理,短链
必须直连。旧实现短链只走 `harvest.proxy`, 于是主链全灭 → worker 回落 TeraBox
备份 → TeraBox dlink 绑定解析出口, 只能走代理 → 82 KB/s 爬 2GB(实际要 7 小时)。

修法:短链解析也记一份出口偏好 `_OUO_EGRESS`, 尝试表是「出口 × 指纹」——
主力指纹先把两个出口各试一遍(`_ouo_step` 现在返回 `(落地, 是否被盾)` 以便撞盾
立即翻面, 而不是傻等整条流程走完), 再换 `safari17_0` 兜底;哪个出口过了盾就
记住。实测翻到直连后三条链 24s/21s 出 MediaFire 页(23 秒里 20 秒是 `wait` 间隔)。

顺带一条:`download_stream` 的出口翻面只在**一点都没下下来**时做。MediaFire CDN
会按连接掐流(每 ~35MB 一次 `curl 56`), 那是限速不是出口坏 —— 旧逻辑每次都翻面,
一半的段被迫走代理, 实测平均 1.2 MB/s;改完后 2.0 MB/s(直链裸测 33 MB/s,
掐流是 CDN 侧行为, 靠 Range 续传吃掉)。

再补一条(同日 931 实录):零进展的连接失败要按**整卷累计**给预算。931(2.15GB)
的曲线是「每 ~35MB 被掐一次(有进展, 走 PROGRESS_RETRIES 不计) + 每隔几次夹一个
连上即死」;旧预算 3 次、6 次都在这条曲线上被判死(960MB、1.81GB 两处),而每次
重排都能从 `.part` 续下去 —— 这明显是对新连接的频率限制,不是出口不通。现在
`CONN_STALL_BUDGET = 30`(整卷累计,只管「零进展 + 连接层失败」,403/软拒绝仍按
`retries` 判)配 `STALL_BACKOFF = (5, 10, 20, 30)s`。931 第三次重排后从 1.81GB
续到 2,150,986,350 字节校验通过,四本全部入库。

回归用例:`test_fetch_html_retries_cf_403`、`test_fetch_html_cf_challenge_page_is_retried`、
`test_fetch_html_403_exhausted_reports_reason`、`test_resolve_ouo_flips_to_direct_when_proxy_challenged`、
`test_resolve_ouo_keeps_remembered_egress`、`test_resolve_ouo_both_egress_challenged_returns_none`、
`test_download_stream_does_not_flip_when_partial_data_arrived`、
`test_download_stream_gives_conn_failures_a_wider_budget`;`test_fetch_html_does_not_retry_http_error`
保留(404 仍不重试)。

### MediaFire 「软拒绝」:200 + 一页 HTML 冒充文件(2026-10-22)

热补丁上线后 598/600/601/602/603 五个任务全挂在 SHA256 不匹配,且同一份
期望值两次跑出两个不同的实得值(50dea61… / 32c24e9…) —— 说明下下来的内容
每次都不一样,根本不是文件。

现场取证:直链 302 到 `www.mediafire.com/download_repair.php?flag=2&dkey=…`,
返回 **HTTP 200 + `text/html` + 无 `content-length`**,正文是那个"下载修复"
页面(36KB)。状态码是 200、`Range` 也能续,下载函数一路顺利"写完"才在 SHA
校验处炸掉 —— 而那时 `.part` 已被当垃圾删掉,整卷白下(1.4GB 也白下)。
十几分钟后再试同一个文件,四种组合(直连/代理 × 有无 cookie+Referer)全部
拿回真正的 `application/x-rar`,说明这是 MediaFire 侧**临时**的限速/风控,
不是链接坏了、也不是出口 IP 绑定。

修法(`pipeline._download_once`,写盘之前):

1. 响应 `content-type` 含 `text/html`,或重定向落到 `download_repair.php` →
   抛 `_Retryable(soft=True)`,一个字节都不写进 `.part`;
2. 传了 `expected_size`(采集侧用 API 给的 `file_info.size`)而
   `content-length + 已续传字节 ≠ size`,或干脆没有 `content-length` → 同样判软拒绝;
3. 软拒绝的退避比连接类失败长(`SOFT_BLOCK_BACKOFF = 5s/20s`),用尽后报
   「MediaFire 拒绝下载(返回验证页而非文件)…已重试 3 次;这类拦是临时的,
   过一会儿重排即可」,而不是含糊的 SHA 不符。

回归用例:`test_download_stream_detects_mediafire_repair_page`、
`test_download_stream_size_mismatch_is_soft_block`、
`test_download_stream_reports_soft_block_after_retries`。

**验证页的另一半原因(同一天挖到的)**:直链 dkey 绑「取页面的那个客户端」。
页面走代理、下载换一条无 cookie 的连接直连 → 4/4 全部被塞 `download_repair`
页;只要下载复用取页面的那个 `curl_cffi.Session`(cookie 一致,出口仍可换) →
4/4 正常;页面与下载都直连(同出口无 cookie)也 4/4 正常。所以:

- `net.mediafire_page_session()` 把「这次取页面的 Session」一起返回,
  `mediafire_info_from_url(keep_session=True)` / `mediafire_folder_files`
  随 info 带出 `_session` + `_referer`(采集 worker 负责关闭);
- `pipeline.download_stream(session=…, referer=…)` 用这个 Session 发下载请求,
  出口仍按前面的 `_EGRESS` 策略逐请求决定(实测 Session 的 cookie 与出口可以
  不一致)。A/B 见 `tests/test_pipeline.py::test_download_stream_uses_given_session_and_referer`。

### 大文件被「一刀刀掐断」→ 有进展就一直续(2026-10-22)

同一波里 598 那卷 1.4GB:每条连接都被对端在 20-25MB 处 `curl (56)` 掐断,
直连、代理都一样,3 次重试只推进到 67MB。但有进展就意味着 `.part` 是合法的、
Range 续传能接着下 —— 所以「连接失败且 `.part` 有增长」不再消耗重试预算,
按 `PROGRESS_RETRIES=120`(≈3GB)一路滚,退避 2→10s。没进展的失败仍按
`retries=3` 判死;软拒绝(验证页)按 `SOFT_BLOCK_BACKOFF` 加长退避。
回归用例:`test_download_stream_keeps_resuming_when_attempts_advance`。

### 镜像死链 → TeraBox 备份兜底(2026-10-23,任务 707)

帖子详情页常挂**两条以上短链**:同一条 ouo 是 MediaFire,另一条是 TeraBox 备份。
707 实录:第一条 `ouo.io/omuODmK` 落地
`https://www.mediafire.com/error.php?errno=378&quickkey=…`(页面本身 404,
文件已被 MediaFire 下架),第二条 `ouo.io/RFzVQAV` 是活的 TeraBox 分享。

旧逻辑两条硬伤:

1. `_resolve_infos` 按顺序处理,第一条失败就 `return None` 判 failed ——
   后面的镜像根本不看;
2. `resolve_ouo` 落地 terabox 抛 `UnsupportedHostError`(「不支持TeraBox网盘下载」),
   但 TeraBox 下载通道我们本来就有(`terabox.py`,4kup 站用的就是它),
   于是这个包明明有备份却永远下不来。

改动:

- `resolve_ouo` 落地 MediaFire 错误页 → 抛 `MediaFireDeadError`(带 errno 中文
  原因,`mediafire_error_reason()` 映射);落地其他网盘 → `UnsupportedHostError`
  **带上落地 URL**(`e.url`),调用方才有 surl 兜底
- `_resolve_infos` 逐条试镜像:单条失败只记一笔继续;落地 TeraBox 的收作备用;
  MediaFire 系全废而备用存在 → 整包走 `_resolve_terabox`;分卷只拿到一部分
  视为失败(残包解不出东西,且**不与备份混下**,页面会话随即关掉)
- 任务报错因此能分开:「MediaFire 文件已被下架(errno=378)」≠「短链解析失败」

TeraBox 侧要注意的两个实测点(都已写在代码注释里):dlink 绑定**解析出口 IP**
(`proxy_fallback=False`,直连抓是 404,与解析同出口才 200);`599003486 B`
那类大包走代理约 1.1MB/s,比 MediaFire 直连慢一个量级,是备份兜底的代价。

回归用例:`test_resolve_ouo_mediafire_error_page_raises`、
`test_unsupported_host_error_carries_landing_url`、
`test_resolve_infos_mediafire_dead_falls_back_to_terabox`、
`test_resolve_infos_mediafire_dead_without_backup_reports_reason`、
`test_resolve_infos_discards_partial_volumes`。

### 短链落地 URL 被截断 + 直挂 TeraBox 备份没人收(2026-10-24,任务 760)

760 报 `MediaFire 页面取不到(HTTP 400)`,看上去像「MediaFire 链接失效」,
实际**两个源都完好**,是三个缺陷叠在一起:

1. **ouo 的 302 `Location` 把目标 URL 截断在 255 字符**。760 落在
   `…%E4%B8%83%E` 这个半个百分号转义上(非 Latin-1 字符百分号编码后很长),
   MediaFire 对畸形路径回 HTTP 400。修复:`mediafire_info_from_url` 只用传进来
   的 URL 取 `quick_key`,页面一律走 API `links.normal_download`(MF 自己的
   canonical 写法;没给就退裸 `<host>/file/<key>/`)。文件名段本就只是装饰,
   同一文件用 canonical 链接 2 秒拿到直链。预热(`_mf_prime_url` → `__cf_bm`)
   照旧,因为 canonical 带文件名段、与裸 key 页不同。
2. **单条源的 RuntimeError 穿透 `_resolve_infos`**。`_try_link` 只 catch
   `MediaFireDeadError`/`UnsupportedHostError`,页面/API 的 `RuntimeError`
   (400 / 502 / CF 盾打满 3 次)直接冒到 `_run_job` —— 后续镜像与备份全不看,
   任务连 failed 文案都写不进去。修复:`_try_link` 把「这条源这轮取不到」
   一律收成 `("fail", 说明)`,与「内容已下架」同列,由上层决定换源。
3. **详情页直挂的 TeraBox 链接从未进过解析**。760 页面形态:

   ```html
   <a href="https://ouo.io/oL053g">Download link: MediaFire</a>
   <a href="https://terabox.com/s/1Y96hEf0OjWQO_yOyS_6qTg">Download link: Terabox</a>
   ```

   旧解析器只收 `SHORTLINK_RE`(ouo 域)与 `MEDIAFIRE_LINK_RE`(MF 文件页),
   直挂的 terabox 分享两边都不匹配,直接被丢 —— 备份躺在页面上却永远用不上。
   修复:`_collect_direct_download_links()`(MF 直链 + `_collect_terabox_links`)
   收进 `shortlinks`,buondua / misskon / nicesss 三个解析器共用;worker 侧
   `_try_link` 见 terabox 域直接判 `("tb", …)`,不再当 MediaFire 页面解析
   (以前会撞「无法从 URL 提取 quick_key」)。

优先级不变:同一包仍**只走一个源**,MediaFire 优先,TeraBox 只在 MF 全废时兜底
(混下就是双倍流量)。回归用例:
`test_misskon_direct_terabox_collected_from_real_page_shape`、
`test_mediafire_info_prefers_api_canonical_page`、
`test_resolve_infos_mf_page_error_falls_back_to_direct_terabox`、
`test_resolve_infos_direct_terabox_link_in_backup_list`、
`test_resolve_infos_mf_page_error_reported_not_raised`。

### 源站短链本身已停用(2026-10-24,misskon FEILIN Video No.031)

用户报「详情页的下载按钮点了显示 rejected」。点了 `rejected` 的是**我们自己
的油猴徽标**,不是源站,也不涉及下载:

1. `buondua-bridge.user.js` 在 misskon 详情页把徽标挂在 `p.post-tag`(标签行)
   上;点击时它从宿主节点里找 `a[href*='://misskon.com/']` 当详情 URL,而标签
   行里全是 `https://misskon.com/tag/…` 归档链接 —— 推上去的是标签页;
2. 服务端 `_serial_from_url` → `net.serial_from_url` 对标签页既无 slug 序号
   也取不到 postid,抛 ValueError → `/api/ext/harvest` 回 `state: "rejected"`;
3. 徽标文案是 `LABEL[st] || st`,没有 `rejected` 这一项 → 原样把英文状态画在
   徽标上。

修法:详情页直接用 `location.href`(只有列表页卡片才从卡片里找详情链接),
`LABEL` 补 `rejected: "✕ 链接无效"` + 未知状态兜底「✕ 推送失败」,序号解析失败
的文案也改成人话。脚本 `@version` 1.8.0 → 1.8.1。

顺带查清该帖真实状态:它是 2017 年的**视频**帖,整页只有一条
`http://shink.me/wyxfh`(锚文本写 Google Drive)。shink.me 已关站,域名进了
ParkLogic 停放页(真 Chrome 从 misskon 点进去,落到 "This domain name may be
for sale",router 也只回停放广告) —— 目标地址无残留,**不可恢复**;同类老帖
(No.025/027)用的是 adf.ly,现在全量 302 到 linkvertise,同样过不去。所以这类
帖子在源站就是死档,不是我们解析器的问题。

为此加了 `net.DEAD_SHORTENER_HOSTS` + `_collect_dead_shortener_links()`:
buondua / misskon / nicesss / 4kup 四个解析器把这类死链服务名记进
`HarvestTarget.dead_shortlinks`;worker 在「没有可用短链」时据此报
「源站短链已停用(shink.me),没有可用的下载源」,而不是笼统的「详情页未找到
下载短链」—— 前者一眼看出是源站废了,后者容易被当成解析 bug。

测试:`tests/test_dead_shortener.py`(死链页面 failed 文案 + 无链接页面维持原
文案)、`tests/test_net.py::test_dead_shortener_page_has_no_usable_links`
等 3 条(死链不污染 shortlinks、与可用短链共存时照记、按服务去重)。

### 老帖列表页「刷新后徽标全消失」(2026-10-24,misskon tag 第 320 页)

用户报 `https://misskon.com/tag/xiuren/page/320/` 首次打开 20 张卡片都有「⬇ 下载」
角标,**F5 一次就全没了**,再刷也不回来。是脚本自己的 bug,与服务端无关:

1. 该页 20 张卡片全是老帖 slug(`/xiuren-no-1131-…/`,无 `<序号>-` 前缀),
   脚本本地取不到序号 → 走「未知 URL」通道;
2. 首次访问: 序号不在 GM 存储 → `fresh` 非空 → `POST /status-by-url` 让服务端
   解析,拿到 `serial` 后写进 `GM_setValue("pb_serial:<url>")`,顺手把徽标画出来;
3. 刷新后: 20 个 URL 全在 GM 存储里 → `fresh` 为空 → 改走
   `queryBySerial()`,而调用处写成了

   ```js
   queryBySerial(known.map(u => ({…}), cards));
   ```

   `cards` 落进了 `Array.map` 的 thisArg 位置(箭头函数本就忽略 this),
   `queryBySerial` 的第二参数是 `undefined` → `applyUnknown` 里
   `cards.forEach` 抛 `TypeError: Cannot read properties of undefined
   (reading 'forEach')` → 一张徽标都画不出来,**且异常在 GM 回调里被吞掉**,
   页面看起来只是"没角标"。首次访问走的是 `fresh` 分支,所以正常。

修法:调用处括号改对(`queryBySerial(known.map(…), cards)`),另外两处兜底
(以后同类漏参不会再静默失败)`applyUnknown` 缺 `cards` 时现场 `cardNodes()`;
`cardTitle()` 对 `cards.find(…) || {}` 的假卡片直接返回空串(否则抛
`card.querySelector is not a function`)。脚本 1.8.1 → 1.8.2。

顺带的好处: 刷新后走 `/status`(单次批量),不再每次轮询都让服务端回源 20 个
详情页。

验证方式(没有 JS 测试框架,用真浏览器跑):headless Chrome + CDP 打开该页,
注入 GM 打桩版脚本,首屏 20 个徽标(`⬇ 下载|new|27505` …),`Page.reload`
后仍 20 个、无 `cbError`;修复前同一流程刷新后是 0 个并抛上述 TypeError。

### 4kup 老帖的站内中转短链(bit.ly → getlink,XXTEA 加密)(2026-10-24,任务 824)

824(`4kup.net/mfstar-vol-076-mu-yu-qian`)报「详情页未找到下载短链」。**源站
链接是好的**:2022 及更早的 4kup 帖子不挂直链,下载按钮是站内广告中转短链,
而且是**单引号** href:

```html
<a href='https://bit.ly/3U2VFgk' target='_blank' rel="nofollow noopener">Download from terabox.com</a>
```

链路(实查):

```
bit.ly/<code>   301→  https://www.4kup.net/p/go.html#?u=<XXTEA+base64 令牌>
页面 JS          →   https://4kup.net/getlink/?u=<令牌>
Tea.decrypt(令牌, config.defaultkey)  →  JSON {"url": "<真网盘链接>", "note2": "4kup"}
```

我们两边都没收:短链白名单(`SHORTLINK_RE`)只认 ouo,`TERABOX_LINK_RE` 又只
匹配 terabox 系域名,页面上也没有直挂 terabox → 一条源都进不了 `shortlinks`。
抽样确认这是一整类老帖(不是个例):`bololi-bol-05x`、`xiuren-no-4326/4327`、
`xiaoyu-vol-00x`、`coser-money-no-027` 等全是 bit.ly 中转,落地 MF 与 TeraBox
各占一半;2023 年后的帖子才改成直挂 `1024terabox.com`。

修复(`net.py`):

- `_collect_4kup_gate_links()`:白名单短链域名(bit.ly / tinyurl / cutt.ly /
  rebrand.ly / s.id / is.gd / za.gl / shrinkme / t.ly / rb.gy / shorturl.at),
  同时吃单双引号 —— 只收白名单,页面里的广告 iframe / 图库大图链接不会误入;
- `is_4kup_gate_link()`:短链域,或 4kup 自家 `p/go.html` / `getlink` 页;
- `resolve_4kup_gate()`:`allow_redirects=False` 自己跟跳转拿 `Location` →
  取出 `u` 令牌(**先 `unquote`**,URL 里是百分号编码的)→ XXTEA 解出 JSON。
  密钥先用实查常量 `maxbong`,解不开再现场读中转页里的 `defaultkey`(密钥换了
  也不至于废);两者都失败报「令牌解不开(可能需要口令)」,不静默。
- `parse_4kup_detail_page()`:中转短链补进 `shortlinks`(直挂 terabox 在前,
  优先级不变)。

worker 侧(`worker.py`):`mf_links` 与备用链过滤都认中转短链;`_try_link`
解出落地 URL 后按域分流 —— TeraBox 走分享展开,MediaFire 走 760 那套
canonical 页面 + API 取直链。落地 URL 的文件名段可能是双重编码
(`%2528…`),不影响:760 起只用 `quick_key`,页面一律走 canonical 链接。

测试:`tests/test_4kup_gate.py` 16 条(XXTEA 加解密往返、单引号收取与去重、
解析进 shortlinks、`is_4kup_gate_link` 正负例、terabox/MF 两种落地、密钥变了
走中转页兜底、需要口令、没跳转、落地不是 URL、worker 三种分流 + 失败文案)。
令牌用测试内的 `xxtea_encrypt`(镜像页面 `Tea.encode`)自造,`cr.get` 与
`fetch_html` 全打桩,不发网络请求。

实测:修复后 `parse_4kup_detail_page` 拿到 `['https://bit.ly/3U2VFgk']`,三条
真实短链分别解出 `terabox.com/s/1OmrqqD…`、`mediafire.com/file/19vcmlv1ba2n4rv/…`、
`mediafire.com/file/u565jqfr9bphwh3/…`;重推 824 → 任务 825 正常下载
(332MB)。

### 进阶缺陷:入库标题被压缩包内目录名截短 + 模特名抽不到(2026-10-24,任务 825)

上面那条修完,824 下载成功(任务 825,53 张),但合集成了
`未分类-mfstar-vol-076`,标题只有「MFStar Vol.076」。两处各自独立:

**1) 标题截短** —— 入库 title 取自**目录名**,而目录名取自压缩包内自带的
顶层目录(4kup 老帖包内是 `MFStar Vol.076`,页面标题却是
`MFStar Vol.076 Mu Yu Qian (慕羽茜)`):`archive_collection()` 优先用包内
目录名,`import_album()` 又 `title = album_dir.name`,页面标题在中间被丢掉。
顺带还和 worker 的 `dest_dir` 预检不一致(预检按页面标题算目录名)。

修法(`pipeline.archive_collection`):**包内目录名是页面标题的前缀**且页面
标题不带「(N photos)」尾缀时,改用页面标题做目录名。其他来源包内目录名通常
就是完整标题(不是前缀关系),行为不变 —— 也顺手让「预检目录」与「真实目录」
重新对齐。

**2) 模特名** —— `titlemodel` 第 10 条白名单只有 XIUREN / UGIRLS / IMISS /
YouMi,`MFStar Vol.076 …` / `BoLoli Bol.054 …` 这类老帖系列整批落「未分类」。
抽样 25 条 4kup 老帖标题:修复前 15/25 抽到名,修复后 **25/25**。

修法(`titlemodel` 新增 10b):通用「系列 编号 名字」规则,系列名本身不当
人名(名字位固定在编号后),排在原有白名单规则之后,不遮蔽任何既有形态:

```
^[A-Za-z][A-Za-z0-9]{2,14}[\s._-]+
(?:\d{4}[-._/]\d{1,2}[-._/]\d{1,2}[\s._-]+)?     # 可选日期(系列名与编号之间)
(?:Vol|No|Bol|U)\.?[\s._-]*\d{1,5}[\s._-]+(.+)$
```

`U` 这一支是 UGirls 老帖的「系列 U258 名字」写法(HuaYang 那批是「系列
日期 Vol.007 名字」)。这两种形态当时也全落「未分类」——用户报了 8 条
(`UGirls U098/U120/U236 Mu Yu Qian (慕羽茜)`、`UGirls U258/U309/U336/U420
Mu Fei Fei (穆菲菲)`、`HuaYang 2017-09-25 Vol.007 Mu Fei Fei (穆菲菲)`),
补上后 8/8 抽出名字,街拍批量标题(`…精选街拍作品 NO.5926 BYD展台车模…`)
仍然抽不出来(不该抽)。

**3) 原生名一直没落下** —— `model_name_from_title()` 返回的是
`(拉丁名, 原生名)`,采集链路只接了前半,`models.stage_name` 永远空着(前台
模特页因此没有「又名 …」)。现在 `HarvestTarget.model_native` 一路带到
`import_album(..., model_native=…)`,写进 `models.stage_name`:模特页显示
「Known as 慕羽茜」,`/models` 与搜索也能用中文命中。已有模特**不覆盖**非空
`stage_name`(人工填的艺名比自动抽取的可信),只在空的时候补。既有那条
`Mu Yu Qian` 已补成 `慕羽茜`。

数据修复(合集 801 就地改,不重下也不重传):DB 里改 title/slug/model_id +
53 行 `photos.filename`、`_cache/` 下两个规格目录跟着改名(原图已在上传后
本地清理,无需搬)、`harvest_jobs.collection_slug` 同步。
`photo_uploads.remote_path` **不动** —— 远端文件没搬,改了反而断链。

修复后:`/collections/mu-yu-qian-mfstar-vol-076-mu-yu-qian-(慕羽茜)` 200,
标题「MFStar Vol.076 Mu Yu Qian (慕羽茜)」,模特 `Mu Yu Qian`,缩略图正常出图。

测试:`tests/test_titlemodel_series.py` 18 条(15 条真帖标题语料 + 系列名不得
当人名 + 不遮蔽既有前缀 + 无编号不抽 + 街拍标题不被误抽),
`tests/test_pipeline.py` 新增 3 条(截短名升级为页面标题 / 无前缀关系保持
包内名 / 带张数尾缀的标题不拿来当目录名)。

历史数据清理(同日,一次性):按「标题能抽出名字但 `model_id` 为空」扫全库,
就地挂模特 —— 上面 8 条 + `HuaYang Vol.363 赵惟依coco`(这条更早被抽成模特
`HuaYang` 挂错了,系列名当人名),共 9 条:改 `collections.model_id/slug`、
`photos.filename`、`_cache` 两档目录,目录跟着模特 slug 走;
`photo_uploads.remote_path` 不动。顺带删掉搬空的假模特 `HuaYang`。
之后「未分类」合集 76 → 68,剩下的确实没人名(AI 生成系列 / 街拍批量 /
杂志卷号 / 中文角色名)。脚本是临时用的,没进仓库 —— 判据(能抽名 + 未分类)
放在 `titlemodel` 里,以后新采的不会再落这条坑。

### 取页抖动零重试 + 三站点原生名没带走(2026-10-25,任务 869)

任务 869(`misskon.com/120229-…-sentimental-57-photos`)在 5 秒内 `failed`,
`bytes_done=0`、`title`/`model_name` 都是 NULL,报错原文是裸的
`Failed to perform, curl: (35) Recv failure: Connection reset by peer.`。

**根因**:`net.fetch_html` 单次请求、零重试,被对端 reset 一次就是任务终态。
报错里没有 `下载连接失败 …` 前缀正是判据 —— 那是 `download_stream` 的措辞,
说明死在第一步取详情页,根本没进解析/下载。同一批的 870 号任务 1 秒后在
同一个代理出口上正常下完 52MB,可见站点与出口当时都通,纯粹是单连接抖动。
重排后同一个 URL 一次就过(详情页 1.4s / 83,768B),`ouo.io` → MediaFire
`78,288,398` 字节 / sha256 也对得上,内容侧没有问题。

**修法**:`fetch_html(url, *, timeout, retries=FETCH_RETRIES)` 对**连接层**异常
(连接重置 / TLS / 超时 / 代理)按 `FETCH_RETRY_BACKOFF = (1s, 3s, 6s)` 退避重试;
HTTP 非 200 **不重试**(404/403 是站点的确定答复),`InvalidURL` 这类参数级错误
也不重试。用尽后报错保留原始 curl 文本并追加 `(已重试 N 次)`,日志能直接看出
是 curl 35 还是 28。

**顺带补的原生名**:上一节只让 4kup 传 `model_native`,而 buondua / misskon /
nicesss 的模特名来自页面 tag,原名(日文/中文)只藏在标题里,于是这三家的模特
`stage_name` 永远空着 —— 869 就是活例:`Asano Kokoro` 明明带 `(浅野こころ)`,
模特 164 号却没有「又名」。现在三家解析器都调 `native_name_for_model(title, 模特名)`:
① 标题规则的 `(拉丁名, 原生名)` 与模特名同一人 → 直接用;
② 模特名后面紧跟括号、括号内是 CJK → 取它(标题里别的括号是张数/系列,
靠 CJK 守卫排除);抽不到或原名与名字本身相同 → 空串,不写同义「又名」。

还有一处会**建错模特**:nicesss 的标题正则把括号一起吃进名字位
(`Asano Kokoro (浅野こころ)`),tag 偶尔也这么写。`split_trailing_native(名字)`
把「Latin (原名)」拆成 (模特名, 原生名),三家解析器都先过一道 ——
否则会长出一个带括号、前台搜不到的模特条目。

测试:`tests/test_net.py` 新增 10 条(连接重置重试后成功 / 用尽保留 curl 原文 /
HTTP 404 不重试 / 非法 URL 不重试 / `retries=1` 单次 / 三家站点各带出原生名 /
名字位「Latin (原名)」拆开 / tag 带括号拆开),
`tests/test_titlemodel_series.py` 新增 3 组(括号取原名 + 全角括号 /
张数与同义重复不取 / 拉丁名对不上时不猜)。

历史数据补名(同日,一次性):补丁只对**新入库**生效,既有模特仍空着,所以
按「该模特名下任一合集标题能抽出与名字同属一人的原名」扫全库,给
`stage_name` 为空且有唯一候选的模特补上 —— 289 个模特里 **287** 个为空,
**168** 个抽出唯一原名(日文/韩文为主,`Shiori Hatano → 羽田野栞`、
`Yeha → 예하`、`Kirara Asuka → 明日花キララ`);唯一冲突
`Yang Chen Chen → {杨晨晨Yome, 杨晨晨}` 是同一人的两种写法,**跳过不猜**。
补后 170/289 有「又名」。人工填过的非空 `stage_name` 一律不动。
验证:模特页出「又名 浅野こころ」,`/api/search?q=浅野こころ` 命中
`asano-kokoro`(5 本)、`q=예하` 命中 `yeha`(8 本)。改前快照
`photobook.db.bak-wal-20261026-0417`。

### 出品方 tag 被当成模特名(2026-10-27,假模特 `le` 的 14 本)

用户报 `/models/le` 这个模特页:模特名识别错了,`LE` 不是人名。库里 `le`
名下 **14 本 / 892 张**,合集 slug 全是 `le-[le]-…`。

**根因**:buondua / misskon 的模特名取「tag 列表里第一个未被排除词命中的
tag」,而 misskon 的 `[LE] LEHF-240B: Min.E (민이)` 这类帖子 tag 就是
`[LE, Min.E]` —— `LE` 是出品方、偏偏排第一,于是这 14 本全挂在一个假模特上。
往排除词里补 `LE` 只治这一家,下个出品方出现时还得再补一条;「总排在首位的
tag 都是出品方」这条统计结论得靠标题交叉验证兜底,而不是靠人肉维护词表。

**修法**(`filters.resolve_model`,标题规则优先 + tag 兜底 + 交叉验证):

1. tag 全被排除 → 用标题规则抽到的名字(以前一律落「未分类」);
2. 两路指向同一个人 → 用 tag 名(tag 常带原生名,原生名另有兜底);
3. tag 命中的正是标题里的出品方方括号(`[LE]` / `[MAXIM]` / `[ROGLE]` …)
   → 用标题里的名字(新出品方不用再改代码);
4. 其余不一致 → 保持 tag 名,不拿标题规则去覆盖可靠的 tag。

没做成「无脑标题优先」,是因为拿 **731 条历史 job 标题**实测:无脑翻转会把
`Coser@水淼Aqua: …` 抽成带尾冒号的账号名、把 `[MAXIM] Green` 抽成
`[MAXIM] Green`。所以顺手补了 `titlemodel` 两处清洗(名字位前的方括号块、
名字位后的尾冒号),并把第 8 条规则从写死 `[LE]` 改成「任意出品方方括号 +
可选冒号/破折号分隔」(`LEHF-209B: Xiu`、`LEDG-237 - Ming` 现在都能抽到,
且能带出 `(민이)` 这类原生名)。`GMS` 也从 `_STOP`(系列名黑名单)移出 ——
用户确认它是模特名。

回归对比(同 731 条:沿用 692、**从「未分类」变有人名 21**、覆盖 18、
变成空 **0**):覆盖里 12 条是出品方 tag 纠正(`LE`/`ROGLE`/`Acute`/
`HIGH FANTASY`),另 6 条是「Latin (原生名)」拆分(本就在跑的逻辑)。

历史数据修复(同日,一次性,不重下不重传):

- 14 本里 **397 / 399** 与已有合集 **190 / 97** 是同一本 MissKON 写真的逐张
  重复(文件名完全相同 —— 当初模特名不同,预检没拦住,白下了一遍),
  按「留已有那两本」删掉后采的副本(**远端 `le/` 下的文件不动,留作备份**;
  `photos` / `photo_uploads` / `upload_jobs` 行一并清掉);
- 其余 12 本就地改 `collections.model_id/slug`、`photos.filename` 前缀、
  `_cache/{s900,s2400}` 目录跟着模特 slug 走,`photo_uploads.remote_path`
  **不动**(远端文件没搬,改了反而断链);
- 新建模特 `GMS` / `Xiu` / `U.Hwa(은유화)` / `Sir.Bean(피아)` / `Son.J` /
  `Woo` / `Silver`,`Ming` 挂回已有 253 号;删掉搬空的假模特 `le`(176);
- 排除词里去掉 `gms`(现在是模特名),`LE` 保留。

验证:`/models/le` → 404,`/models/gms`、`u-hwa`、`sir-bean`、`silver` 200,
12 本合集页 200;原图 `/media/gms/[le]-gms-006a-gms/…` 4,090,938B、
`/t/s900/` 62,084B(302 回源与搬过来的缩略图缓存都通)。
改前快照 `photobook.db.bak-lefix-20261027`。

**顺带治了同类隐患(同日晚)**:库里还有 7 个「名字里带原生名括号」的老条目
(`Coco (瑚々)`、`Jdabyeol (정다별이)`、`Seo Yi (박서이)`、`Rlwndud (쥬입니댜)`、
`Kasame 花雨(かさめ)`、`Unpai (うんぱい)`、`Marupi (まるぴ)`),而新规则抽出来的
是拆开后的名字 —— 精确比名字会给同一个人再建一条,模特名一变,合集 slug /
媒体目录跟着变,采集侧的「这本导过没有」预检就认不出来(重复下载的老路)。

- `library_import._find_model`:先精确匹配,再按 `titlemodel.model_key`(拆掉
  「(原生名)」+ 忽略标点/大小写)兜底;`_get_or_create_model` 与 `_owner_slug`
  都走它 —— 后者尤其关键,预检 slug 必须落在**既有**模特的 slug 前缀上。
  比较键没有走模块级导入:harvest 包一进来就 import `library_import`,反向
  模块级依赖会成环,所以在函数里延迟导入。
- 7 个条目就地改名:`models.name/slug/stage_name`(括号里的原生名转进
  stage_name)、合集 slug、`photos.filename` 前缀、本地媒体目录、各档缩略图
  缓存目录、`harvest_jobs.collection_slug` 一起搬,`photo_uploads.remote_path`
  不动。12 本合集 / 1,148 张;改前快照 `photobook.db.bak-paren`。
  **踩坑记录**:`photos.filename` 重写用 `新slug||'/'||substr(filename, len(旧slug)+1)`
  时 `substr` 起点正好是原来那个 `/`,会写成 `coco//[jp]-…`(1,148 行),
  当场修掉并复查 —— 正确的起点是 `len(旧slug)+2`,或干脆 `||substr(...)` 里
  不补 `/`。迁移后 `collection_exists` / `collection_slug` 对这 12 本全部
  重算出原 slug(预检认得出),模型页 `/models/{coco,unpai,marupi,kasame-花雨,
  seo-yi,jdabyeol,rlwndud}` 200、旧带括号 URL 404、原图与 s900/s2400 缩略图 200。

测试:`tests/test_library_import.py` 新增 5 条(带括号的老条目按归一化键复用 /
标点变体复用 / 不同的人不合并 / 预检 slug 用既有模特 slug / 端到端导入不新建);
`tests/test_model_resolve.py` 新增 10 条(出品方 tag 让位给标题名 / tag 全排除
时标题兜底 / 同一人保留 tag 名与原生名 / 写法不同取标题写法 / 不一致时保持 tag /
GMS 是模特名 / 账号尾冒号与出品方方括号清洗 / 两路都没名字仍归未分类)。

### 「已入库」判定:跳过时没有登记本站序号(2026-10-27)

用户报 buondua `/tag/le` 里 **888-891** 四本没显示「已入库」,可它们其实在库里。
浏览器联动脚本判态只看 `ext_api.collection_exists(serial)` —— 即
`collections.source_serial` 与 `source_serials`;**跟任务状态、`harvest_jobs` 行
都没关系**。这四本是 buondua 链接,下完 235MB、解包后才在 `import_album` 的
slug 幂等上命中 misskon 那批同内容(888≡396、889≡398、890≡402、891≡411),
任务判 done,序号却没写进任何写真集 → 脚本永远显示「可下载」,点了白下一遍。

三处跳过路径都补了 `_register_existing_serial`(序号进 `source_serials`,
`harvest_jobs.collection_slug` 补上那条写真集):

1. **预检 ②(slug 命中)** —— 顺手修了它为什么没拦住这四本:页面标题带源站
   装饰 `[LE] GMS-006A: GMS (60 photos)`,而归档目录名是 `[LE] GMS-006A GMS`,
   slug 差一个 `-(60-photos)` 尾缀 → 预检永远比不中,整包白下。现在算两个
   候选:原样 + `titlematch.strip_counts()` 剥掉尾缀;剥尾缀那条**必须过
   真实张数守卫**(`photo_count(标题) == 该写真集实际张数`),否则泛化系列
   标题的不同批次(诛仙-陆雪琪 25/121/310 张)会互相误判 —— 与 44755 那条
   误判实录同一类坑。
2. **`import_album` 幂等跳过** —— 这条正是 888-891 走到的:跳过时要回传
   既有写真集的 slug(`stats["slug"]`),采集侧才拿得到那条记录去登记。
3. **`FileExistsError` 兜底** —— 按目标标题算 slug 再登记;算不出就放弃
   (不比以前差)。③ 标题等价预检本来就会登记,不动。

**存量回填**(同日一次性):按「剥尾缀 slug + 张数守卫」和「token 序列全等 +
张数相等」两条判据,把历史上 `collection_slug is null` 且 `已导入过` 的任务
补登记 —— 命中 12 条(含 888-891 与两条跨站改写过的 445/449),另 2 条
(217 `Nitori Hina …[Graphis] Limited Edition`、314 `精选街拍 NO.5734`)
库里确实没有对应写真集,不动。快照 `photobook.db.bak-skipserials`。
复查:`select` 全表「挂了合集但序号没登记」的任务 = **0**;
`/api/ext/status?serials=57073,56653,56612,56353` 全部 `done`;
拿这 4 条线上 URL 真解析跑一遍预检,4/4 在下载前就命中(候选=剥尾缀)。

测试:`tests/test_harvest_serial_link.py` 5 条(跳过登记后脚本判得出 / 幂等 /
FileExistsError 兜底 / 幂等跳过回传既有 slug / 剥尾缀必须过张数守卫)。

### 测试

- `test_harvest_scan_route` 会真实扫 buondua.com 列表页并把当前首页写真入队,
  内容随时间漂移 → 已 mock `scan_once`(真实扫描曾致 `test_enqueue_manual_accepts_real_url`
  撞上去重)。

### 归档目录规则(2026-09 调整)

`library/<模特名>/<写真目录>/`,**不再额外套一层标题目录**:

- 解压产物根层只有唯一目录(忽略 `__MACOSX` / `.DS_Store` 等垃圾项)→ 直接用该目录名,
  整目录改名过去。压缩包内一般已按标题建好目录,7zz 路径下即发行方原始目录名。
- 根层没有唯一目录(散文件或多顶层)→ 回退用详情页标题。
- 目标目录已存在且非空 → `FileExistsError`(job 标记 `exists`,防覆盖)。
- 注意两种解压工具的结构差异:**7zz 保留**归档内顶层目录;**unar 会压平**单一顶层目录,
  产物多于一项时改套一层 `<压缩包主名>/`。故 unar 回退的任务目录名 = MediaFire 文件名主名
  (如 `XlUREN No.10977`),同样是单层、无重复嵌套。

### 模特名识别 + 排除词(2026-09 新增)

详情页有两个 tag 区域:文章自己的 `<div class="article-tags"><div class="tags">…`,以及
**相关推荐卡片**的 `.item-tags`。旧实现取「页面第一个 `/tag/` 链接」→ 常取到别人的分类 tag。
现只解析 `article-tags` 容器,返回 `HarvestTarget.tags`(显示名、保序)。

模特名 = tag 列表里**第一个未被排除词命中**的 tag(出品方/分类总排在前面):
`[Cosplay, 麻花麻花酱] → 麻花麻花酱`、`[JP, ATFM, Tsubaki] → Tsubaki`、
`[Yeha, AI Enhanced] → Yeha`;全部命中 → 空 → 归档进「未分类」。

`harvest.model_exclude`(默认 38 个词)的推导方式:2026-09 对 buondua 采样
(1020 个列表页专辑 + 330 个详情页,共 1350 个 tag 列表),凡「总是排在首位(从不处于模特位)」
且出现 ≥2 次的 tag 均为出品方/杂志/平台(无一个人名),再人工复核加入 `FEILIN`/
`KelaGirls`/`UGIRLS` 等旧源品牌;`graphis`/`wanimal` 为杂志/摄影师品牌。
实测 1350 个 tag 列表:72 个全被排除(→未分类),其余取到的都是真实模特名。

匹配方式是**按词匹配**(非裸子串):slug 归一化(小写、非字母数字汉字→空格)后要求关键词两侧
不紧邻 `[0-9a-z]` → `jp` 命中 `jp-11853`、`ag` 命中 `ag-11787`,但都不误伤 `magda`;
中文关键词(如 `内购无水印`)不受影响。另会跳过明显非人名的标签(如 `(42 photos)`)。

### 归档库导入(2026-09 新增,M4)

`app/services/library_import.py`:扫 `<library>/<模特名>/<写真目录>/` → 图片**移动**到
`/media/<模特slug>/<写真slug>/` → 建 `models`/`collections`/`photos`(PIL 读宽高、自然序
`001…061` 作 `sort_order`、首图作封面),`status=published` + `published_at`=当天 → 立即可见。

- 幂等键 = `collections.slug`(`<模特slug>-<写真slug>`),重复导入直接跳过、不动文件;
  采集重试前的「已存在」预检也用它(避免白下 1GB)
- 一级目录名 = 模特名;等于 `harvest.unsorted_dir`(如 `未分类`)时 `model_id` 留空
- 跳过 `.DS_Store`/`._*`/`__MACOSX`/隐藏文件/视频;移动后清理空目录(保留 library 根与 `_tmp`)
- 失败回滚:已移动的文件移回原位,不留半成品
- 触发点:① 采集归档成功后自动导入(try/except 隔离,入库失败不改任务状态)
  ② 后台采集页「扫描归档库导入」按钮(`POST /admin/harvest/import`)

### 灯箱修复与性能优化(2026-09,v1.0.0 前)

**竖屏图放大只显示上半截**:根因是 `.lightbox__stage` 为 `display:grid`,行高由内容决定,
图片的 `max-height:100%` 无解析基准被当作 `none` → 竖图只受宽度约束,溢出部分被
`overflow:hidden` 裁掉(横图不受影响,故此前未暴露)。修复:fit 模式图片改**绝对定位居中**
(`inset:0 + margin:auto`,百分比相对 stage 实际高度解析);放大模式回到文档流且 stage
`overflow:auto`(1:1 可平移,`safe center` 防回弹死区),取消放大自动回顶。

**切图卡顿(最差帧 111ms)**:根因是每张图都全尺寸解码 22MP/9MB 原图(约 84MB 位图上传 GPU)。
优化:fit/切图改走 `/t/1800` 缩放版(约 490 万像素,开销 1/7;服务端 `min(w, sw)` 只缩不放),
放大时后台升级原图 1:1(解码完无缝替换,不闪烁),每次切图预取相邻两张,过期响应丢弃
(快速连切不错屏);下载按钮仍指原图。实测最差帧 111ms → 21ms。

注:Chrome 窗口被遮挡时 rAF 暂停(动画看似卡住实为不渲染),属浏览器节流行为,非页面问题。

### 采集任务队列分页 + 状态筛选(2026-09 新增)

背景:原实现 SSR 取最近 100 条、轮询 API 取最近 30 条且整表重绘,旧任务(终态记录
只增不减)超过 30 条后从界面消失,重试/删除都够不着;两处上限不一致还会首屏闪烁。

实现要点:

- 每页 20 条(`JOBS_PER_PAGE`);状态筛选按分组(全部/进行中/已完成/已跳过/失败,
  `JOB_STATUS_GROUPS`),done 组含 `done+exists`、active 组含四种运行态 — 与
  `ix_jobs_status_id` 索引对齐,过滤 + 倒序取页都是索引扫描
- **轮询 API 分页感知**是关键:页面 2 秒整表重绘的设计下,页码/筛选状态由前端持有
  (`curPage`/`curStatus`),轮询透传 `?page=&status=`,否则任何分页都会被下一次轮询冲掉;
  API 返回 `page/totalPages/total`,越界页码收敛到最后一页(`_clamp_page`)
- SSR 与 API 共用 `_jobs_query`(一处改,两边一致);筛选胶囊计数来自一次
  `GROUP BY status` 查询
- 行内操作(重试/取消/删除)表单带 `back` 隐藏域回跳原筛选原页;`back` 只接受
  `?status=<组>&page=<n>` 白名单形态(正则校验),防开放重定向
- 新词条入 i18n STRINGS(上一页/下一页/第 x/y 页/共 n 条/状态名等,zh-CN/zh-TW)
- 测试:`tests/test_harvest_pagination.py`(分页边界、筛选、API、back 白名单、空态)

## 十二、删除写真集: 远端清理后台化(2026-10-20)

**症状**:管理后台点「删除」后转圈几十秒到几分钟;期间整站(含 `/healthz`)
一起无响应。线上实测:43 张的写真集 44s,137 张的 70s+,773 张的推算 6 分钟。

**根因(三层叠加)**:

1. `storage.purge_remote_of_collection` 同步跑在请求里,而 WebDAV 没有批量删除
   —— 每张照片 × 每个存储一次 HTTP DELETE。OpenList 驱动实测:**123 盘 0.098s/次,
   115 盘 0.479s/次**(115 侧并发无加速,服务端串行)。137 张 × 2 存储 = 274 次
   ≈ 70s,与日志完全吻合。
2. handler 是 `async def` 却在其中做同步网络 + 文件 IO → 事件循环被钉死。
   实测删除期间 `/healthz` 要等 22s 才被服务。
3. 删模特时按写真集串行清远端,最坏是「N 本 × 每本几分钟」的累加。

**修复**:

- 请求线程只做三件快事:删前**快照** `photo_uploads` 的远端路径(删行后会被
  级联清空,事后再查不到)、删 DB 行、删本地照片与缩略图缓存;
- 远端清理交 `purge_remote_async()` → 全局 4 线程池,按 200 条/批分片,
  失败只记日志(原本就是「尽力而为」语义);
- 后台清理可能跑几分钟,期间同一本写真集若被重新采集上传,远端路径完全相同
  —— 删前回查 `photo_uploads`,仍被引用的跳过(`_still_referenced`),避免
  误删刚传上去的新文件;
- 两个删除 handler 改回同步 `def`,由 Starlette 线程池执行,不再阻塞事件循环。

**效果**(同机实测):8 张 → 4.48s 降到 0.09s;40 张 → 22s 降到 0.12s,
期间 `/healthz` 8ms。

**代价**:进程在后台清理完成前退出(重启/更新)会留下远端孤儿文件 —— 与
「尽力而为」的原语义一致,日志里 `queued N remote files ... for background
purge` 与 `purged N remote files` 可对账。要彻底解决需把删除动作也做成
`upload_jobs` 那样的队列表,当前规模不值得。

**测试**:`tests/test_collection_delete_async.py`(handler 必须同步、请求不等
远端、模特删除逐本排队、重传竞态保护、按存储分组快照)。

## 十三、存储后端: openlist 类型 + 目录级删除 / 去重 / 并发 / 校验(2026-10-20)

新增 `type=openlist`(走 OpenList 的 `/api/fs/*`),与 `type=webdav`(只走
WebDAV 的 PUT/DELETE/MKCOL/PROPFIND)**并列**而不是替换:同一台 OpenList 上
两者能力对等,现场实测的耗时差异在 10% 以内,选型意义只在「服务端哪套接口
更稳、是否需要 API 特有功能」。两条 backend 都实现了下面四项优化。

### 1. 目录级删除

上传目录与写真集一一对应(`root/media/model/album`),所以删写真集不再需要
「一张一个 DELETE」:

| | 单张删除 | 目录删除 |
|---|---|---|
| 123 盘(40 张) | ~4.0s | **0.10s** |
| 115 盘(40 张) | ~19s | **0.25s** |

- webdav: `DELETE /dav/<dir>`(RFC 4918 集合递归);
- openlist: `POST /api/fs/remove {dir, names:[<dirname>]}`;
- 删前先列一次目录(webdav PROPFIND Depth:1 / `fs/list`),发现**快照之外**
  的文件就拒删(那说明写真集刚被重新导入并上传),退回逐文件删除 —— 竞态
  保护从「逐文件回查 photo_uploads」升级成「整目录守卫 + 逐文件回查」;
- 目录里混进新文件时仍按目录分组批量提交(openlist 一次 `fs/remove` 删多个
  name),不是一张一个请求。

### 2. MKCOL / mkdir 去重

WebDAV 的 MKCOL 与 OpenList 的 `fs/mkdir` 在网盘驱动上都不便宜:115 盘
一次 2.6s、123 盘 1.2s,而每张照片上传前都要确认目录存在。进程内
`CreatedDirs` 缓存 `(storage_id, api_url, root_dir) → 已建目录`,命中即 0
请求;目录被删后 `forget()` 连子孙一起失效。同一目录的第二批上传实测从
「每张 0.6s 的额外建目录」降到 0.03s。

### 3. 并发上传

两家协议都**没有批量上传**:WebDAV 一次一个 PUT;OpenList 的
`/api/fs/form` 是 multipart 但只认第一个 `file` 字段(塞两个会静默丢弃)。
唯一的提速维度是并发,worker 改为每个存储最多 4 个 PUT 在飞(主线程按序
读原图、有界队列背压,DB 仍只由主线程写,断点续传语义不变)。

实测 8 张 ~2MB:123 盘串行 10.1s → 4 路 4.6s(2.2x);115 盘 5.3s → 4.0s(1.3x)。

### 4. 上传校验

一组传完对**每个目录**做一次列表(不是每张一次),核对远端大小:不符的重传
一次,仍不符则任务 `failed` 并保留本地原图(可重传),不再出现「任务显示
完成、远端其实是截断文件」。列表失败(服务端抖动)只记日志跳过,不误判。

### 协议细节(实测)

| | WebDAV | OpenList API |
|---|---|---|
| 认证 | Basic(用户名+密码) | `POST /api/auth/login` 换 JWT,头 `Authorization: <token>`(无 Bearer) |
| 上传 | `PUT /dav/<path>` | `PUT /api/fs/put`,路径在 **`File-Path` 头**(必须 percent-encode,HTTP 头放不下中文) |
| 建目录 | `MKCOL`(逐级) | `POST /api/fs/mkdir`(一次递归建整条,幂等) |
| 删除 | `DELETE`(404 视为已删) | `POST /api/fs/remove {dir,names[]}` |
| 列目录 | `PROPFIND Depth:1`(XML) | `POST /api/fs/list`(JSON,分页) |
| 错误语义 | HTTP 状态码 | **永远 HTTP 200**,成败看 body 的 `code`;路径不存在 = `code 500` + `object not found` |
| 目录缓存 | 无 | `fs/list` 默认读 OpenList 的目录缓存,刚上传/刚删除时可能滞后 → 统一 `refresh=true`(代价:773 文件目录 123 盘 2.8s / 115 盘 0.6s) |
| 直链 | `/d/<path>` | `/d/<path>`(同一个 OpenList 直链,302 到网盘 CDN) |

`webdav` backend 不调用任何 `/api/*`,换成别的 WebDAV 服务端行为一致;
`openlist` backend 不碰 `/dav`。

115 盘的删除是上游异步的: `fs/remove` 偶发回 `errno 990009 删除操作尚未执行完成`,
重试(1.5s/4s 退避)后即可;后台清理的日志里看到它重试属于正常现象。

### 5. 静默丢失与回补(2026-10-20 线上事故)

123 盘的 `fs/put` **会回 200 但文件不落地**。1.9.0 之后靠校验能当场发现,
但当时本地原图可能已被另一个存储的收尾删掉 —— 照片的本地原图在上传成功后
即删, 它是所有存储共用的唯一字节来源。ID13/ID28 就是这么丢的两张(PNG,
19.7MB / 23.1MB), 表现为站点直链 302 解析失败 → 404。

全库体检(`scripts/repair_remote.py --dry-run`, 328 个目录):

| 存储 | 目录 | 缺失文件 | 说明 |
|---|---|---|---|
| OpenList-123(direct_link=1) | 328 | **57**(8 个写真集) | 全部来自 10-12 / 10-17 / 10-18 三次批量上传,那时还没有校验 |
| OpenList-115(纯备份) | 328 | 0 | 备份盘完整, 是唯一的回补来源 |

由此改了三处(`app/services/storage/worker.py`):

1. **原图删除推迟到本组全部落定之后**:`_delete_local_originals` 先查同写真集
   其它存储任务(只算启用的存储), 有 `failed` / `queued` / `running` 就整体
   不删, 在 `job.error` 里写「完成,保留本地原图(其他存储上传失败)」;
2. **校验没过的文件撤掉 `photo_uploads` 行**:上传时按 200 就记行, 不撤的话
   重试会把它们当已上传直接跳过, 任务变绿而文件仍然缺;
3. 新增 `scripts/repair_remote.py`:按目录 list 一次做体检(不是逐文件),
   缺失项依次从「本地原图 → 其它存储」取字节(校验字节数), 重传后再 list 复核;
   支持 `--dry-run` / `--storage` / `--collection`, 修不回来的列出来交人工。
   非 dry-run 时退出码 1 表示有文件既不在本地也不在任何备份存储。

### 6. 重启打断上传组 → 任务重排(2026-10-23)

重启容器时如果正好有一个上传组在跑, 任务会被记成 `failed`
「内部错误(详见日志)」。日志里其实是:

```
upload group [1019, 1020] crashed
RuntimeError: cannot schedule new futures after shutdown
  at worker.py:293  executor.submit(backend.upload, ...)
```

解释器退出时 `concurrent.futures.thread` 的 atexit 钩子先把**所有**
ThreadPoolExecutor 置成 shutting down, 上传主线程还在往线程池投下一张, 于是
`submit()` 抛错并冒到 `_consume_loop` 的兜底 `except` —— 任务本身没有任何
问题, 只是被进程退出掐断, 却被当成真失败, 还得手工重排(线上 572 / 689 各一
组, 4 条)。

现在 `_consume_loop` 先认这个特定的 `RuntimeError`
(`_is_shutdown_error`): 命中就 `_requeue_jobs` 把仍在 `running` 的任务放回
`queued`(`error=None`), 然后直接 `return` —— executor 已经全局关闭, 再循环
也没有意义, 进程随即退出。断点续传靠 `photo_uploads` 行, `photos_done` 下一
轮会按它重算, 重跑只补缺的那几张; 被掐断在飞的那几张会被幂等重传一次(远端
覆盖, 无副作用)。

注意只认这一句错误串: 其它异常照旧 `failed`「内部错误」, 别把真崩也变成静默
重排。

### 7. 静默丢失是概率事件 → 校验重传给三轮; 原图保留看「每个存储的最新任务」(2026-10-29)

用户报「任务 879 上传卡住了」:写真集 879(`Coser@Machi馬吉 - Castorice Swimsuit`,
131 张,每张 17-24MB)在 123 盘停在 **128/131**。真相不是卡住 —— 是那 3 张
(`020` / `063` / `110`)的 `fs/put` 回了 200 但文件没落地,单轮重传也没落地,
任务判 `failed`,而写真集列表页的上传列是按 `photo_uploads` 计数渲染的
(128/131 → 「partial」),看着就像卡在 98%。隔一阵手工单张重传,一次就上去了
(5.2s) → 结论:**静默丢失是过载时的概率事件,间隔重传比连着重传有效**。

- `_verify_job` 的重传从「一轮」改成 `_VERIFY_PAUSES = (0.0, 5.0, 15.0)` 轮,
  每轮重算还没落地的那些,间隔让服务端缓一下;三轮仍不符才判失败并撤
  `photo_uploads` 行。代价只在真的丢文件时发生(正常一本只多 1 次 list)。
- `_originals_needed` 改成**每个存储只看最新那条任务**(按 id 取 max,含自己):
  重试是新建任务,成功之后早先那条 `failed` 只是历史记录, 不该再把本地原图
  钉住 —— 否则 879 重试成功后仍报「完成,保留本地原图(其他存储上传失败)」,
  2.9GB 原图永远删不掉。

**线上处置**:879 补传走的正是「集合页上传按钮」这条正式路径(先给手工补传成功
的 020 补一行 `photo_uploads`, 免得多传一遍),新任务 1433/1434 秒级完成
131/131,两个存储都是 `done`,列表页显示「已上传 ✓」。全库复查「半截」的
写真集×存储只剩 3 条(col 861/862/863 的 115 盘, 那批是 403
`AccessDenied by bucket policy`, 与静默丢失无关)。

### 测试

- `tests/test_storage_backends.py`:进程内 stub 同时实现两套协议,断言
  「N 张上传只 MKCOL/mkdir 一次」「删目录 = 1 次请求」「有陌生文件时拒删并
  逐文件兜底」「校验能发现截断、重传后恢复」;
- `tests/test_upload_concurrency.py`:打桩 backend 记录峰值并发(2..4);
  校验不一致时任务必须 failed、**撤掉 photo_uploads 行**、保留原图;一个存储
  掉文件时另一个存储收尾**不得**删原图(两个存储都通过时才删);重启竞态
  (`cannot schedule new futures after shutdown`)任务回 `queued` 而不是
  `failed`, 而普通异常仍记 failed;
- `tests/test_upload_verify_retry.py`:静默丢包两轮后第三轮成功 → 任务不判
  失败;一直丢 → 判失败并撤行;重试新建的任务成功后,早先那条 `failed` 不再
  钉住本地原图(反过来最新那条失败仍保留);
- `tests/test_collection_delete_async.py`:后台清理 + 重传竞态守卫。
