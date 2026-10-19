"""TeraBox 分享解析 / 下载 — 官方前端同参数链路(ndus Cookie)。

2026 年起 TeraBox 对匿名会话不再下发 dlink(/share/download 返回
errno 400310 "need verify_v2" 或 errno 2),必须带登录 Cookie(ndus)。
链路(与 docs/terabox/terabox-research.md 实测一致):

    1. GET 分享页            → jsToken + 匿名 Cookie
    2. GET /api/shorturlinfo → shareid/uk/sign/timestamp + 文件列表
    3. GET /share/download   → dlink(短时效,拿到立刻下载,不缓存)
    4. GET <dlink>           → CDN;CDN 同样校验 ndus Cookie

1024terabox.com / terasharelink.com 等镜像域与 dm.terabox.com 同账号
体系,shorturlinfo 按镜像域 referer 走也返回同一套数据;统一打到
dm.terabox.com 的 API(实测镜像链接可直接用其 surl 查询)。

Cookie 来源:settings 表 harvest.terabox_cookie_file 指向 Netscape
cookies.txt(# Netscape HTTP Cookie File 头 + 制表符七列)。
"""

from __future__ import annotations

import http.cookiejar
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlparse

from curl_cffi import requests as cr

log = logging.getLogger("harvest")

API_HOST = "https://dm.terabox.com"
APP_ID = "250528"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 分享页分享域:任意 terabox 系域名都能打开,统一用 dm.terabox.com 的
# /sharing/link 拿 jsToken(免得每个镜像域单独适配 jsToken 正则)。
SHARE_URL = API_HOST + "/sharing/link?surl={surl}"

# 已知镜像域(worker 侧识别「这是 terabox 链接」用;大小写不敏感)
TERABOX_HOST_FRAGS = (
    "terabox.com", "terabox.app", "1024tera", "terasharelink",
    "mirrobox", "nephobox", "4funbox", "freeterabox", "teraboxlink",
    "terashare", "dbshare",
)


class TeraboxError(RuntimeError):
    """TeraBox 解析/下载失败(Cookie 缺失/过期、接口变更、分享失效)。"""


def is_terabox_url(url: str) -> bool:
    host = urlparse(url).netloc.lower() if url else ""
    return any(frag in host for frag in TERABOX_HOST_FRAGS)


def parse_surl(link: str) -> str:
    """分享链接(任意镜像域)→ surl 短码。

    /s/<code> 的 code 原样保留(短码可能以 1 开头,不能剥 —— 与
    shorturlinfo 的「补前导 1」是两回事:API 参数 shorturl = 1 + surl,
    而页面 URL 里的整段就是 surl)。
    """
    m = re.search(r"[?&]surl=([A-Za-z0-9_-]+)", link or "")
    if m:
        return m.group(1)
    m = re.search(r"/s/([A-Za-z0-9_-]{10,})", link or "")
    if m:
        return m.group(1)
    raise TeraboxError(f"无法从链接解析 surl: {link}")


def load_cookie_header(cookie_file: str | None) -> str:
    """Netscape cookies.txt → "k=v; k=v" 头。

    只保留 terabox 系域的条目(cookie 文件可能混有其他站的);
    expired 行(0/负数)也带上 —— ndus 这类会话值在部分导出里 expiry
    是 0,.ignore_expires 语义与浏览器一致:未失效就发。
    """
    if not cookie_file or not cookie_file.strip():
        raise TeraboxError("未配置 TeraBox Cookie 文件(harvest.terabox_cookie_file)")
    path = Path(cookie_file.strip()).expanduser()
    if not path.is_file():
        raise TeraboxError(f"TeraBox Cookie 文件不存在: {path}")
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if "terabox" not in domain.lower() and "dubox" not in domain.lower():
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(f"{name}={value}")
    if not any(c.startswith("ndus=") for c in out):
        raise TeraboxError("Cookie 文件里没有 ndus —— 请导出已登录 terabox.com 的 Cookie")
    return "; ".join(out)


def _headers(referer: str | None) -> dict:
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        h["Referer"] = referer
        h["Origin"] = API_HOST
    return h


def _get(cookie_header: str, url: str, *, params: dict | None = None,
         referer: str | None = None, timeout: float = 30.0) -> cr.Response:
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    # curl_cffi 的 cookies 参数只认 dict/CookieJar,字符串头走 headers
    h = _headers(referer)
    h["Cookie"] = cookie_header
    return cr.get(url, headers=h, impersonate="chrome", timeout=timeout,
                  proxy=_proxy())


def _proxy() -> str | None:
    """与 net._proxy 同源(settings 表 harvest.proxy)。"""
    from app.database import SessionLocal
    from app.services import settings_store
    s = SessionLocal()
    try:
        val = str(settings_store.harvest_conf(s).get("harvest.proxy") or "").strip()
        return val or None
    finally:
        s.close()


def _api_json(resp: cr.Response, what: str) -> dict:
    try:
        return json.loads(resp.text)
    except ValueError:
        raise TeraboxError(f"{what} 返回非 JSON: {resp.text[:120]!r}")


@dataclass
class TeraBoxFile:
    fs_id: str
    filename: str
    size: int
    md5: str = ""
    path: str = ""
    dlink: str = ""          # 直链(短时效,resolve_dlink 返回后立即用)
    children: list = field(default_factory=list)  # 目录展开前的原始条目


def _share_page_token(cookie_header: str, surl: str) -> str:
    """分享页 → jsToken(页面里 fn("HEX") 形态)。"""
    r = _get(cookie_header, SHARE_URL.format(surl=surl), timeout=30.0)
    if r.status_code != 200:
        raise TeraboxError(f"分享页 HTTP {r.status_code}")
    m = (re.search(r'fn%28%22([0-9A-Fa-f]{32,})%22%29', r.text)
         or re.search(r'fn\("([0-9A-Fa-f]{32,})"\)', r.text)
         or re.search(r"jsToken\s*=\s*['\"]([0-9A-Fa-f]{32,})['\"]", r.text))
    if not m:
        raise TeraboxError("分享页未能提取 jsToken(接口可能已变更)")
    return m.group(1)


_COMMON_PARAMS = {
    "app_id": APP_ID,
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}


def _shorturlinfo(cookie_header: str, surl: str, js_token: str,
                  referer: str) -> dict:
    params = {
        **_COMMON_PARAMS,
        "jsToken": js_token,
        "dp-logid": "".join(random.choice("0123456789") for _ in range(20)),
        # shorturl 必须补前导 1;clientfrom=h5&psign=0 缺一即 400210 verify_v2
        "shorturl": surl if surl.startswith("1") else "1" + surl,
        "root": "1",
        "clientfrom": "h5",
        "psign": "0",
    }
    r = _get(cookie_header, API_HOST + "/api/shorturlinfo", params=params,
             referer=referer)
    return _api_json(r, "shorturlinfo")


def _share_list(cookie_header: str, surl: str, js_token: str,
                referer: str, dir_path: str) -> list[dict]:
    params = {
        **_COMMON_PARAMS,
        "jsToken": js_token,
        "shorturl": surl,
        "root": "0",
        "dir": dir_path,
        "page": "1",
        "num": "1000",
    }
    r = _get(cookie_header, API_HOST + "/share/list", params=params,
             referer=referer)
    data = _api_json(r, "share/list")
    if data.get("errno") != 0:
        raise TeraboxError(f"列目录失败 errno={data.get('errno')}")
    return data.get("list") or []


def _flatten(cookie_header: str, surl: str, js_token: str, referer: str,
             entries: list[dict], depth: int = 0) -> list[dict]:
    """目录递归展开成文件列表(与官方分享页目录树一致)。"""
    out: list[dict] = []
    if depth > 8:
        return out
    for e in entries:
        if str(e.get("isdir")) == "1":
            out.extend(_flatten(cookie_header, surl, js_token, referer,
                                _share_list(cookie_header, surl, js_token,
                                            referer, e.get("path", "")),
                                depth + 1))
        else:
            out.append(e)
    return out


def _resolve_meta(cookie_header: str, surl: str) -> tuple[str, str, dict, list[dict]]:
    """分享 → (jsToken, referer, shorturlinfo, 文件平铺列表)。"""
    js_token = _share_page_token(cookie_header, surl)
    referer = SHARE_URL.format(surl=surl)
    info = _shorturlinfo(cookie_header, surl, js_token, referer)
    errno = info.get("errno")
    if errno != 0:
        raise TeraboxError(f"shorturlinfo errno={errno}"
                           + ("(Cookie 过期或分享失效)" if errno in (2, -6, 400310, 400210) else ""))
    files = _flatten(cookie_header, surl, js_token, referer,
                     info.get("list") or [])
    if not files:
        raise TeraboxError("分享中没有文件")
    return js_token, referer, info, files


def _dlink_for(cookie_header: str, js_token: str, referer: str,
               info: dict, fs_id: str) -> str:
    params = {
        **_COMMON_PARAMS,
        "jsToken": js_token,
        "dp-logid": "".join(random.choice("0123456789") for _ in range(20)),
        "scene": "purchased_list",
        "shareid": str(info["shareid"]),
        "sign": info["sign"],
        "timestamp": str(info["timestamp"]),
        "fid_list": json.dumps([str(fs_id)]),
        "uk": str(info["uk"]),
        "primaryid": str(info["shareid"]),
        "product": "share",
        "nozip": "0",
    }
    r = _get(cookie_header, API_HOST + "/share/download", params=params,
             referer=referer)
    data = _api_json(r, "share/download")
    if data.get("errno") != 0 or not data.get("dlink"):
        errno = data.get("errno")
        if errno in (2, -6, 400310, 400210):
            raise TeraboxError(
                f"服务端拒绝下发直链(errno={errno}) —— Cookie 过期,请更新 harvest.terabox_cookie_file")
        raise TeraboxError(f"获取直链失败 errno={errno}")
    return data["dlink"]


def resolve_dlink(cookie_header: str, share_url: str,
                  *, index: int = 0) -> TeraBoxFile:
    """分享链接 → 第 index 个文件的 TeraBoxFile(带 dlink)。

    dlink 短时效(sign/timestamp 过期很快),调用方拿到必须立刻下载,
    不得缓存或重试时复用。
    """
    surl = parse_surl(share_url)
    js_token, referer, info, files = _resolve_meta(cookie_header, surl)
    if index >= len(files):
        raise TeraboxError(f"文件序号越界: {index}/{len(files)}")
    f = files[index]
    dlink = _dlink_for(cookie_header, js_token, referer, info, f["fs_id"])
    return TeraBoxFile(
        fs_id=str(f["fs_id"]),
        filename=f.get("server_filename") or f"terabox-{f['fs_id']}",
        size=int(f.get("size") or 0),
        md5=(f.get("md5") or "").lower(),
        path=f.get("path") or "",
        dlink=dlink,
    )


def resolve_dlink_by_ids(cookie_header: str, surl: str, fs_id: str,
                         *, referer: str = "") -> TeraBoxFile:
    """按 surl + fs_id 现取 dlink(下载阶段逐卷调用,dlink 不落库)。

    重走一遍 meta(shareid/sign 短时效,无法跨阶段复用),但按 fs_id
    精确定位文件,不依赖文件序号(分享内容在解析与下载之间不会变,
    序号却可能因重新展开而漂移)。
    """
    js_token, referer, info, files = _resolve_meta(cookie_header, surl)
    for f in files:
        if str(f["fs_id"]) == str(fs_id):
            dlink = _dlink_for(cookie_header, js_token, referer, info, fs_id)
            return TeraBoxFile(
                fs_id=str(fs_id),
                filename=f.get("server_filename") or f"terabox-{fs_id}",
                size=int(f.get("size") or 0),
                md5=(f.get("md5") or "").lower(),
                path=f.get("path") or "",
                dlink=dlink,
            )
    raise TeraboxError(f"分享中找不到 fs_id {fs_id}")


def download_file(cookie_header: str, f: TeraBoxFile, dest: Path, *,
                  on_progress=None, stream_key=None,
                  max_bytes: int = 8 * 1024**3) -> Path:
    """下载单个文件到 dest(复用 pipeline.download_stream:续传/SHA 由它管)。

    CDN 校验 ndus Cookie,请求必须带 cookie_header;dlink 短时效,
    失效后由调用方重新解析(这里不重试,失败语义与 mediafire 直链一致)。
    dlink 绑定解析请求的出口 IP(TeraBox CDN 签名校验含 IP),下载必须与
    解析走同一出口 —— 即同样跟随 harvest.proxy(use_proxy=True;未配代理
    时 _proxy() 返回 None,同为直连,行为不变)。
    """
    from . import pipeline
    # terabox 只给 content-md5(且常为空),download_stream 的校验是
    # SHA256 语义,不适用 —— 完整性由 worker 的大小核对兜底
    return pipeline.download_stream(
        f.dlink, dest, max_bytes=max_bytes, on_progress=on_progress,
        stream_key=stream_key, use_proxy=True,
        headers={"Cookie": cookie_header, "User-Agent": UA,
                 "Referer": API_HOST + "/"})
