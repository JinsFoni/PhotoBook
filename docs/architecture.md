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

### 测试

- `tests/test_storage_backends.py`:进程内 stub 同时实现两套协议,断言
  「N 张上传只 MKCOL/mkdir 一次」「删目录 = 1 次请求」「有陌生文件时拒删并
  逐文件兜底」「校验能发现截断、重传后恢复」;
- `tests/test_upload_concurrency.py`:打桩 backend 记录峰值并发(2..4);
  校验不一致时任务必须 failed、**撤掉 photo_uploads 行**、保留原图;一个存储
  掉文件时另一个存储收尾**不得**删原图(两个存储都通过时才删);重启竞态
  (`cannot schedule new futures after shutdown`)任务回 `queued` 而不是
  `failed`, 而普通异常仍记 failed;
- `tests/test_collection_delete_async.py`:后台清理 + 重传竞态守卫。
