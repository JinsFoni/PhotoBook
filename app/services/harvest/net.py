"""采集网络客户端 — curl_cffi 模拟 Chrome TLS 指纹。

已验证链路(见 /tmp/bd 原型):
- buondua 列表页/详情页:纯 curl_cffi 即可
- ouo.io → ouo.press 三步跳转:x-token(Turnstile)服务端不校验,留空
- MediaFire 页面直链正则 + 公开 API get_info.php(哈希字段 file_info.hash)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from curl_cffi import requests as cr

UA_IMPERSONATE = "chrome"


@dataclass
class HarvestTarget:
    """从详情页解析出的采集目标。"""

    serial: int
    title: str = ""
    model_name: str = ""
    password: str = ""
    shortlinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # 详情页自己的 tag(显示名,保序)


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """GET 页面,返回 HTML 文本。失败抛 RuntimeError。"""
    r = cr.get(url, impersonate=UA_IMPERSONATE, timeout=timeout)
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
SHORTLINK_RE = re.compile(r'href="(https?://(?:ouo\.io|ouo\.press)/[^"]+)"')

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


def parse_detail_page(url: str, existing_html: str | None = None,
                      model_exclude: str | None = None) -> HarvestTarget:
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
    shortlinks = list(dict.fromkeys(SHORTLINK_RE.findall(html)))
    return HarvestTarget(serial=serial, title=title, model_name=model_name,
                         password=password, shortlinks=shortlinks, tags=tags)


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
    # 落地 URL 可能缺尾部路径(如 .../file/<key>),完整链接在响应体里
    m = re.search(r'(https?://www\.mediafire\.com/file/[^"\'\s]+)', r3.text)
    return m.group(1) if m else final


def resolve_ouo(link: str, *, wait: float = 3.0, max_hops: int = 3) -> str | None:
    """ouo.io/<id> → MediaFire 文件页 URL。失败返回 None。

    2026-09 起 ouo 常见两段式:第三步落地 ouo.io/<新短码>(还是短链页),
    需把同样流程再走一遍(最多 max_hops 轮)才到达 MediaFire。
    """
    s = cr.Session(impersonate=UA_IMPERSONATE)
    try:
        url = link
        for _ in range(max_hops):
            final = _ouo_step(s, url, wait=wait)
            if not final:
                return None
            if "mediafire.com/file/" in final and "mediafire.com/download" not in final:
                return final
            if "ouo.io/" not in final and "ouo.press/" not in final:
                return None
            url = final  # 下一段短码,继续
        return None
    except Exception:
        return None


# ---- MediaFire ---------------------------------------------------------------

MF_DIRECT_RE = re.compile(r'href="(https://download[^"]+)"')
MF_KEY_RE = re.compile(r"mediafire\.com/file/([a-z0-9]+)(?:/|$)", re.I)


def mediafire_direct_url(page_url: str) -> str | None:
    html = fetch_html(page_url)
    m = MF_DIRECT_RE.search(html)
    return m.group(1).replace("&amp;", "&") if m else None


def mediafire_info_from_url(page_url: str) -> dict:
    """文件页 URL → {quick_key, direct_url, size, sha256, filename}。"""
    key_m = MF_KEY_RE.search(page_url)
    if not key_m:
        raise RuntimeError(f"无法从 URL 提取 quick_key: {page_url}")
    key = key_m.group(1)

    api = cr.get("https://www.mediafire.com/api/1.5/file/get_info.php",
                 params={"quick_key": key, "response_format": "json"},
                 impersonate=UA_IMPERSONATE, timeout=30)
    fi = api.json()["response"]["file_info"]
    direct = mediafire_direct_url(page_url) or ""
    return {
        "quick_key": key,
        "direct_url": direct,
        "size": int(fi.get("size", 0)),
        "sha256": (fi.get("hash") or "").lower(),
        "filename": fi.get("filename", ""),
    }
