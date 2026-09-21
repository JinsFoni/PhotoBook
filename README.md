# Photo Collection v1.0.0

写真作品管理与展示 Web 应用:FastAPI + Jinja2 SSR + 渐进增强前端,SQLite 存储,
内嵌串行采集 Worker(自动抓取 → 归档 → 入库)。面向 NAS / Docker 单容器部署。

> 应用名 "Photo Collection" 为品牌名,各语言界面下保持原文。

## 功能总览

- **前台**:发现页 / 写真列表(瀑布流)/ 写真详情(照片墙 + 灯箱)/ 模特列表与详情 / 收藏(模特·写真·照片)/ 搜索 / 个人中心
- **灯箱**:`←` `→` `ESC`、点击放大 1:1 平移、移动端滑动、相邻预取(fit 显示用 1800w 缩放版,放大时升级原图)
- **后台**:仪表盘 / 模特·写真·标签·用户管理 / 采集下载控制台(扫描、队列、黑名单、模特名排除词、归档库一键导入)
- **采集链路**:buondua 列表页 → 详情页解析(tag → 模特名识别)→ 下载 → 解压 → 归档 `library/<模特名>/<写真>/` → 自动导入 media + 落库(published 立即可见)
- **媒体服务**:`/media` 原图 + `/t/<w>[x<h>]` 按需缩略图(WebP,LANCZOS,磁盘缓存 immutable)
- **i18n**:简体中文 / 繁體中文,服务端 `t()` + 前端 js_strings,品牌名不译

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8777
# 打开 http://localhost:8777/  首次启动自动建库并 seed(demo 图片 + 账号)
```

默认账号:`admin / admin123`(管理员)、`demo / demo123`(普通用户)——**部署后请立即修改**。

### Docker(NAS)

```bash
docker compose up -d --build
# 端口与采集开关:.env(参考 .env.example);数据落 ./data/{db,media,library}
```

目录约定(可用环境变量覆盖,见 `app/config.py`):`data/` SQLite(WAL)、`media/` 图片库与缩略图缓存、`library/` 采集归档暂存区。

## 目录结构

```
app/
  main.py            FastAPI 入口(中间件、启动 seed、内嵌 worker)
  config.py          全部配置项(环境变量可覆盖)
  db.py / database.py  12 张表的模型与会话
  routers/           web(SSR)/ auth / admin / favorites_api / search_api
  services/
    harvest/         采集:net(curl_cffi)/ pipeline(下载解压)/ worker(串行队列)/ filters(模特名识别)
    library_import.py 归档库 → media + 落库(幂等、可回滚)
    media.py         /media 原图与 /t 缩略图
  templates/         Jinja2 SSR(前台 + admin)
  static/            app.css 设计系统 · app.js 运行时 · i18n
assets/              早期静态原型稿(设计参照,非运行代码)
docs/architecture.md 架构与决策记录(含采集链路维护日志)
tests/               pytest(117 用例,网络全部打桩)
```

## 测试

```bash
.venv/bin/python -m pytest        # 117 passed;不打真实网络
```

## 文档

- 架构与决策:`docs/architecture.md`
- 产品需求与 UI 设计:`UI需求.md`
