# Photo Collection v1.9.10

写真作品管理与展示 Web 应用:FastAPI + Jinja2 SSR + 渐进增强前端,SQLite 存储,
内嵌采集 / 上传 Worker(自动抓取 → 归档 → 入库 → 可选上传外存)。面向 NAS /
Docker 单容器部署,另带一个 Compose 写的 Android 客户端。

> 应用名 "Photo Collection" 为品牌名,各语言界面下保持原文。

## 功能总览

- **前台**:发现页(精选轮播 + 虚化背景主题)/ 写真列表(瀑布流,大屏 6 列网格虚拟化,万级条目流畅滚动)/ 写真详情(照片墙 + 灯箱 + 档案推荐)/ 模特列表与详情(2/3 竖幅头像,生成式默认头像)/ 收藏(模特·写真·照片,带标签胶囊按钮)/ 搜索 / 个人中心
- **主题**:深色 / 浅色 / 虚化背景三态循环,首帧无闪烁(内联脚本同步),跨页背景静止(指纹比对免重淡入)
- **灯箱**:`←` `→` `ESC`、点击放大 1:1 平移、移动端滑动、相邻预取(fit 显示用 1800w 缩放版,放大时升级原图)、收藏/下载同排;管理员可「设为封面 / 设为模特头像」
- **后台**:仪表盘 / 模特·写真·标签·用户管理 / 采集下载控制台(扫描、队列、黑名单、模特名排除词、归档库一键导入)/ 标签补录 / 外部存储管理 / 系统设置
- **采集链路**(buondua):列表页 → 详情页解析(tag → 模特名识别,标签同步落库挂到合集与模特)→ ouo 短链跳转 → MediaFire / TeraBox 下载 → 解压 → 归档 `library/<模特名>/<写真>/` → 自动导入 media + 落库(published 立即可见);TeraBox 走登录 Cookie(见 `docs/terabox/`)
- **PikPak 链路**:油猴脚本在 mypikpak.com 勾选即入队(`/api/ext/pikpak`),服务端下载 → 归档 → 入库,与采集链路各自独立排队
- **外部存储**(可选):`imgbed` / `webdav` / `openlist` 三类,写真可自动或手动上传到图床 / 网盘;本地原图缺失时按优先级 302 到远端直链,失败回退流式代理
- **移动端**:Android 客户端(Compose,M0/M1 主链路)+ `/api/mobile/*` JSON API(Bearer token)
- **媒体服务**:`/media` 原图 + `/t/<w>[x<h>]` 按需缩略图(WebP,LANCZOS,磁盘缓存 immutable)
- **i18n**:简体中文 / 繁體中文,服务端 `t()` + 前端 js_strings,品牌名不译
- **全站卡片比例**:2/3 竖幅(列表/详情推荐/头像/搜索缩略图统一,减少封面裁切)

## 运行

需要 Python 3.12+(镜像基于 `python:3.12-slim`)。

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8777
# 打开 http://localhost:8777/  首次启动自动建库并 seed(demo 图片 + 账号)
```

默认账号:`admin / admin123`(管理员)、`demo / demo123`(普通用户)——**部署后请立即修改**。
不需要 demo 内容时置 `SEED_DEMO=0`;已有 demo 数据可用 `scripts/purge_demo.py` 清掉。

### Docker(NAS)

```bash
docker compose up -d --build
# 端口与采集开关:.env(参考 .env.example);数据落 ./data/{db,media,library}
# 非 UID 1000 主机:compose 里加 user: "<UID>:<GID>" 并 chown data/ 一次
```

发布镜像(多架构 amd64/arm64)在 GitHub Release 时自动构建推送至 GHCR:

```bash
docker pull ghcr.io/jinsfoni/photobook:latest
```

目录约定(可用环境变量覆盖,见 `app/config.py`):`data/` SQLite(WAL)、`media/` 图片库与缩略图缓存、`library/` 采集归档暂存区。

## 外部存储(可选)

管理后台 → 存储:填名称、类型、站点地址、账号、远端根目录即可,支持「测试连接」。

| 类型 | 协议 | 说明 |
|---|---|---|
| `imgbed` | CloudFlare ImgBed `/upload`、`/api/manage/*` | 图床。需要 upload 权限;测试连接与远端删除另需 list / delete 权限 |
| `webdav` | 只用 WebDAV:`PUT` / `DELETE` / `MKCOL` / `PROPFIND` | 任意 WebDAV 服务端(实测 OpenList `/dav`);不调用服务端的 `/api/*` |
| `openlist` | 只用 OpenList API:`/api/auth/login`、`/api/fs/*` | 登录换 JWT 后上传 / 删除 / 列目录;不碰 `/dav`。路径不存在等错误在 HTTP 200 的 body `code` 里 |

上传目录 = `root_dir` + 本地相对目录前两级(`模特/写真`),一本写真集对应一个远端目录,因此:

- **删写真集走目录级删除**:webdav 一次集合 `DELETE`,openlist 一次 `fs/remove`,不是一张一个请求
  (实测 40 张:123 盘 4.0s → 0.10s、115 盘 19s → 0.25s)。删前列目录做守卫,发现快照之外的
  文件(删完又立刻重新导入上传)就拒删并退回逐文件;
- **建目录去重**:`MKCOL` / `fs/mkdir` 结果进进程内缓存,同目录只付一次(115 盘建一级目录实测 2.6s);
- **并发上传**:每个存储最多 4 个 PUT 在飞(实测 123 盘 2.2x、115 盘 1.3x),断点续传不受影响;
- **上传校验**:每个目录传完列一次核对远端大小,不符重传一次,仍不符任务标记失败、撤掉该文件的
  上传记录并保留本地原图(下次重试才会真的重传);
- **静默丢失兜底**:网盘的 `fs/put` 会「回 200 但文件不落地」,本地原图因此推迟到同写真集的
  所有存储任务都成功后才删;`scripts/repair_remote.py` 可全库体检并从备份存储回补缺失文件
  (`--dry-run` 只报告,认不出的明细会列出来);
- **直链**:webdav / openlist 为 `api_url + /d/<路径>`,imgbed 为 `api_url + /file/<路径>`;
  服务端解析 302 后交给浏览器,图床/网盘字节不过 NAS;关闭直链即纯备份。

「优先级」决定多存储时的回源/302 顺序;「参与手动上传」「开启直链」可逐存储开关;
「自动上传(新入库)」只影响之后入库的写真,存量请到写真集列表手动上传。

## Android 客户端

`android/`(Compose,minSdk 31):登录 → 发现 → 写真列表 → 详情 → 灯箱(缩放/收藏/下载)。
构建 `cd android && ./gradlew :app:assembleDebug`,架构见 `docs/android-architecture.md`。

## 目录结构

```
app/
  main.py            FastAPI 入口(中间件、启动 seed、内嵌 worker)
  config.py          全部配置项(环境变量可覆盖)
  db.py / database.py  17 张表的模型与会话
  routers/           web(SSR)/ auth / admin / mobile_api / ext_api / photo_meta / search_api / favorites_api
  services/
    harvest/         采集:net(curl_cffi)/ pipeline(下载解压)/ terabox(登录 Cookie)/ worker(串行队列)/ filters(模特名识别)
    pikpak/          PikPak 队列(油猴脚本推送直链 → 下载 → 归档)
    storage/         外部存储:base(协议/目录缓存)/ webdav / openlist / imgbed / worker(并发上传)
    library_import.py 归档库 → media + 落库(幂等、可回滚)
    media.py         /media 原图与 /t 缩略图
    tagging.py       自动打标 / 标签补录
    avatar.py        生成式默认头像(SVG,确定性)
  templates/         Jinja2 SSR(前台 + admin)
  static/            app.css 设计系统 · app.js 运行时 · i18n
android/             Compose 客户端
scripts/             运维小工具(如 purge_demo.py)
assets/              早期静态原型稿(设计参照,非运行代码)
docs/                架构与决策记录(含采集链路维护日志、Android 架构)
tests/               pytest(377 用例,网络全部打桩)
```

## 测试

```bash
.venv/bin/python -m pytest        # 377 passed;不打真实网络
```

## 文档

- 架构与决策:`docs/architecture.md`(第十二节:删除写真集远端清理后台化;第十三节:存储后端与目录级删除 / 去重 / 并发 / 校验)
- Android 架构:`docs/android-architecture.md`
- 产品需求与 UI 设计:`UI需求.md`
