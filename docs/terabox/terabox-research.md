# TeraBox 直链下载调研（2026-10 实测）

> 目标链接：`https://dm.terabox.com/chinese/sharing/link?surl=0Y8ZvbwJrqOO4n35IAOVLQ`
> 实测时间：2026-10-19　环境：macOS / Python 3.14 / Chrome 141

---

## 0. 一句话结论

**2026 年起，TeraBox 已经不再给匿名会话下发 `dlink`（直链）。** 分享页能列文件、能看到大小，但点“下载”会弹登录框；直接调 API 会返回
`errno 400310 "need verify_v2"` 或 `errno 2`。

GitHub 上目前还能用的项目，思路基本只有两种：

1. **登录 Cookie（`ndus`）+ 官方 API** —— 主流、可靠，本文脚本就是这条路线；
2. **第三方账号池 / 代理服务** —— 别人替你登录，稳定性和隐私都不可控。

所以你需要的不是“找一个新的解析接口”，而是**准备一个已登录的 TeraBox Cookie**。

---

## 1. 你这个链接的实测结果

不登录也能拿到的元数据（脚本 `--info` 已跑通）：

| 字段 | 值 |
| --- | --- |
| 文件名 | `[Espacia Korea] EXC#115 Saika (河北彩花) uncensored.rar` |
| 大小 | 311,296,782 字节（296.88 MB） |
| `shareid` | 667331552 |
| `uk` | 4398292733952 |
| `fs_id` | 92076871386472 |
| `md5` | 7fc6c7d18d3f5a14f783e1a697b4bb6f |

再往下拿 `dlink` 时（未登录）：

```
/share/download → {"errno":2}                  # 浏览器同源请求
/share/download → {"errno":400310,"errmsg":"need verify_v2"}  # curl 直连
```

带上登录 Cookie（`ndus`）后复测：`/share/download` 返回 `errno 0` 和 `dlink`，302 到 CDN 后
`Range: bytes=0-1023` 返回 **206**、文件头为 `Rar!`，说明直链有效。**CDN 侧同样校验 `ndus` Cookie**，
所以直链不能脱离 Cookie 单独发给别人。

---

## 2. 官方前端到底怎么拿直链

我把 `dm.terabox.com` 的前端 bundle 拆开看了，下载逻辑在懒加载 chunk 里，核心是这一段：

```js
// _downloadByDlink()
Wt({ shareid, sign, timestamp }, {
  fid_list: JSON.stringify([fs_id]),
  uk,
  primaryid: String(shareid)
})
// → GET /share/download?scene=purchased_list&...&product=share&nozip=0
```

完整链路：

| 步骤 | 请求 | 作用 |
| --- | --- | --- |
| 1 | `GET /chinese/sharing/link?surl=<surl>` | 拿 `jsToken`（页面里 `fn("HEX")`）+ 匿名 Cookie（`TSID` / `browserid` / `csrfToken`） |
| 2 | `GET /api/shorturlinfo?shorturl=1<surl>&root=1&clientfrom=h5&psign=0&jsToken=…` | 文件列表 + `sign` / `timestamp` / `shareid` / `uk` / `randsk` |
| 3 | `GET /share/list?shorturl=<surl>&root=1` | 文件列表；**匿名时没有 `dlink` 字段** |
| 4 | `GET /share/download?scene=purchased_list&shareid=…&sign=…&timestamp=…&fid_list=["<fs_id>"]&uk=…&primaryid=…&product=share&nozip=0` | **登录后才返回 `dlink`** |
| 5 | `GET <dlink>` | 302 到 CDN，开始下载 |

几个容易踩的坑：

- `shorturlinfo` 的 `shorturl` 要**补一个前导 `1`**（`surl` 本身不带 `1` 时要补）；
- 必须带 `clientfrom=h5&psign=0`，否则匿名请求直接 `400210 need verify_v2`；
- 第 1 步拿到的匿名 Cookie 要一起带上，否则同样触发 `verify_v2`；
- `sign`/`timestamp` 是**短时效**的，拿到 `dlink` 要立刻下载，别缓存。

另外，前端 `smartDownload()` 里还有个限制：**单文件 < 50 MB 才走网页直下，≥ 50 MB 会引导你装 PC 客户端**。你这个 297 MB 的文件在网页端本来就不会给你直链按钮。

---

## 3. GitHub 项目盘点

按“现在还能不能用”排序（star 数为 2026-10-19 抓取）：

### ✅ 仍然活跃、思路正确

| 项目 | ★ | 语言 | 最近推送 | 说明 |
| --- | --- | --- | --- | --- |
| [Alex-0099/Terabox-DL](https://github.com/Alex-0099/Terabox-DL) | 1 | Python | 2026-10-07 | **最贴近你的需求**：CLI，`ndus` Cookie，多线程、断点续传、递归目录、交互选择 |
| [seiya-npm/terabox-api](https://github.com/seiya-npm/terabox-api) | 42 | Node.js | 2026-10-14 | 账号级 SDK（登录/上传/分享/下载），适合二次开发，不是匿名解析器 |
| [abdul97233/TeraBox-Downloader-Bot](https://github.com/abdul97233/TeraBox-Downloader-Bot) | 56 | Python | 2026-10-11 | Telegram Bot，不想登录网页可以用它中转 |
| [aruxyz/trauso](https://github.com/aruxyz/trauso) | 87 | Rust + React | 2026-01-10 | Tauri 桌面 GUI，内置多下载服务器 + aria2，Windows 安装包开箱即用 |
| [Armanidrisi/Terabox-downloader-telegram](https://github.com/Armanidrisi/Terabox-downloader-telegram) | 131 | JavaScript | 2026-06-29 | Telegram Bot，star 最高的一批 |

### ⚠️ 已归档 / 已明确失效（别再浪费时间）

| 项目 | ★ | 状态 | 原因 |
| --- | --- | --- | --- |
| [maiquocthinh/Terabox-DL](https://github.com/maiquocthinh/Terabox-DL) | 130 | 已归档（2024-02） | 旧 `/share/list` 直接带 `dlink` 的接口早已下线 |
| [Hrishi2861/Terabox-Downloader-Bot](https://github.com/Hrishi2861/Terabox-Downloader-Bot) | 92 | 已归档（2025-04） | 同上 |
| [0xarchit/Terabox-Downloader](https://github.com/0xarchit/Terabox-Downloader) | 97 | 2025-06 停更 | README 自己写着 *“Currently unavailable due to recent changes in terabox”*，且代码依赖登录 Cookie |
| [r0ld3x/terabox-app](https://github.com/r0ld3x/terabox-app) | 104 | 2024-02 停更 | 旧 API |
| [r0ld3x/terabox-downloader-bot](https://github.com/r0ld3x/terabox-downloader-bot) | 124 | 2024-08 停更 | 旧 API |

### 🔍 值得读的“踩坑记录”（比代码更有价值）

- [abhi-dhakar/download24 PR #6](https://github.com/abhi-dhakar/download24/pull/6)：明确记录了
  `400210 / 460020` 是“IP 被挑战”，以及 **`ndus` Cookie 才能让 TeraBox 给受限分享签名 `dlink`**。
- [bytepassperks/terabox-resolver-saas PR #5](https://github.com/bytepassperks/terabox-resolver-saas/pull/5)：记录了
  `/share/list` 假 105、`/share/download` 400310 的现状，并给出 `shorturlinfo + /share/streaming` 的绕过方案（**只对视频有效**，HLS 切片）。
- [bytepassperks/terabox-resolver-saas PR #1](https://github.com/bytepassperks/terabox-resolver-saas/pull/1)：商业解析服务用“账号池轮换”，侧面印证单靠匿名接口已经走不通。

---

## 4. 三条可行路线对比

| 方案 | 成本 | 稳定性 | 隐私 | 适合 |
| --- | --- | --- | --- | --- |
| **A. 登录 Cookie + 本仓库脚本** | 注册一个免费账号（10 GB 空间够用） | 高，官方接口 | 高，Cookie 只留在本地 | 想长期、批量下载 |
| **B. Telegram Bot** | 0 | 中，可能限速/限制大小 | 低，文件经过第三方 | 偶尔下一个文件 |
| **C. 桌面 GUI（trauso）** | 装软件 | 中，依赖它内置的下载服务器 | 中 | 不想碰命令行 |

**建议 A。** 免费账号下载 297 MB 完全没问题；脚本支持断点续传，断了重跑即可。

---

## 5. 本仓库脚本用法

脚本：[`terabox_dl.py`](./terabox_dl.py)，**零第三方依赖**（纯标准库）。

### 5.1 只看文件信息（不需要登录）

```bash
python3 terabox_dl.py "https://dm.terabox.com/chinese/sharing/link?surl=0Y8ZvbwJrqOO4n35IAOVLQ" --info
```

### 5.2 拿到登录 Cookie

1. Chrome 打开 <https://www.terabox.com>，用 Google / 邮箱注册并登录；
2. `F12` → **Network** → 刷新页面 → 点任意一个 `terabox.com` 请求；
3. 在 **Request Headers** 里找到 `Cookie:`，**整条复制**（至少要有 `ndus=`，最好连 `ndut_fmt`、`browserid`、`csrfToken` 一起）。

### 5.3 解析直链 / 下载

```bash
# 只打印直链
python3 terabox_dl.py "<分享链接>" \
  --cookie "ndus=xxxx; ndut_fmt=xxxx; browserid=xxxx; csrfToken=xxxx" --print-url

# 下载到 ./downloads，支持断点续传
python3 terabox_dl.py "<分享链接>" \
  --cookie "ndus=xxxx; ..." -o ./downloads
```

也可以把 Cookie 放进环境变量，避免出现在命令历史里：

```bash
export TERABOX_COOKIE="ndus=xxxx; ..."
python3 terabox_dl.py "<分享链接>" -o ./downloads
```

> 直链是短时效的，脚本会“解析完立刻下载”；如果 `--print-url` 拿到的链接过一会儿 403，重新跑一次即可。

---

## 6. 注意事项

- **Cookie 等于账号**，不要贴到第三方“在线解析”网站，也不要用别人的账号池；
- 本项目只做协议复现，不绕过登录/付费；请只下载你有权访问的内容，并遵守 TeraBox 服务条款；
- TeraBox 的接口大约每季度会变一次（`jsToken` 正则、参数名、域名都可能改）。脚本把关键点集中在
  `get_share_page()` / `shorturlinfo()` / `resolve_dlink()` 三个函数里，坏了改这三处即可；
- 如果哪天 `shorturlinfo` 也开始返回 `400210`，先换住宅 IP / 关代理，再检查 Cookie 是否过期。
