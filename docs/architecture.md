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
