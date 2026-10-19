#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
terabox_dl.py — TeraBox 分享链接解析 / 直链下载工具（仅用 Python 标准库）

用法：
    # 只看文件信息（无需登录）
    python3 terabox_dl.py "https://dm.terabox.com/.../link?surl=xxxx" --info

    # 只打印直链（需要登录 Cookie）
    python3 terabox_dl.py "<分享链接>" --cookie "ndus=xxxx; ..." --print-url

    # 下载（断点续传）
    python3 terabox_dl.py "<分享链接>" --cookie "ndus=xxxx; ..." -o ./downloads

Cookie 获取方式：
    1. 浏览器登录 https://www.terabox.com
    2. F12 → Network → 任意请求 → Request Headers → 复制整条 Cookie
       （至少需要 ndus；建议整条复制，包含 ndut_fmt / browserid / csrfToken）
    3. --cookie "粘贴到这里"

说明：
    * 2026 年起 TeraBox 对匿名会话不再下发 dlink：
        - /share/list        → 能列出文件，但没有 dlink 字段
        - /share/download    → errno 400310 "need verify_v2" 或 errno 2
      登录后（带 ndus）才会签名下发 dlink，本脚本按官方前端同样的参数调用。
    * 仅用于下载你有权访问的文件；请遵守 TeraBox 服务条款。
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
API_HOST = "https://dm.terabox.com"
SHARE_HOST = "https://dm.terabox.com"
APP_ID = "250528"
CHUNK = 1024 * 1024

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Chromium";v="141", "Not?A_Brand";v="24", "Google Chrome";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


class TeraboxError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# HTTP 会话
# --------------------------------------------------------------------------- #
def build_opener(cookie_header: str | None) -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    if cookie_header:
        for part in cookie_header.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name, value = name.strip(), value.strip()
            if not name:
                continue
            jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name,
                    value=value,
                    port=None,
                    port_specified=False,
                    domain=".terabox.com",
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={"HttpOnly": None},
                    rfc2109=False,
                )
            )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = list(BASE_HEADERS.items())
    return opener


def http_get(
    opener: urllib.request.OpenerDirector,
    url: str,
    params: dict | None = None,
    referer: str | None = None,
    timeout: int = 30,
) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    if referer:
        req.add_header("Referer", referer)
        req.add_header("Origin", API_HOST)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def api_json(opener, path: str, params: dict, referer: str | None = None) -> dict:
    raw = http_get(opener, API_HOST + path, params, referer=referer)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise TeraboxError(f"接口返回非 JSON：{raw[:200]!r}")


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def parse_surl(link: str) -> str:
    link = link.strip()
    m = re.search(r"[?&]surl=([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    m = re.search(r"/s/([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
        return link
    raise TeraboxError("无法从链接中解析出 surl，请检查分享链接。")


def get_share_page(opener, surl: str) -> tuple[str, str]:
    """返回 (jsToken, referer)。"""
    url = f"{SHARE_HOST}/chinese/sharing/link?surl={urllib.parse.quote(surl)}&clearCache=1"
    html = http_get(opener, url).decode("utf-8", "replace")
    m = re.search(r"fn%28%22([0-9A-Fa-f]+)%22%29", html) or re.search(
        r'fn\("([0-9A-Fa-f]+)"\)', html
    )
    if not m:
        m = re.search(r"jsToken\s*=\s*[\"']([0-9A-Fa-f]{32,})[\"']", html)
    if not m:
        raise TeraboxError("未能从分享页提取 jsToken（页面结构可能已变化）。")
    return m.group(1), url


def shorturlinfo(opener, surl: str, js_token: str, referer: str) -> dict:
    params = {
        "app_id": APP_ID,
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
        "jsToken": js_token,
        "dp-logid": "".join(random.choice("0123456789") for _ in range(20)),
        "shorturl": surl if surl.startswith("1") else "1" + surl,
        "root": "1",
        "clientfrom": "h5",
        "psign": "0",
    }
    return api_json(opener, "/api/shorturlinfo", params, referer=referer)


def list_dir(opener, surl: str, js_token: str, referer: str, dir_path: str) -> list[dict]:
    params = {
        "app_id": APP_ID,
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
        "jsToken": js_token,
        "shorturl": surl,
        "root": "0",
        "dir": dir_path,
        "page": "1",
        "num": "1000",
    }
    data = api_json(opener, "/share/list", params, referer=referer)
    if data.get("errno") != 0:
        raise TeraboxError(f"列目录失败：{data.get('errno')} {data.get('errmsg', '')}")
    return data.get("list") or []


def flatten_files(opener, surl, js_token, referer, entries, depth=0) -> list[dict]:
    """把目录展开成文件列表。"""
    out: list[dict] = []
    if depth > 8:
        return out
    for e in entries:
        if str(e.get("isdir")) == "1":
            try:
                children = list_dir(opener, surl, js_token, referer, e.get("path", ""))
            except TeraboxError as exc:
                print(f"  ! 跳过目录 {e.get('server_filename')}: {exc}", file=sys.stderr)
                continue
            out.extend(flatten_files(opener, surl, js_token, referer, children, depth + 1))
        else:
            out.append(e)
    return out


def resolve_dlink(opener, info: dict, fs_id: str, js_token: str, referer: str) -> str:
    """按官方前端 _downloadByDlink() 的参数调用 /share/download。"""
    params = {
        "app_id": APP_ID,
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
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
    data = api_json(opener, "/share/download", params, referer=referer)
    errno = data.get("errno")
    if errno == 0 and data.get("dlink"):
        return data["dlink"]
    msg = data.get("errmsg") or ""
    if errno in (2, -6, 400310, 400210) or "verify" in msg.lower():
        raise TeraboxError(
            f"服务端拒绝下发直链（errno={errno} {msg}）。\n"
            "  → 现在必须登录：请在浏览器登录 terabox.com 后复制整条 Cookie，\n"
            "    用 --cookie \"ndus=...; ndut_fmt=...; browserid=...\" 重试。"
        )
    raise TeraboxError(f"获取直链失败：errno={errno} {msg}")


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def download(opener, url: str, dest: str, referer: str) -> None:
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    if have:
        req.add_header("Range", f"bytes={have}-")

    with opener.open(req, timeout=60) as resp:
        status = resp.getcode()
        if have and status != 206:
            have = 0  # 服务端不支持续传，重头来
        total = resp.headers.get("Content-Length")
        total = int(total) + have if total else None
        mode = "ab" if have else "wb"
        done = have
        t0 = time.time()
        last = 0.0
        with open(part, mode) as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last > 0.2:
                    last = now
                    speed = done / max(now - t0, 1e-6)
                    pct = f"{done * 100 / total:5.1f}%" if total else "  ?  "
                    print(
                        f"\r  {pct} {human(done)}"
                        + (f" / {human(total)}" if total else "")
                        + f"  {human(speed)}/s   ",
                        end="",
                        flush=True,
                    )
        print()

    if total and done < total:
        raise TeraboxError(f"下载不完整（{done}/{total}），可重新运行续传。")
    os.replace(part, dest)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="TeraBox 分享链接解析 / 直链下载（需登录 Cookie 才能拿到直链）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("url", help="TeraBox 分享链接，或单独的 surl")
    ap.add_argument("--cookie", default=os.environ.get("TERABOX_COOKIE", ""),
                    help="浏览器里复制的 Cookie 字符串（或设置 TERABOX_COOKIE）")
    ap.add_argument("--cookie-file", help="Netscape 格式 cookies.txt")
    ap.add_argument("--info", action="store_true", help="只显示文件信息，不下载")
    ap.add_argument("--print-url", action="store_true", help="只打印直链")
    ap.add_argument("-o", "--outdir", default=".", help="保存目录（默认当前目录）")
    ap.add_argument("--name", help="单文件时指定保存文件名")
    args = ap.parse_args()

    cookie_header = args.cookie
    if args.cookie_file:
        cj = http.cookiejar.MozillaCookieJar(args.cookie_file)
        cj.load(ignore_discard=True, ignore_expires=True)
        cookie_header = "; ".join(f"{c.name}={c.value}" for c in cj)

    opener = build_opener(cookie_header or None)
    surl = parse_surl(args.url)

    js_token, referer = get_share_page(opener, surl)
    info = shorturlinfo(opener, surl, js_token, referer)

    if info.get("errno") != 0:
        raise TeraboxError(
            f"shorturlinfo 失败：errno={info.get('errno')} {info.get('errmsg', '')}"
        )

    files = flatten_files(opener, surl, js_token, referer, info.get("list") or [])
    if not files:
        raise TeraboxError("分享中没有文件。")

    print(f"分享：{info.get('share_username', '?')}  文件数：{len(files)}")
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f.get('server_filename')}  ({human(int(f.get('size') or 0))})")

    if args.info:
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    for i, f in enumerate(files, 1):
        name = args.name if (args.name and len(files) == 1) else f.get("server_filename")
        name = os.path.basename(name or f"file_{i}")
        dest = os.path.join(args.outdir, name)
        print(f"\n>>> ({i}/{len(files)}) {name}")
        dlink = resolve_dlink(opener, info, f["fs_id"], js_token, referer)
        if args.print_url:
            print(dlink)
            continue
        if os.path.exists(dest) and os.path.getsize(dest) == int(f.get("size") or 0):
            print("  已存在且大小一致，跳过。")
            continue
        download(opener, dlink, dest, referer)
        print(f"  完成 → {dest}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TeraboxError as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        sys.exit(130)
