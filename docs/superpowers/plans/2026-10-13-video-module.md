# 写真视频模块(add-video 分支)

> 依据:用户确认的架构方向 —— 「写真视频是单独模块,与写真集分开存;视频存 `video/` 目录,目录规则与写真集一致;顶部导航『写真集』后新增『写真视频』入口」。
> 本方案**不修改**写真集(Collection/Photo)的任何现有行为,视频是平行的一套:独立表、独立目录、独立页面、独立管理页。
> 前两版方案(把视频挂成写真集的附属 / 复用 collections 表)被否,定稿即本版:平行模块。

## Task 0 — 分支

- [x] `git checkout -b add-video`(main 干净起步),所有改动在该分支

## 一、总体设计

```
写真集(现有,不动)                 写真视频(新模块,平行)
/media/<模特slug>/<写真slug>/      video_dir = ./video
collections 表                     video_albums 表
photos 表                          videos 表
/collections  /collections/{slug}  /videos    /videos/{slug}
/admin/collections ...             /admin/videos ...
封面:缩略图两档(900/2400)          封面:ffmpeg 抽帧 → 同一套 /t/s{w}/ webp 缓存
播放:灯箱看图                      播放:/video/{rel} + Range → <video>
上传:PhotoUpload                   VideoUpload(平行表)
```

关键复用决定(不重造轮子):

| 能力 | 复用方式 |
|---|---|
| slug 规则 | `library_import.slugify`/`_unique_slug` 原样复用(`_unique_slug` 本就泛型,传 `VideoAlbum` 即可) |
| 目录判定(一级=模特、二级=写真) | `import_library` 的目录发现逻辑复用:扫描 library 时把含视频的目录也收进来 |
| 缩略图缓存布局与档位(900/2400、q88/q78、短边钳制) | `media._cache_path`/`_make_webp` 原样复用 —— **封面帧就是一张 PIL 图片**,喂进同一管线,URL 与照片同构(`/t/s900/<rel>.webp`),前端卡片代码可镜像 |
| 存储 backend(imgbed/webdav 上传、302 直链、Range 流式代理) | `storage/base.py` 协议不变;worker 队列/断点/删本地逻辑平行复制 |
| 管理后台 CRUD/分页/上传上下文 | `admin.py` 的 `_search_q`/`_paged_items`/`_collections_upload_ctx` 泛型部分复用,列表模板平行复制 |
| 收藏 | `favorites` 表不动;`target_type` 新增值 `"video_album"`(11 字符,String(12) 放得下)与 `"video"` |
| 前端虚拟化列表 | `collections.html` 的 vm-grid 引擎 + `videos.html` 复制;`app.js` 的 `NAV`/`activeKey()`/footer 各加一项 |

## 二、Task 分解

### Task 1 — 数据层与配置

**`app/db.py`**(新增,不动现有表)

- `VideoAlbum`:镜像 `Collection` —— `id`/`slug`(unique)/`model_id`(FK SET NULL)/`title`/`cover_video_id`(FK videos.id SET NULL)/`published_at`/`status`/`featured`/`source_serial`/`created_at`/`updated_at`;关系 `videos`(cascade delete-orphan,order_by sort_order,lazy selectin)、`tags`(secondary **新关联表** `video_album_tags`)、`model`
- `Video`:`id`/`album_id`(FK CASCADE)/`filename`(String(255),**/video 相对路径**)/`width`/`height`/`duration`(Float NULL)/`poster`(String(400) NULL,封面帧 webp 相对路径,同缓存树)/`sort_order`/`created_at`;唯一约束 `uq_video_file(album_id, filename)`
- `VideoAlbumTag`:`album_id`+`tag_id` 双主键(FK 均 CASCADE)
- `VideoUploadJob`:`album_id`/`storage_id`/`status`/`files_done`/`files_total`/`error`/时间戳(镜像 `UploadJob`)
- `VideoUpload`:`video_id`(FK CASCADE)/`storage_id`/`remote_path`/`created_at`;唯一约束 `uq_video_upload(video_id, storage_id)`
- `Favorite` 注释补 `video_album | video`(列不动)
- 文件头 docstring「12 张表」→ 17 张

**`app/config.py`**:`video_dir: Path = Path("./video")`;`ensure_dirs()` 加入;新增 `video_frame_at: float = 1.0`(封面帧取秒点,env 可覆盖)

**`docker-compose.yml`**:volumes 加 `./data/video:/data/video`;**`Dockerfile`**:mkdir 加 `/data/video`;apt 行加 `ffmpeg`(抽帧依赖,debian slim 源内)

**`app/database.py`**:新表由 `create_all` 建;`_migrate()` 无需加语句;**新增 `_fix_url_unsafe_video_slugs()`** 挂在 `_migrate()` 末尾(与 `_fix_url_unsafe_slugs` 同构:重算 VideoAlbum slug + 重命名 `video/` 目录 + 同步 `Video.filename` 前缀;幂等,只对含 `#%&?` 的行动手)

### Task 2 — 视频服务 `app/services/video.py`(新文件)

镜像 `media.py` 的职责分工,只做视频相关:

- `serve_video(rel, request)`:**`FileResponse` + `media_type` 按扩展名映射**(mp4/m4v→video/mp4,mov→video/quicktime,mkv→video/x-matroska,webm→video/webm,ts→video/mp2t)。Starlette `FileResponse` 原生支持 Range/206,**拖动进度条零额外代码**;本地缺失 → `remote_redirect` 302 → `remote_stream`(已透传 Range)→ 404,逻辑与 `media.serve_media` 同构
- `serve_poster(rel)`:封面帧路由 —— 查缓存(`_cache_path(900,...)` 同档)命中即回;未命中且本地视频在 → ffmpeg 抽帧 → `media._make_webp` 两档(900/2400)落缓存 → 回 900 档;都不在 → 404(前端回退写真首图/占位)
- `probe(path) -> (w, h, duration)`:`ffprobe -show_streams -show_format` JSON,超时 30s,失败返回 `(None, None, None)`
- `extract_frame(path, at) -> bytes | None`:`ffmpeg -ss {at} -i {path} -frames:v 1 -f image2pipe -vcodec mjpeg -`(管道直出,**不落临时文件**);`shutil.which("ffmpeg")` 为 None 时全链路降级
- `purge_video_album_files(slug, filenames)`:删文件本体 + 封面缓存(按规格目录 rmtree)+ `video/` 空目录清理 + 收藏记录(`target_type=="video_album" AND target_key==slug` + `target_type=="video" AND target_key LIKE "slug:%"`),结构与 `media.purge_collection_files` 平行
- 封面入队 worker:镜像 `media._thumb_queue`,队列元素为 album slug;`ensure_video_worker()`/`queue_video_posters(slug)`/`_publish_ready_album(slug)`(processing → published 并触发 `_auto_upload_new_video_album`)
- `recover_stuck_processing_albums()`:重启自愈,`main.py` lifespan 调用

**`app/main.py`**:注册 `GET /video/{path:path}`(同步 def,注释说明:视频是阻塞 IO,交线程池)、`GET /poster/{path:path}`;lifespan 加 `video.ensure_video_worker()` / `video.recover_stuck_processing_albums()`

### Task 3 — 导入管线 `app/services/library_import.py`

- `list_videos(album_dir, recursive=True) -> list[Path]`:`VIDEO_EXTS` 收集 + 同 `_is_junk`/自然序
- **`import_video_album(...)`**:复制 `import_album` 结构,替换点:
  - 目标根 `media_dir → settings.video_dir`;表 `Collection/Photo → VideoAlbum/Video`
  - 无图不再是跳过条件:`if not images and not videos: skipped`
  - 移动循环:视频文件 → `Video(filename=f"{owner_slug}/{dest_dir.name}/{name}", width/height/duration 由 `video.probe` 给, sort_order=i)`
  - 首视频设 `cover_video_id`
  - 抽帧:`video.extract_frame` → `media._make_webp` 两档入缓存 → `Video.poster` 记 rel;ffmpeg 缺失/失败 → poster=None,前端回退
  - 回滚、`_prune_empty`、`queue_video_posters` 同图片版
- **`import_library` 改动(最小)**:目录发现已覆盖所有二级目录,循环里改为 —— 该目录有图片走 `import_album`,有视频走 `import_video_album`,**两者都有则先图片后视频各建一个 album**(写真与视频分成两个模块的条目,符合「分开存」);stats 增加 `video_albums`/`video_files` 字段(现有 `videos` 计数语义保留)
- `tests/test_library_import.py`:
  - **改写 `test_import_leaves_videos`** → `test_import_moves_videos_to_video_dir`:视频移入 `video/`、建 Video 行、library 侧清空
  - 新增 `test_import_video_only_album`(纯视频目录不再 skipped)
  - 新增 `test_import_album_with_both_photo_and_video`(同目录 → 两个 album)
  - 新增 `test_video_import_without_ffmpeg_degrades`(monkeypatch `shutil.which` → None:导入成功,`poster is None`,文件仍在)

### Task 4 — 存储上传 `app/services/storage/`

- `__init__.py`:
  - `_MIME_BY_EXT` 加视频映射
  - `remote_urls(rel)`:**按扩展名分支** —— 图片走 Photo,视频走 Video(两个查询,任一命中即出 URL)
  - `purge_remote_of_collection(album_id)` 平行加 `purge_remote_of_video_album(album_id)`(join Video/VideoUpload)
- `worker.py`:
  - `enqueue_video_album(album_id, storage_ids)`:镜像 `enqueue_collection`,`total = len(album.videos)`
  - `_run_video_group(job_ids)`:镜像 `_run_group` —— `remote_root` = `videos[0].filename` 前两段(目录规则一致,直接复用);逐文件读 → 并行上传 → `VideoUpload` 记录;断点续传同构
  - `_delete_local_videos(s, st, videos, job)`:**删除门槛多一条** —— 已传所有启用存储 **且封面两档已在盘**(否则封面永远无法再生,比图片更严格:图片删了还能回源重生成缩略图,视频删了连帧都抽不了)
  - `_consume_loop` 处理两类 job(同线程,按 status 取最早;两类互不阻塞)
  - `recover_stuck_running` 覆盖 VideoUploadJob

### Task 5 — Web 前台

**`app/routers/web.py`**

- 复制 trio:`_video_album_card` / `_video_album_payload` / `_published_video_albums`(字段与写真版对齐:`cover`(封面 rel,优先 `cover_video.poster`,回退首视频 poster,再回退 None)、`count`、`videoCount`、`tags`、`created`、`model_*`、`videos:[{id,file,w,h,duration,poster}]`)
- `GET /videos`(镜像 `/collections`:q/tag/model 筛选 + 虚拟化数据池 + tag 计数)
- `GET /videos/{slug}`(镜像详情:404 规则、next 推荐、`payload["next"]`)
- `_model_payload` 加 `videoCount`/`videoAlbumCount`(模特页 facts 表展示,不改现有字段)
- `/favorites` 页加 `video_album` 段(键 = album slug)与 `video` 段(键 = `f"{album_slug}:v{idx}"`,**v 前缀与照片键区分**);`_fav_keys` out dict 加两个桶
- `/profile` recent 段可选加视频(低优先)

**`app/routers/favorites_api.py`**:type 白名单加 `"video_album"`、`"video"`;`list_favorites` out dict 加桶

**`app/routers/search_api.py`**:结果加 `videos` 组(匹配 `title + model.name + tags`,返回 `href=/videos/{slug}`);`app/static/app.js` `renderSearchResults` 平行加一组

**`app/templating.py`**:`boot_json` stats 加 `videoAlbums`;`_blur_src` 加 `path.startswith("/videos/")` 分支(取该视频专辑封面)

**模板**

- 新增 `app/templates/videos.html`:**复制 `collections.html` 全文**(虚拟化引擎原样,`coverUrl` 同 `/t/s900/`),改数据键名与 `page="videos"`
- 新增 `app/templates/video.html`(视频详情页):复制 `collection.html` 骨架;瓦片渲染:
  ```js
  '<img src="' + (v.poster ? '/t/s900/' + v.poster + '.webp' : 占位) + '">' +
  '<span class="video-tile__badge">时长 mm:ss</span>' +   // 新增 CSS 类
  '<button data-video-index="' + i + '">'                   // 灯箱入口
  ```
- `collection.html` **不动**;`favorites.html` 加两个 tab(Video albums / Videos);`discovery.html` 不动(可选后续)

**`app/static/app.js`**

- `NAV` 数组 **在 `/collections` 项之后**插入 `{ href: "/videos", label: t("Videos"), key: "videos" }` —— 满足「写真集后面加写真视频」
- `activeKey()` 加 `if (p.indexOf("/videos") === 0) return "videos";`
- footer Browse 列加 `/videos` 链接
- 灯箱:`paint()` 加视频分支 —— 主图区渲染 `<video controls preload="metadata" poster="/t/s900/{poster}.webp" src="/video/{file}">`;**完全绕开**双缓冲/`lbReady`/`upgradeOriginal`(这些是图片解码专用);垫底层与氛围层**继续复用**(poster 就是普通 webp,`lightboxSrc(p,w)` 对视频返回 poster rel)
- 灯箱 fav 按钮:`data-fav="video"` + key `slug:v{index}`;下载 href `/video/{file}`
- `ICONS` 加 `play`(圆底三角);`state.favs` 加 `video_album: []`、`video: []`;`loadFavs()` 遍历数组补两项;`syncAll()` 的 `[data-fav-count]` 自动覆盖新 tab
- `bindVideoTiles(root)`:镜像 `bindPhotoTiles`,读 `window.PB_DATA.videos`,`open({videos, index, ...})`

**`app/static/app.css`**:`.video-tile__badge`(左下时长胶囊,半透明黑底白字 tabular-nums)、`.video-tile__play`(中央播放三角,悬停显现)、`.lightbox__video`(contain 全屏 + controls 不遮挡 chrome 的 padding)

**`app/i18n.py`**:chrome 段加 `"Videos": {"zh-CN": "写真视频", "zh-TW": "寫真影片"}`;新增段落 `# ---- Videos 页 ----`:`"{n} videos"`、`"Open video {n} full screen"`、`"Favourite video album"`、`"Favourite video"`、`"No favourite videos yet."`、`"No videos yet."`、`"{n} videos · {m}"`;模特页 facts 加 `"Videos"`

### Task 6 — 管理后台

**`app/routers/admin.py`**

- `GET /admin/videos` + `_video_albums_list_payload` + `_video_albums_upload_ctx`(复制 collections 三件套,换表换路由)
- `GET/POST /admin/videos/new`、`GET/POST /admin/videos/{id}/edit`、`POST /admin/videos/{id}/delete`(复制现有段;删除时 `purge_remote_of_video_album` + `video.purge_video_album_files` + 模特无写真无视频才删模特 —— **删除条件要同时查两边**)
- `POST /admin/videos/{id}/tags`、`/tags/{tag_id}/delete`(复制现有)
- `POST /admin/videos/{id}/upload` → `storage_worker.enqueue_video_album`
- dashboard 统计加 `videos`;`/admin/harvest/import` flash 文案加视频数;侧边导航加「写真视频」入口
- ffmpeg 缺失提示:import 结果与 dashboard 各显示一次(`video.ffmpeg_available()` 缓存查询)

**模板**:`admin/videos.html`(复制 `collections.html`,路由换 `/admin/videos`、API 换 `/admin/api/videos`)、`admin/video_album_form.html`(复制 `collection_form.html`,「照片」区改为「视频文件」只读列表附时长/尺寸)、dashboard 侧导航 + 统计卡

### Task 7 — 移动端 API `app/routers/mobile_api.py`

- `_video_album_payload` / `_video_album_card`(加 `coverThumb`;`videos` 用 `idx`)
- `GET /api/mobile/videos`(分页 + sort)、`GET /api/mobile/videos/{slug}`
- `_model_payload` 同步 `videoCount`
- `/api/mobile/favorites/resolve` 加 `videoAlbums`/`videos` 段;`/favorites` POST 白名单加两型
- `/api/mobile/search` 加 videos 组

### Task 8 — Android 端

- `gradle/libs.versions.toml`:`[versions]` 加 `media3 = "1.8.1"`;`[libraries]` 加 `media3-exoplayer`、`media3-exoplayer-hls`、`media3-ui`
- `app/build.gradle.kts`:dependencies 加三个 artifacts
- `data/remote/dto/Dtos.kt`:`VideoAlbumDto`/`VideoDto`(`idx/file/w/h/duration/poster`)、`VideoAlbumCardDto`;`FavoritesDto` 加 `videoAlbum`/`video`;`FavoritesResolveDto` 加 `videoAlbums`/`videos` + `FavVideoDto`/`FavVideoAlbumDto`
- `data/remote/MediaUrls.kt`:加 `video(baseUrl, rel)`(=`/video/`)、`poster(baseUrl, rel)`(=`/t/s900/{rel}.webp`,与图片 thumb 同函数)
- `data/repo/CollectionsRepository.kt`:detail/card 映射加视频;hero 兜底:无照片时用首视频 poster
- `ui/models/Models.kt`:`VideoItem`/`VideoAlbumDetail`;`Favorites` 加 `videoAlbum`/`video` 分支
- `ui/screens/detail/DetailScreen.kt`:视频专辑详情屏 —— 视频瓦片 poster + 时长角标;`onOpenVideo(slug, idx)`
- `ui/screens/lightbox/`:`VideoPage`(`AndroidView` + `PlayerView`,ExoPlayer `remember` 释放,`playWhenReady=false` 省流量,poster 垫底首帧就绪淡出);Pager page 按 `kind` 分支
- `PhotoDownloader.kt`:`downloadVideo(url, fileName)` —— `MediaStore.Video.Media` + `RELATIVE_PATH = Movies/PhotoBook` + MIME 按扩展名
- `ui/icons/StrokeIcons.kt`:`PlayIcon`
- `ui/screens/favorites/`:`FavTab` 加 `VIDEO_ALBUMS`/`VIDEOS`;`FavoritesScreen` 加两 tab + masonry(复用 `arrangeTwoColumnWall`)
- `ui/nav/AppRoot.kt`:路由 `videos`、`video/{slug}`、灯箱支持视频页
- 测试:Repository 映射、FavoritesViewModel video tab、`VideoPage` Compose 冒烟

### Task 9 — 测试与文档

**pytest**

- Task 3 四例(import);`tests/test_video_media.py`:poster 200/404、`/video/` Range 206(本地文件)、视频 MIME、ffmpeg 降级、`_safe_path` 穿越;`test_media_proxy.py`:视频 302/回源(Range 透传);`test_favorites.py`:`video_album`/`video` 增删查;`test_pages.py`:`/videos` 与详情 payload;`test_mobile_api.py`:videos 段形状;`test_admin.py`:videos CRUD + 上传上下文;`test_i18n.py`:新 key 三语言齐
- `test_library_import.py::test_video_import_records_poster_rel` 锁死「封面帧 rel 回写 DB」这条链路(曾断过:worker 只落缓存不回写,封面永远空)

**文档**

- `docs/architecture.md`:§五表清单 12→17(补 5 张表);§六补「视频独立根目录 `/video` + ffmpeg 抽帧 + Range 播放」,删「暂不做视频」表述;§九加 M5 视频模块;新增 §十二 写真视频模块实现记录
- `docs/android-architecture.md`:§2 加 media3、§6.1 视频管线、§8 YAGNI 补直播流不做、§9 加 M5 里程碑、§10 测试策略补视频;追加 §13 M5 偏差记录
- `README.md`:目录结构补 `video/`、`services/video.py`;功能列表补视频管理
- `docs/superpowers/plans/2026-10-13-video-module.md`:本方案落档

## Task 顺序

1. Task 1(表+配置+部署)→ Task 2(video 服务)→ Task 3(导入):后端最小闭环,`pytest tests/test_library_import.py` 绿
2. Task 4(存储上传)→ Task 5(Web 前台)→ Task 6(admin):Web 全链路可用
3. Task 7(移动 API)→ Task 8(Android)
4. Task 9(测试补齐 + 文档)

每步独立可验证;任一步停下,写真集现有功能零影响(视频是纯增量)。所有改动在 `add-video` 分支,完成后提交合并由用户决定。

## 验证命令

```bash
# 后端
.venv/bin/python -m pytest tests/ -q
# 手工:导航「写真视频」→ 列表筛选/排序 → 详情播放(拖动进度条验证 Range)→ 收藏 → 收藏页两 tab
# admin:/admin/videos 新建/编辑/删除/上传/标签

# Android
cd android && ./gradlew :app:assembleDebug :app:testDebugUnitTest -q
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Docker(含 ffmpeg)
docker compose up -d --build
docker compose exec photobook ffmpeg -version | head -1
docker compose exec photobook curl -fsS -H 'Range: bytes=0-99' http://127.0.0.1:8777/video/<rel>.mp4 -o /dev/null -w '%{http_code}\n'  # 期望 206
```

## 风险与对策

| 风险 | 对策 |
|---|---|
| ffmpeg 不在镜像/装不上 | 全链路降级:视频照常导入播放,封面回退写真首图/占位;`shutil.which` 一处开关;admin 提示 |
| 删除本地视频后封面无法再生 | 删本地门槛加「封面两档已缓存」;poster 与视频同目录语义,`purge_video_album_files` 一并清 |
| `Favorite.target_type` 白名单漏改 | 四处同步:favorites_api、mobile POST、web `_fav_keys`、mobile resolve 分桶;测试对每型各写一例 |
| 视频专辑与写真相同目录(同一 library 目录混有图和视频) | `import_library` 分支处理:图片建 Collection、视频建 VideoAlbum,两个模块各自一条目 |
| 大视频 seek 拖累灯箱 | 视频分支完全绕开图片双缓冲/预取逻辑,只保留 poster 垫底 |
| media3 与 compileSdk 37 兼容 | 版本以 Gradle 同步为准,冲突降 1.7.x |
| `_fix_url_unsafe_slugs` 式迁移遗漏视频侧 | `_fix_url_unsafe_video_slugs` 平行实现,video/ 目录重命名 + `Video.filename` 前缀同步,幂等 |

## 完成状态(add-video 分支)

| Task | 状态 | 说明 |
|---|---|---|
| 0 分支 | ✅ | `add-video` |
| 1 数据层与配置 | ✅ | 5 张新表 + `video_dir` + compose/Dockerfile(ffmpeg)+ slug 修复 |
| 2 视频服务 | ✅ | `services/video.py` + `/video` `/poster` 路由 + worker |
| 3 导入管线 | ✅ | 纯视频目录 / 图文混合目录分支 + 抽帧回写 poster |
| 4 存储上传 | ✅ | 视频 job 队列 + 删本地门槛(封面两档已缓存) |
| 5 Web 前台 | ✅ | `/videos` 列表与详情、收藏两 tab、搜索分组、导航入口 |
| 6 管理后台 | ✅ | `/admin/videos` CRUD + 上传 + 标签 + dashboard |
| 7 移动 API | ✅ | `/api/mobile/videos` 列表/详情 + 收藏/搜索分组 |
| 8 Android | ✅ | media3 播放器 + 视频列表/详情/灯箱/下载/收藏两 tab |
| 9 测试与文档 | ✅ | 后端 320 passed;Android 51 tests + assembleDebug;四份文档已更新 |

实施中修掉两个真 bug(详见 `docs/android-architecture.md` §13 踩坑记录):

1. `Video.poster` 从不回写 → 封面永远空(导入时同步回写 + worker 补写 + 测试锁死)
2. `/video/` 与 `/poster/` 被登录墙拦住 → 匿名播放 302(中间件按 `/media` 同级放行)
