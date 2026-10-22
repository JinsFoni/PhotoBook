"""采集网络客户端 — curl_cffi 模拟 Chrome TLS 指纹。

已验证链路(见 /tmp/bd 原型):
- buondua 列表页/详情页:纯 curl_cffi 即可
- ouo.io → ouo.press 三步跳转:x-token(Turnstile)服务端不校验,留空
- MediaFire 页面直链正则 + 公开 API get_info.php(哈希字段 file_info.hash)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from curl_cffi import requests as cr

log = logging.getLogger("harvest")

UA_IMPERSONATE = "chrome"

# ouo 短链落地到的非 MediaFire 网盘 → 展示名。命中则重试无意义,
# 直接抛 UnsupportedHostError 让任务带上明确报错。
OTHER_HOSTS = {
    "terabox": "TeraBox",        # terabox.app/.com/app/link/share/club/freeterabox
    "1024tera": "TeraBox",       # 1024tera.com
    "terasharelink": "TeraBox",  # terasharelink.com
    "4funbox": "TeraBox",
    "mirrobox": "TeraBox",
    "nephobox": "TeraBox",
    "pixeldrain": "Pixeldrain",
    "mega.nz": "MEGA",
    "gofile": "GoFile",
    "krakenfiles": "KrakenFiles",
    "workupload": "Workupload",
    "hitfile": "HitFile",
    "turbobit": "Turbobit",
}


class UnsupportedHostError(RuntimeError):
    """短链落地到不支持下载的网盘平台(包不在 MediaFire)。"""

    def __init__(self, host: str):
        self.host = host
        super().__init__(f"不支持{host}网盘下载")

# ouo.io/ouo.press 专用指纹。ouo 套了 Cloudflare 人机盾(Cf-Mitigated: challenge),
# 按「出口 IP + TLS 指纹」联合概率拦截:机房代理出口 + chrome 指纹实测 100% 403,
# safari17_0 实测 6/6 过盾且完整两段式跳转 3/3 落地 MediaFire。chrome 留作重试
# 兕底(住宅出口/换代理场景 chrome 是通的)。
OUO_IMPERSONATE = "chrome"  # 2026-09-30 实测: safari17_0 被 ouo CF 盾全拦(0/3), chrome 全过(3/3)


def _proxy() -> str | None:
    """采集代理(settings 表 harvest.proxy,空=直连)。

    作用于整条采集链路(页面解析、短链跳转、MediaFire API、归档下载);
    每次请求时读,后台改完即时生效,无需重启。前台与 admin 不受影响。
    """
    from app.database import SessionLocal
    from app.services import settings_store
    s = SessionLocal()
    try:
        val = str(settings_store.harvest_conf(s).get("harvest.proxy") or "").strip()
        return val or None
    finally:
        s.close()


@dataclass
class HarvestTarget:
    """从详情页解析出的采集目标。"""

    serial: int
    title: str = ""
    model_name: str = ""
    password: str = ""
    shortlinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # 详情页自己的 tag(显示名,保序)
    published: str = ""  # 源站发布日期(YYYY.MM.DD);空 = 页面未提供,导入时回退当天


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """GET 页面,返回 HTML 文本。失败抛 RuntimeError。"""
    r = cr.get(url, impersonate=UA_IMPERSONATE, timeout=timeout, proxy=_proxy())
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    return r.text


# ---- buondua 列表页 ---------------------------------------------------------

LIST_LINK_RE = re.compile(r'href="(/[^"]*?-(\d{3,}))"')
PAGINATION_START_RE = re.compile(r'[?&]start=(\d+)')


def scan_list_page(base_url: str) -> tuple[list[tuple[int, str]], bool]:
    """解析列表页,返回 ([(序号, 详情路径)...], 有无下一页)。

    排除 /tag/ 链接(形似详情页但不是)。
    """
    html = fetch_html(base_url)
    found: dict[int, str] = {}
    for path, serial in LIST_LINK_RE.findall(html):
        if path.startswith("/tag/") or path.startswith("/search"):
            continue
        found.setdefault(int(serial), path)
    links = sorted(found.items())
    # 分页:?start=N
    starts = [int(x) for x in PAGINATION_START_RE.findall(html)]
    has_next = bool(starts)
    return links, has_next


# ---- buondua 详情页 ---------------------------------------------------------

OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')
PASSWORD_RE = re.compile(r"Password:\s*([^<\n]+)")
PAGE_TOTAL_RE = re.compile(r"\( Page \d+ / (\d+) \)")
FULLTEXT_RE = re.compile(
    r'<div[^>]*class="article-fulltext"[^>]*>(.*?)'
    r'(<div[^>]*class="(?:article-tags|bottom-articles))', re.S)
IMG_RE = re.compile(r"https://i\d*\.buondua\.com/[^\"'\s\\]+?\.(?:jpe?g|png|webp)(?:\?[^\"'\s\\]*)?")
SHORTLINK_RE = re.compile(
    r'<a[^>]+href="(https?://(?:ouo\.io|ouo\.press)/[^"]+)"[^>]*>(.*?)</a>', re.S)
# 锚文本里的网盘名: "👉 Download link: MediaFire" / "Terabox"。
# 页面常见双备份(同一包 MediaFire + TeraBox 各一条链), 只取 MediaFire;
# 极少部分 Terabox 链的锚文本也标着 MediaFire, 由 resolve_ouo 落地后兜底识别。
ANCHOR_LABEL_RE = re.compile(r'Download link:\s*([A-Za-z]+)')

# 老帖不挂 ouo 短链,直接放 MediaFire 文件/文件夹页
# (如 http://www.mediafire.com/file/xxx/Name.rar/file)。与 SHORTLINK_RE 同域
# 白名单思路:只要 MF 文件/文件夹页形态就收,worker 侧按域跳过 ouo 解析。
MEDIAFIRE_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?mediafire\.com/(?:file|folder)/[^"]+)')

# 文章自己的 tag 容器:
#   <div class="article-tags"><div class="tags"><a href="/tag/x-123"><span>X</span></a>…
# 注意:页面上还有大量「相关推荐」卡片的 .item-tags,那是别的写真集的 tag,
# 绝不能用(旧实现取「页面第一个 /tag/ 链接」→ 模特名取成了出品方/分类)。
ARTICLE_TAGS_RE = re.compile(
    r'<div[^>]*class="[^"]*article-tags[^"]*"[^>]*>\s*'
    r'<div[^>]*class="[^"]*\btags\b[^"]*"[^>]*>(.*?)</div>', re.S)
TAG_LINK_RE = re.compile(r'href="/tag/([^"]+)"[^>]*>\s*<span[^>]*>([^<]*)</span>', re.S)


def _article_tags(html: str) -> list[str]:
    """只取 article-tags 容器内的 tag 显示名(去重保序)。"""
    m = ARTICLE_TAGS_RE.search(html)
    if not m:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for slug, name in TAG_LINK_RE.findall(m.group(1)):
        label = name.strip()
        if label and slug not in seen:
            seen.add(slug)
            names.append(label)
    return names


def _serial_from_url(url: str) -> int:
    m = re.search(r"-(\d+)(?:[/?#]|$)", url)
    if not m:
        raise ValueError(f"URL 末尾无序号: {url}")
    return int(m.group(1))


# WordPress(misskon/nicesss/4kup)在 ld+json 里给 datePublished;JSON 字符串里
# 斜杠可能被转义(\/),先归一再取。发布时间带时区,取日期段不做时区换算 ——
# 与源站页面上展示的日期一致即可。
DATE_PUBLISHED_RE = re.compile(r'"datePublished":"(\d{4}-\d{2}-\d{2})')
# WordPress(GP 主题,4kup)ld+json 缺失时 <time datetime> 兜底
TIME_DATETIME_RE = re.compile(
    r'<time[^>]*\bdatetime="(\d{4}-\d{2}-\d{2})', re.I)


def _date_published_iso(html: str) -> str:
    m = (DATE_PUBLISHED_RE.search(html.replace("\\/", "/"))
         or TIME_DATETIME_RE.search(html.replace("\\/", "/")))
    return m.group(1) if m else ""


def _to_dotted(iso: str) -> str:
    """YYYY-MM-DD → YYYY.MM.DD(与 published_at 存储格式一致)。"""
    return iso.replace("-", ".")


def _collect_mediafire_links(html: str) -> list[str]:
    """详情页直挂的 MediaFire 文件/文件夹链接(去重保序)。

    老帖不挂 ouo 短链而是直接放 MF 链接;链接进 shortlinks 与 ouo 短链混排,
    worker 按域分流(ouo → resolve_ouo,mediafire → 直接取直链)。
    """
    out: list[str] = []
    seen: set[str] = set()
    for link in MEDIAFIRE_LINK_RE.findall(html):
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def serial_from_url(url: str) -> int:
    """按站点分派的序号提取:buondua 尾段数字 / misskon slug 前缀或 postid /
    nicesss <id>.html / 4kup post id(slug 多无数字,回退页面 post-N)。"""
    if is_4kup_url(url):
        try:
            return _serial_from_4kup_url(url)
        except ValueError:
            return _4kup_serial_from_page(fetch_html(url))
    if is_nicesss_url(url):
        return _serial_from_nicesss_url(url)
    if is_misskon_url(url):
        try:
            return _serial_from_misskon_url(url)
        except ValueError:
            return _misskon_serial_from_page(url)   # 老帖 slug 无序号
    return _serial_from_url(url)


def parse_detail_page(url: str, existing_html: str | None = None,
                      model_exclude: str | None = None) -> HarvestTarget:
    """按站点分派的详情页解析(nicesss 不需要 model_exclude)。"""
    if is_4kup_url(url):
        return parse_4kup_detail_page(url, existing_html=existing_html,
                                      model_exclude=model_exclude)
    if is_nicesss_url(url):
        return parse_nicesss_detail_page(url, existing_html=existing_html)
    if is_misskon_url(url):
        return parse_misskon_detail_page(url, existing_html=existing_html,
                                         model_exclude=model_exclude)
    return _parse_buondua_detail_page(url, existing_html=existing_html,
                                      model_exclude=model_exclude)


def _parse_buondua_detail_page(url: str, existing_html: str | None = None,                               model_exclude: str | None = None) -> HarvestTarget:
    """解析详情页:标题/标签/模特名/密码/短链。

    模特名 = article-tags 里第一个未被 model_exclude(模特名排除词)命中的 tag,
    因为出品方/分类 tag 总排在前面(如 [Cosplay, 麻花麻花酱] → 麻花麻花酱)。
    """
    from .filters import pick_model_name

    html = existing_html if existing_html is not None else fetch_html(url)
    serial = _serial_from_url(url)

    m = OG_TITLE_RE.search(html)
    title = m.group(1).strip() if m else ""
    # og:title 可能带 "( Page x / y )" 后缀
    title = re.sub(r"\s*\(\s*Page \d+ / \d+\s*\)\s*$", "", title)

    tags = _article_tags(html)
    model_name = pick_model_name(tags, model_exclude)

    pm = PASSWORD_RE.search(html)
    password = pm.group(1).strip() if pm else ""
    # 详情页常写 "misskon.com or mrcong.com";实际加密用哪个取决于发布站点,
    # 多候选原样保留,由 extract_archive 逐个尝试;单一密码则保持原文。
    if " or " in password and ("misskon.com" in password or "mrcong.com" in password):
        password = "misskon.com or mrcong.com"
    # 短链按锚文本过滤: 详情页可能同时挂 MediaFire 与 TeraBox 等多网盘
    # (同一包的备份链, 不是分卷), 只保留锚文本标注 MediaFire 的。
    # 极少数 Terabox 链错标 MediaFire → resolve_ouo 落地后仍会兜底识别报错。
    shortlinks = []
    seen: set[str] = set()
    for link, anchor in SHORTLINK_RE.findall(html):
        label = ANCHOR_LABEL_RE.search(re.sub(r"<[^>]+>", "", anchor))
        if label and label.group(1).lower() != "mediafire":
            continue
        if link not in seen:
            seen.add(link)
            shortlinks.append(link)
    for link in _collect_mediafire_links(html):
        if link not in seen:
            seen.add(link)
            shortlinks.append(link)
    # Joomla article-info: <small>09:10 29-10-2017</small>(发布时间,时间在前)
    dm = re.search(r'<small>\s*(\d{2}:\d{2})\s+(\d{2})-(\d{2})-(\d{4})\s*</small>', html)
    published = (f"{dm.group(4)}.{dm.group(3)}.{dm.group(2)}" if dm else "")
    return HarvestTarget(serial=serial, title=title, model_name=model_name,
                         password=password, shortlinks=shortlinks, tags=tags,
                         published=published)


def download_archive_urls(target: HarvestTarget) -> list[dict]:
    """解析所有短链 → 返回 [{url(直链), quick_key, size, sha256}]。"""
    results = []
    for link in target.shortlinks:
        direct = resolve_ouo(link)
        if not direct:
            continue
        info = mediafire_info_from_url(direct)
        info["page_url"] = direct
        results.append(info)
    return results


# ---- nicesss 详情页 ----------------------------------------------------------
# 与 buondua 不同:页面没有本页专属 tag 容器(侧边栏标签云是全站热门,与文章
# 无关),模特名只能从标题提取。标题格式非常规整(2026-10 全站采样):
#   [Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社
#   [XINGYAN星颜社]2026.01.21 VOL.456 时安安[82+1P／910MB] - 呦糖社
# 出品方放 tags[0],模特名 = 方括号日期编号后、体积方括号前的那段。

NICESSS_HOST = "nicesss.com"

NICESSS_TITLE_RE = re.compile(
    r'^\[([^]]+)\]\s*(?:\d{4}\.\d{2}\.\d{2}\s*)?'
    r'(?:NO\.|VOL\.|Vol\.)?\s*\d*\s*(.+?)\[')
# 密码优先取正文 <font> 标签里的(meta description 也含这段文字,裸匹配会串进来)。
# 老帖(2022 采样 37628)没有 <font> 包裹,是纯文本 "[解压密码]：xxx<br />",
# 简体且无 -Password 后缀 → 第二条裸文本正则兜底。冒号全角/半角都收。
NICESSS_PASSWORD_RE = re.compile(
    r'<font[^>]*>\[?解壓密碼-Password\]?\s*[：:]\s*([^<]+)')
NICESSS_PASSWORD_PLAIN_RE = re.compile(
    r'\[解压密码\]\s*[：:]\s*([^\s<]+)')
# 下载按钮: <a href="https://ouo.io/xxx" ...><span>Download</span>…,正文挂两遍,去重
NICESSS_SHORTLINK_RE = re.compile(r'href="(https?://ouo\.(?:io|press)/[^"]+)"')


def is_nicesss_url(url: str) -> bool:
    host = urlparse(url).netloc.lower() if url else ""
    return host == NICESSS_HOST or host.endswith("." + NICESSS_HOST)


def _serial_from_nicesss_url(url: str) -> int:
    """…/archives/xr/xiurw/464006.html → 464006。"""
    m = re.search(r"/(\d+)\.html?(?:[?#]|$)", url)
    if not m:
        raise ValueError(f"URL 末尾无序号: {url}")
    return int(m.group(1))


def parse_nicesss_detail_page(url: str, existing_html: str | None = None) -> HarvestTarget:
    """解析 nicesss 详情页:标题 → 出品方 + 模特名,模特名同时作为唯一 tag。

    (用户需求:解析到的模特名作为 tag,直接进黑白名单过滤与 import_album
    的标签关联。)
    """
    html = existing_html if existing_html is not None else fetch_html(url)
    serial = _serial_from_nicesss_url(url)

    # og:title 带 "- 呦糖社" 后缀(另一个无后缀的 og:title 在 JSON-LD 里)
    m = OG_TITLE_RE.search(html)
    title = m.group(1).strip() if m else ""
    title = re.sub(r"\s*-\s*呦糖社\s*$", "", title)

    publisher = ""
    model_name = ""
    tm = NICESSS_TITLE_RE.match(title)
    if tm:
        publisher, model_name = tm.group(1).strip(), tm.group(2).strip()

    pm = NICESSS_PASSWORD_RE.search(html) or NICESSS_PASSWORD_PLAIN_RE.search(html)
    password = pm.group(1).strip() if pm else ""

    shortlinks: list[str] = []
    seen: set[str] = set()
    for link in NICESSS_SHORTLINK_RE.findall(html):
        if link not in seen:
            seen.add(link)
            shortlinks.append(link)

    # nicesss 只挂 MediaFire 备份(页面明确标注「下載網盤:MediaFire」),
    # 锚文本没有网盘名,无法像 buondua 那样按锚文本过滤。
    tags = [model_name] if model_name else []
    if publisher:
        tags = [publisher, *tags]
    return HarvestTarget(serial=serial, title=title, model_name=model_name,
                         password=password, shortlinks=shortlinks, tags=tags,
                         published=_to_dotted(_date_published_iso(html)))


# ---- misskon 列表页 ----------------------------------------------------------
# WordPress 形态: 绝对 URL /<serial>-<slug>/,分页 /page/2/(buondua 是相对路径
# + ?start=N)。LIST_LINK_RE(相对路径正则)不适用,单独一条。

MISSKON_LIST_LINK_RE = re.compile(
    r'href="(https://misskon\.com/(\d{3,})-[^"/]*/?)"')
# 正文卡片容器(侧栏 widget 的「热门文章」也是同形态链接,必须只在 article 里找)
MISSKON_CARD_RE = re.compile(
    r'<article class="item-list">(.*?)</article>', re.S)


def scan_misskon_list_page(base_url: str) -> tuple[list[tuple[int, str]], bool]:
    """解析 misskon 列表页,返回 ([(序号, 详情绝对 URL)...], 有无下一页)。"""
    html = fetch_html(base_url)
    found: dict[int, str] = {}
    for card in MISSKON_CARD_RE.findall(html):
        for url, serial in MISSKON_LIST_LINK_RE.findall(card):
            found.setdefault(int(serial), url)
    links = sorted(found.items())
    has_next = bool(re.search(r'href="https://misskon\.com/page/\d+/"', html))
    return links, has_next


MISSKON_HOST = "misskon.com"

# WordPress(Tie 主题)结构,与 buondua(Joomla)不同但语义一致:
# - 列表链接绝对 URL: https://misskon.com/119420-bluecake-lee-ahrin-red-night-255-photos/
# - 详情页无 og:title,标题在 <h1 class="name post-title entry-title">
# - tag 容器: <p class="post-tag">Tags<a rel="tag">BLUECAKE</a>…(模特名/出品方顺序不定)
# - 密码两种写法: 新帖 "Password unrar:</strong> <span>misskon.com</span>",
#   老帖 "Unzip password:</strong> <input value="mrcong.com">(转载源自 mrcong)
MISSKON_H1_RE = re.compile(
    r'<h1[^>]*class="[^"]*(?:post-title|entry-title)[^"]*"[^>]*>(.*?)</h1>', re.S)
MISSKON_TAG_ROW_RE = re.compile(r'<p class="post-tag">Tags(.*?)</p>', re.S)
MISSKON_TAG_LINK_RE = re.compile(r'href="https://misskon\.com/tag/[^"]*"[^>]*>([^<]+)<')
MISSKON_PASSWORD_RE = re.compile(
    r'(?:Password unrar|Unzip password):?</strong>\s*'
    r'(?:<span[^>]*>([^<]+)</span>|<input[^>]*value="([^"]+)")')
# 老帖 slug 无 <序号>- 前缀(如 /xiuren-no-962-model-…/),序号取 body class
# 的 WordPress post id;已验证与新式 URL 序号同源(postid-119420 ↔ /119420-…/)
MISSKON_POSTID_RE = re.compile(r'\bpostid-(\d+)')


def is_misskon_url(url: str) -> bool:
    host = urlparse(url).netloc.lower() if url else ""
    return host == MISSKON_HOST or host.endswith("." + MISSKON_HOST)


def _serial_from_misskon_url(url: str) -> int:
    """…/119420-bluecake-lee-ahrin-red-night-255-photos/ → 119420。

    分卷文章尾段是 /2/ /3/(无序号),前一段 slug 里的序号才是本体。
    老帖 slug 无序号前缀 → 抛 ValueError,由 serial_from_url 抓页面补取。
    """
    clean = url.split("?")[0].split("#")[0].rstrip("/")
    clean = re.sub(r"/\d+$", "", clean)          # 掉尾段纯数字分页段
    m = re.search(r"/(\d{3,})(?:-|$)", clean)
    if not m:
        raise ValueError(f"URL 无序号: {url}")
    return int(m.group(1))


_misskon_serial_cache: dict[str, int] = {}
_misskon_serial_cache_max = 2000


def _misskon_serial_from_page(url: str) -> int:
    """老式 URL(slug 无序号)从详情页 body class 的 postid-N 取序号。

    结果按 URL 缓存: 油猴脚本每 5s 轮询一次状态, 同一页 URL 反复解析
    意味着每轮都真实回源拉一次 misskon 详情页(单次 1s+, 且占采集代理),
    缓存后整页只有第一次慢。
    """
    cached = _misskon_serial_cache.get(url)
    if cached is not None:
        return cached
    html = fetch_html(url)
    m = MISSKON_POSTID_RE.search(html)
    if not m:
        raise ValueError(f"URL 无序号且页面无 postid: {url}")
    serial = int(m.group(1))
    if len(_misskon_serial_cache) >= _misskon_serial_cache_max:
        _misskon_serial_cache.clear()
    _misskon_serial_cache[url] = serial
    return serial


def _misskon_title(html: str) -> str:
    m = MISSKON_H1_RE.search(html)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def parse_misskon_detail_page(url: str, existing_html: str | None = None,
                              model_exclude: str | None = None) -> HarvestTarget:
    """解析 misskon 详情页:结构语义与 buondua 一致(标题/tag/密码/ouo 短链),
    选择器不同;模特名同样从 tag 里按排除词挑。"""
    from .filters import pick_model_name

    html = existing_html if existing_html is not None else fetch_html(url)
    try:
        serial = _serial_from_misskon_url(url)
    except ValueError:
        idm = MISSKON_POSTID_RE.search(html)
        if not idm:
            raise ValueError(f"URL 无序号且页面无 postid: {url}")
        serial = int(idm.group(1))

    title = _misskon_title(html)

    tags: list[str] = []
    seen: set[str] = set()
    tm = MISSKON_TAG_ROW_RE.search(html)
    if tm:
        for name in MISSKON_TAG_LINK_RE.findall(tm.group(1)):
            label = name.strip()
            if label and label.lower() not in seen:
                seen.add(label.lower())
                tags.append(label)
    model_name = pick_model_name(tags, model_exclude)

    pm = MISSKON_PASSWORD_RE.search(html)
    password = (pm.group(1) or pm.group(2)).strip() if pm else ""

    # ouo 短链 + 锚文本 MediaFire 过滤:与 buondua 同构(直挂的 terabox 链
    # 不是 ouo 域,SHORTLINK_RE 天然滤掉),去重保序。老帖直挂 MediaFire
    # 链接(无 ouo 短链)也一并收。
    shortlinks: list[str] = []
    seen_links: set[str] = set()
    for link, anchor in SHORTLINK_RE.findall(html):
        label = ANCHOR_LABEL_RE.search(re.sub(r"<[^>]+>", "", anchor))
        if label and label.group(1).lower() != "mediafire":
            continue
        if link not in seen_links:
            seen_links.add(link)
            shortlinks.append(link)
    for link in _collect_mediafire_links(html):
        if link not in seen_links:
            seen_links.add(link)
            shortlinks.append(link)
    return HarvestTarget(serial=serial, title=title, model_name=model_name,
                         password=password, shortlinks=shortlinks, tags=tags,
                         published=_to_dotted(_date_published_iso(html)))


# ---- 4kup.net 详情页 ----------------------------------------------------------
# WordPress(GP 主题)。该站只有 TeraBox 链接(download-box),没有 MediaFire/
# ouo;tag 只有分类(地区/出品方),模特名只能从标题按规则抽取(见
# titlemodel.py,规则移植自 docs/model-name 原型,实测 95%+ 命中)。

FOURKUP_HOST = "4kup.net"

# 正文下载区: <p id='download'><a href='https://1024terabox.com/s/xxx'>
# (单引号/双引号都有);整页兜底正则只认 terabox 系域名,不会误收广告链。
FOURKUP_DOWNLOAD_BOX_RE = re.compile(
    r"<p[^>]*id=['\"]download['\"][^>]*>(.*?)</p>", re.S)
TERABOX_LINK_RE = re.compile(
    r'href=["\'](https?://[^"\']*?(?:terabox|1024tera|terasharelink|'
    r"freeterabox|mirrobox|nephobox|4funbox)[^\"']*)['\"]", re.I)
FOURKUP_POSTID_RE = re.compile(r'<article[^>]*\bpost-(\d+)\b')
# 标题 <h1 class="entry-title">…</h1>(og:title 与其一致,带站点后缀)
FOURKUP_H1_RE = re.compile(
    r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', re.S)


# 列表页卡片: <article id="post-53150" class="post-53150 …">…</article>。
# 捕获组含完整开标签(post id 在开标签的 class/id 里),h2 内标题链接;
# 侧栏「热门文章」等 widget 也是同形态链接,必须只在 article 卡片里找,
# 与 misskon MISSKON_CARD_RE 同思路。
FOURKUP_CARD_RE = re.compile(
    r'(<article[^>]*class="[^"]*post-\d+[^"]*"[^>]*>)(.*?)</article>', re.S)
FOURKUP_LIST_LINK_RE = re.compile(
    r'<h\d[^>]*>\s*<a href="(https://4kup\.net/[^"]+)"', re.S)


def scan_4kup_list_page(base_url: str) -> tuple[list[tuple[int, str]], bool]:
    """解析 4kup.net 列表页,返回 ([(post_id, 详情绝对 URL)...], 有无下一页)。

    序号 = WordPress post id(article 开标签 class 里的 post-N,卡片自带,
    无需回源详情页)。分页 /page/N/。
    """
    html = fetch_html(base_url)
    found: dict[int, str] = {}
    for open_tag, card in FOURKUP_CARD_RE.findall(html):
        for url in FOURKUP_LIST_LINK_RE.findall(card):
            m = re.search(r"/post-(\d+)/", url) or FOURKUP_POSTID_RE.search(open_tag)
            if not m:
                continue
            found.setdefault(int(m.group(1)), url)
    links = sorted(found.items())
    has_next = bool(re.search(r'href="https://4kup\.net/page/\d+/"', html))
    return links, has_next


def is_4kup_url(url: str) -> bool:
    host = urlparse(url).netloc.lower() if url else ""
    return host == FOURKUP_HOST or host.endswith("." + FOURKUP_HOST)


def _serial_from_4kup_url(url: str) -> int:
    """…/post-53150 类页面的序号: WordPress post id。

    slug 大多无数字尾段(/le-gms-006a-gms/),与 misskon 老帖同思路
    回退到详情页 article 的 post-N 取;有数字尾段的 slug(coser-2630)
    与 post id 同源吗?——不同源(它只是去重 slug),所以一律回退页面。
    这里仅识别 /post-<id>/ 形态,其余抛 ValueError 由调用方抓页面。
    """
    m = re.search(r"/post-(\d+)(?:[/?#]|$)", url)
    if m:
        return int(m.group(1))
    raise ValueError(f"URL 无序号(4kup 需详情页 post id): {url}")


def _4kup_serial_from_page(html: str) -> int:
    m = FOURKUP_POSTID_RE.search(html)
    if not m:
        raise ValueError("页面无 post id(4kup)")
    return int(m.group(1))


def _collect_terabox_links(html: str) -> list[str]:
    """页面里全部 terabox 系链接(去重保序)。

    优先 download-box(正文下载按钮),整页扫描兜底 —— 部分帖子下载区
    结构略异,但 terabox 域名特征稳定,广告 iframe 不含这些域。
    """
    out: list[str] = []
    seen: set[str] = set()
    boxes = FOURKUP_DOWNLOAD_BOX_RE.findall(html)
    for scope in boxes + [html]:
        for link in TERABOX_LINK_RE.findall(scope):
            link = link.replace("&amp;", "&")
            if link not in seen:
                seen.add(link)
                out.append(link)
        if out:
            break  # download-box 命中就不再整页扫
    return out


def parse_4kup_detail_page(url: str, existing_html: str | None = None,
                           model_exclude: str | None = None) -> HarvestTarget:
    """解析 4kup.net 详情页。

    与其他站点最大的不同:模特名不来自 tag(该站 tag 只有分类),而是
    从标题规则抽取(titlemodel);抽取不到 → 空串归「未分类」。tags 返回
    标题抽取出的模特名(供黑白名单 tag 过滤与 import_album 关联),
    另加页面分类名。密码固定 4kup(站点公开约定)。
    """
    from .titlemodel import model_name_from_title

    html = existing_html if existing_html is not None else fetch_html(url)
    import html as _html
    html = _html.unescape(html)   # og:title/正文带 &#8211; 等实体,先统一解码
    try:
        serial = _serial_from_4kup_url(url)
    except ValueError:
        serial = _4kup_serial_from_page(html)
    m = OG_TITLE_RE.search(html)
    title = m.group(1).strip() if m else ""
    # og:title 带 " – Beautiful Girls Collection" 站点后缀(h1 无)
    title = re.sub(r"\s*[–-]\s*Beautiful Girls Collection\s*$", "", title)
    title = re.sub(r"\s*\(\s*Page \d+ / \d+\s*\)\s*$", "", title)
    if not title:
        hm = FOURKUP_H1_RE.search(html)
        if hm:
            title = re.sub(r"<[^>]+>", "", hm.group(1)).strip()

    name, _native = model_name_from_title(title)

    # 分类名只取正文 <article> 内的 category 链接文本(页面导航/侧栏菜单
    # 也是 /category/ 链接,整页正则会把全站分类误收进来)
    tags: list[str] = []
    seen: set[str] = set()
    if name:
        tags.append(name)
        seen.add(name.lower())
    art = re.search(r"<article\b.*?</article>", html, re.S)
    if art:
        for label in re.findall(
                r'href="https://4kup\.net/category/[^"]*"[^>]*>([^<]+)<',
                art.group(0)):
            label = label.strip()
            if label and label.lower() not in seen:
                seen.add(label.lower())
                tags.append(label)

    # 该站下载区只挂 terabox,无 password 字样;归档密码是站点公开约定 4kup
    shortlinks = _collect_terabox_links(html)
    return HarvestTarget(serial=serial, title=title, model_name=name,
                         password="4kup", shortlinks=shortlinks, tags=tags,
                         published=_to_dotted(_date_published_iso(html)))


# ---- ouo.io 跳转链(已验证;2026-09 起为两段式) -------------------------------

def _ouo_step(s, link: str, *, wait: float = 3.0) -> str | None:
    """走一轮 ouo 短码页 → 返回落地 URL(可能是 MediaFire,也可能是下一段 ouo.io 短码)。

    流程:GET 短码页取 _token/v-token → POST ouo.press/go/<code>
    → 解析 form-go 的 action/_token → POST action → 302 落地。
    """
    code = link.rstrip("/").split("/")[-1]
    r1 = s.get(link, timeout=30)
    if r1.status_code != 200:
        return None
    tok = re.search(r'name="_token"\s+type="hidden"\s+value="([^"]+)"', r1.text)
    vtok = re.search(r'id="v-token"\s+name="v-token"\s+type="hidden"\s+value="([^"]+)"', r1.text)
    if not tok:
        return None
    time.sleep(wait)

    r2 = s.post("https://ouo.press/go/" + code,
                data={"_token": tok.group(1), "x-token": "",
                      "v-token": vtok.group(1) if vtok else "bx"},
                timeout=30)
    if r2.status_code != 200 or "form-go" not in r2.text:
        return None
    m_action = re.search(r'action="([^"]*)"[^>]*id="form-go"', r2.text)
    m_tok2 = re.search(r'id="form-go">.*?name="_token"\s+type="hidden"\s+value="([^"]+)"', r2.text, re.S)
    if not m_action or not m_tok2:
        return None
    time.sleep(wait + 1.0)

    r3 = s.post(m_action.group(1), data={"_token": m_tok2.group(1), "x-token": ""},
                timeout=30, allow_redirects=True)
    final = str(r3.url)
    if "mediafire.com/file/" in final:
        return final
    if "mediafire.com/folder/" in final:
        return final  # 分卷包发布方把所有卷放一个文件夹, 由调用方 API 展开
    # 落地到其他网盘(terabox 等): 短链活着, 只是托管不在 MediaFire。
    # 分类由 resolve_ouo 统一处理(抛 UnsupportedHostError / 记日志)。
    if "ouo.io/" not in final and "ouo.press/" not in final:
        log.warning("ouo %s landed on non-mediafire host: %s", code, final[:120])
    # 落地 URL 可能缺尾部路径(如 .../file/<key>),完整链接在响应体里
    m = re.search(r'(https?://www\.mediafire\.com/file/[^"\'\s]+)', r3.text)
    return m.group(1) if m else final


def resolve_ouo(link: str, *, wait: float = 3.0, max_hops: int = 3) -> str | None:
    """ouo.io/<id> → MediaFire 文件页 URL。失败返回 None。

    2026-09 起 ouo 常见两段式:第三步落地 ouo.io/<新短码>(还是短链页),
    需把同样流程再走一遍(最多 max_hops 轮)才到达 MediaFire。

    CF 盾是概率拦截:单会话被盾/流程断掉 → 换新会话重试(safari17_0 优先,
    末轮 chrome 兕底, 兼容住宅出口场景)。落地到其他网盘(terabox 等)
    抛 UnsupportedHostError(重试无意义);完全未知的域返回 None。
    """
    proxy = _proxy()
    for attempt in range(3):
        imp = OUO_IMPERSONATE if attempt < 2 else "safari17_0"  # 末轮换 safari 兑底(出口指纹多样性)
        s = cr.Session(impersonate=imp, proxy=proxy)
        try:
            url = link
            for _ in range(max_hops):
                final = _ouo_step(s, url, wait=wait)
                if not final:
                    break  # 被盾/页面异常 → 换新会话重试
                if "mediafire.com/file/" in final and "mediafire.com/download" not in final:
                    return final
                if "mediafire.com/folder/" in final:
                    return final
                if "ouo.io/" not in final and "ouo.press/" not in final:
                    # 落地到外部网盘: 已知平台抛错(带平台名), 完全未知域判短链坏
                    for frag, name in OTHER_HOSTS.items():
                        if frag in final:
                            raise UnsupportedHostError(name)
                    return None
                url = final  # 下一段短码,继续
        except UnsupportedHostError:
            raise  # 已知网盘平台, 原样上抛(带平台名)
        except Exception:
            pass
    return None


# ---- MediaFire ---------------------------------------------------------------

# 直链 host 形如 download1510.mediafire.com;页面给 http 还是 https 不定
# (2025-10 起观察到回落 http),方案必须两者都认
MF_DIRECT_RE = re.compile(r'href="(https?://download[^"]+)"')
# key 后面可能是 "/"(带文件名)、"?"(2026-10 起 MediaFire 把 /file/<key>/ 302 到
# /file/<key>/?action=check,短链落地 URL 因此带查询串)、"#" 或行尾
MF_KEY_RE = re.compile(r"mediafire\.com/file/([a-z0-9]+)(?:[/?#]|$)", re.I)
MF_FOLDER_RE = re.compile(r"mediafire\.com/folder/([a-z0-9]+)", re.I)


# 2026-10-22 起 MediaFire 前置的 Cloudflare 对**无 cookie** 的客户端按频率
# 抽检:实测同一 URL 冷请求 8 次有 3 次回 403 + `cf-mitigated: challenge`
# (裸 /file/<key>/ 约 1/6)。采集链路每次都是新的 cr.get,拿不到 __cf_bm,
# 撞上一次就整任务失败(任务 596 两次重排都死在这一步,bytes 0)。
# 规避方式实测有效:同一 Session 先打裸页 /file/<key>/(无查询串)拿到
# __cf_bm/ukey,再打目标页 —— 4/4 通过。仍被拦则换新 Session 退避重试。
CF_RETRY_TRIES = 3
CF_RETRY_BACKOFF = (2.0, 5.0)
CF_CHALLENGE_MARKERS = ("Just a moment", "cf-challenge", "__cf_chl_", "cf_chl_opt")


def is_cf_challenge(r) -> bool:
    """响应是否 Cloudflare 人机盾拦截页(200 也可能是盾页,故正文也要查)。"""
    try:
        if str(r.headers.get("cf-mitigated") or "").lower() == "challenge":
            return True
    except Exception:
        return False
    try:
        body = (r.text or "")[:4096]
    except Exception:
        return False
    # 正文只看前 4KB 的盾页特征 —— 盾页有时用 200 返回,所以状态码不作前提
    return any(m in body for m in CF_CHALLENGE_MARKERS)


def _cf_backoff(attempt: int) -> float:
    return CF_RETRY_BACKOFF[min(attempt, len(CF_RETRY_BACKOFF) - 1)]


def _mf_prime_url(url: str) -> str:
    """去掉查询串/文件名的裸文件页 —— 预热 Session 用。"""
    m = MF_KEY_RE.search(url)
    return f"https://www.mediafire.com/file/{m.group(1)}/" if m else ""


def mediafire_page_session(page_url: str, *, timeout: float = 30.0):
    """取文件页并**把这次的 Session 一起返回**:`(html, session)`。

    为什么要把 Session 交出去(2026-10-22 实测,决定性的那一条):
    MediaFire 会把直链 dkey 绑在「取页面的那个客户端」上 —— 页面走代理、
    下载换个无 cookie 的连接直连,4/4 都被塞 download_repair 验证页;
    只要下载复用取页面时的 Session(cookie 一致,出口可以换),4/4 正常;
    页面和下载都直连(同一出口)也 4/4 正常。所以下载必须带上这个 Session。

    每轮:新 Session → 裸页预热(拿 __cf_bm/ukey,失败也继续)→ 目标页;
    被盾则换 Session 退避重试。失败抛 RuntimeError。
    """
    proxy = _proxy()
    prime = _mf_prime_url(page_url)
    last = "未尝试"
    for attempt in range(CF_RETRY_TRIES):
        s = cr.Session(impersonate=UA_IMPERSONATE, proxy=proxy)
        try:
            if prime and prime != page_url:
                try:
                    s.get(prime, timeout=timeout, allow_redirects=True)
                except Exception as exc:  # 预热失败不影响主请求(可能已拿到 cookie)
                    log.debug("mediafire 预热失败(忽略): %s", exc)
            r = s.get(page_url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and not is_cf_challenge(r):
                return r.text, s
            last = f"HTTP {r.status_code}"
            if is_cf_challenge(r):
                last += " (cf challenge)"
            log.warning("mediafire 页面第 %d/%d 次失败: %s %s",
                        attempt + 1, CF_RETRY_TRIES, last, page_url)
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            log.warning("mediafire 页面第 %d/%d 次异常: %s %s",
                        attempt + 1, CF_RETRY_TRIES, last, page_url)
        try:
            s.close()
        except Exception:
            pass
        if attempt < CF_RETRY_TRIES - 1:
            time.sleep(_cf_backoff(attempt))
    raise RuntimeError(f"MediaFire 页面取不到({last}): {page_url}")


def mediafire_page(page_url: str, *, timeout: float = 30.0) -> str:
    """只要 HTML(内部会关掉 Session)。下载路径请用 mediafire_page_session。"""
    html, s = mediafire_page_session(page_url, timeout=timeout)
    try:
        s.close()
    except Exception:
        pass
    return html


def _mf_api_get(url: str, params: dict, *, timeout: float = 30.0):
    """MediaFire 公开 API(JSON)—— 同样会被 CF 抽检,退避重试。返回 Response。"""
    last = "未尝试"
    for attempt in range(CF_RETRY_TRIES):
        try:
            r = cr.get(url, params=params, impersonate=UA_IMPERSONATE,
                       timeout=timeout, proxy=_proxy())
            if r.status_code == 200 and not is_cf_challenge(r):
                return r
            last = f"HTTP {r.status_code}"
            if is_cf_challenge(r):
                last += " (cf challenge)"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        log.warning("mediafire API 第 %d/%d 次失败: %s %s",
                    attempt + 1, CF_RETRY_TRIES, last, url)
        if attempt < CF_RETRY_TRIES - 1:
            time.sleep(_cf_backoff(attempt))
    raise RuntimeError(f"MediaFire API 请求失败({last}): {url}")


def _mf_direct_from_html(html: str) -> str:
    m = MF_DIRECT_RE.search(html)
    return m.group(1).replace("&amp;", "&") if m else ""


def mediafire_direct_url(page_url: str, *, session=None) -> str | None:
    """文件页 → 直链。给了 session 就复用它(下载端要沿用同一个)。"""
    if session is not None:
        r = session.get(page_url, timeout=30, allow_redirects=True)
        html = r.text if r.status_code == 200 and not is_cf_challenge(r) \
            else mediafire_page(page_url)
    else:
        html = mediafire_page(page_url)
    return _mf_direct_from_html(html) or None


def mediafire_folder_files(folder_url: str) -> list[dict]:
    """MediaFire 文件夹页 URL → 夹内全部文件(逐页取全)。

    走公开 API folder/get_content.php, 返回项与 mediafire_info_from_url
    同构: {quick_key, direct_url, size, sha256, filename}。分卷包发布方
    (2025-11 起)常把所有卷放一个文件夹再挂短链, 文件页正则认不出。
    直链用 file/get_info.php 返回的 download link, 无需再抓文件页。
    """
    key_m = MF_FOLDER_RE.search(folder_url)
    if not key_m:
        raise RuntimeError(f"无法从 URL 提取 folder_key: {folder_url}")
    folder_key = key_m.group(1)
    files: list[dict] = []
    chunk = 1
    while True:
        api = _mf_api_get("https://www.mediafire.com/api/folder/get_content.php",
                          params={"folder_key": folder_key,
                                  "content_type": "files",
                                  "response_format": "json", "chunk": chunk})
        fc = api.json()["response"].get("folder_content", {})
        batch = fc.get("files") or []
        for f in batch:
            page = f.get("links", {}).get("normal_download") or ""
            if not page:
                continue
            html, sess = mediafire_page_session(page)
            files.append({
                "quick_key": f["quickkey"],
                # normal_download 是文件页(非直链), 复用文件页直链提取
                "direct_url": _mf_direct_from_html(html),
                "size": int(f.get("size", 0)),
                "sha256": (f.get("hash") or "").lower(),
                "filename": f.get("filename", ""),
                # 下载必须沿用取页面的 Session(dkey 绑客户端),由调用方负责关闭
                "_session": sess,
                "_referer": page,
            })
        total_chunks = int(fc.get("chunks") or 1)
        if chunk >= total_chunks or not batch:
            break
        chunk += 1
    return files


def mediafire_info_from_url(page_url: str, *, keep_session: bool = False) -> dict:
    """文件页 URL → {quick_key, direct_url, size, sha256, filename}。

    keep_session=True 时额外返回 `_session`/`_referer`:下载必须复用这个
    Session(dkey 绑客户端),调用方负责 close。
    """
    key_m = MF_KEY_RE.search(page_url)
    if not key_m:
        raise RuntimeError(f"无法从 URL 提取 quick_key: {page_url}")
    key = key_m.group(1)

    api = _mf_api_get("https://www.mediafire.com/api/1.5/file/get_info.php",
                      params={"quick_key": key, "response_format": "json"})
    fi = api.json()["response"]["file_info"]
    html, sess = mediafire_page_session(page_url)
    info = {
        "quick_key": key,
        "direct_url": _mf_direct_from_html(html),
        "size": int(fi.get("size", 0)),
        "sha256": (fi.get("hash") or "").lower(),
        "filename": fi.get("filename", ""),
    }
    if keep_session:
        info["_session"] = sess
        info["_referer"] = page_url
    else:
        try:
            sess.close()
        except Exception:
            pass
    return info
