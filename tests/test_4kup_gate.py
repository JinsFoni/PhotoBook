"""4kup 老帖的站内中转短链(bit.ly → p/go.html → getlink,XXTEA 加密)。

2026-10-24 任务 824(MFStar Vol.076 Mu Yu Qian)报「详情页未找到下载短链」。
实查:2022 及更早的 4kup 帖子下载按钮不是直链,而是

    <a href='https://bit.ly/3U2VFgk'>Download from terabox.com</a>

点开是站内广告中转页,密码在页面里:

    bit.ly/<code>  301→  https://www.4kup.net/p/go.html#?u=<XXTEA+base64 令牌>
    页面 JS         →   https://4kup.net/getlink/?u=<令牌>
    Tea.decrypt(令牌, config.defaultkey) → JSON {"url": "<真网盘链接>"}

我们既没认 bit.ly(短链白名单只有 ouo),页面上也没有直挂 terabox → 一条
下载源都收不到。这里用**自造令牌**覆盖解析链路(cr.get / fetch_html 全打桩,
不发网络请求)。
"""

from __future__ import annotations

import base64
import json
from urllib.parse import quote

import pytest

from app.services.harvest import net, worker

# ---- 测试自用的 XXTEA 加密(镜像 getlink 页面的 Tea.encode,生产只要解密) ----

_DELTA = 0x9E3779B9
_M32 = 0xFFFFFFFF


def _longs(data: bytes) -> list[int]:
    data = data + b"\0" * ((4 - len(data) % 4) % 4)
    return [int.from_bytes(data[i:i + 4], "little")
            for i in range(0, len(data), 4)]


def xxtea_encrypt(plain: str, key: str) -> str:
    """明文 → 令牌(base64),与页面 JS 的 Tea.encrypt 等价。"""
    v = _longs(plain.encode("utf-8"))
    if len(v) < 2:
        v.append(0)
    k = _longs(key.encode("utf-8")[:16].ljust(4, b"\0"))
    while len(k) < 4:
        k.append(0)
    n = len(v)
    rounds = 6 + 52 // n
    total = 0
    z, y = v[n - 1], v[0]
    while rounds:
        total = (total + _DELTA) & _M32
        e = (total >> 2) & 3
        for p in range(n):
            y = v[(p + 1) % n]
            mx = ((((z >> 5) ^ ((y << 2) & _M32))
                   + ((y >> 3) ^ ((z << 4) & _M32))) & _M32) \
                ^ (((total ^ y) + (k[(p & 3) ^ e] ^ z)) & _M32)
            z = v[p] = (v[p] + mx) & _M32
        rounds -= 1
    raw = b"".join(x.to_bytes(4, "little") for x in v)
    return base64.b64encode(raw).decode()


def _token_with_specials(payload: dict, key: str = net.FOURKUP_GATE_KEY) -> str:
    """拿一个既含 `+` 又含 `/` 的令牌(覆盖 URL 百分号编码那条路)。"""
    text = json.dumps(payload)
    for pad in range(0, 40):
        token = xxtea_encrypt(text + " " * pad, key)
        if "+" in token and "/" in token:
            return token
    return token  # 极少数情况拿不到, 用最后一个(zip 长度对齐即可)


class _Redirect:
    """打桩的 301 响应: Location 里带 #?u=<百分号编码的令牌>。"""

    def __init__(self, token: str, status: int = 301):
        self.status_code = status
        self.headers = {
            "location": f"https://www.4kup.net/p/go.html#?u={quote(token, safe='')}"}


def _patch_redirect(monkeypatch, token: str, seen: list | None = None):
    def fake_get(url, **kw):
        if seen is not None:
            seen.append((url, kw))
        return _Redirect(token)
    monkeypatch.setattr(net.cr, "get", fake_get)


# ---- 令牌加解密 --------------------------------------------------------------

def test_xxtea_roundtrip():
    payload = {"url": "https://terabox.com/s/1OmrqqD_hO-gzAsjUDqDkHw",
               "note2": "4kup"}
    token = xxtea_encrypt(json.dumps(payload), net.FOURKUP_GATE_KEY)
    raw = net._xxtea_decrypt(token, net.FOURKUP_GATE_KEY)
    assert json.loads(raw.decode("utf-8")) == payload


def test_xxtea_wrong_key_does_not_explode():
    token = xxtea_encrypt('{"url":"x"}', net.FOURKUP_GATE_KEY)
    with pytest.raises(Exception):
        json.loads(net._xxtea_decrypt(token, "not-the-key").decode("utf-8"))


# ---- 页面链接收集 ------------------------------------------------------------

# 824 的真实形态:下载按钮单引号 + 图库大图链接(绝不能当下载源)
PAGE_824 = """
<html><head><meta property="og:title" content="MFStar Vol.076 Mu Yu Qian"></head>
<body>
<article id="post-7580" class="post-7580 post type-post status-publish">
  <h1 class="entry-title">MFStar Vol.076 Mu Yu Qian (慕羽茜)</h1>
  <div class="entry-content">
    <p><a href='https://bit.ly/3U2VFgk' target='_blank' rel="nofollow noopener">Download from terabox.com</a></p>
    <a class="thumb-photo" href="https://lh5.ggpht.com/x/4kup-mfstar-vol-76-1.jpg"><img></a>
  </div>
</article>
</body></html>
"""


def test_collect_gate_links_from_old_post_template():
    """单引号 href 的 bit.ly 能被收出来,图库链接不会误收。"""
    assert net._collect_4kup_gate_links(PAGE_824) == ["https://bit.ly/3U2VFgk"]


def test_collect_gate_links_dedupes_and_skips_other_hosts():
    html = ("<a href=\"https://bit.ly/aaa\">x</a>"
            "<a href='https://bit.ly/aaa'>y</a>"
            "<a href='https://1024terabox.com/s/zzz'>t</a>"
            "<a href='https://lh5.ggpht.com/x.jpg'>img</a>")
    assert net._collect_4kup_gate_links(html) == ["https://bit.ly/aaa"]


def test_4kup_parse_keeps_gate_link_as_shortlink():
    """老帖页面上没有直挂 terabox → 中转短链必须进 shortlinks, 否则 worker 无事可做。"""
    target = net.parse_4kup_detail_page("https://4kup.net/mfstar-vol-076-mu-yu-qian/",
                                        existing_html=PAGE_824)
    assert target.shortlinks == ["https://bit.ly/3U2VFgk"]


def test_4kup_parse_keeps_direct_terabox_first():
    """直链与中转短链同时存在时: 直链在前(优先级不变), 中转短链补在后。"""
    html = PAGE_824.replace(
        "<p><a href='https://bit.ly/3U2VFgk'",
        "<p><a href='https://1024terabox.com/s/direct'>Download from 1024terabox.com</a></p>\n"
        "    <p><a href='https://bit.ly/3U2VFgk'")
    target = net.parse_4kup_detail_page("https://4kup.net/x/", existing_html=html)
    assert target.shortlinks == ["https://1024terabox.com/s/direct",
                                 "https://bit.ly/3U2VFgk"]


def test_is_4kup_gate_link():
    for url in ("https://bit.ly/3U2VFgk", "https://tinyurl.com/abc",
                "https://www.4kup.net/p/go.html#?u=abc",
                "https://4kup.net/getlink/?u=abc"):
        assert net.is_4kup_gate_link(url), url
    for url in ("https://1024terabox.com/s/abc",
                "https://www.mediafire.com/file/abc/x.rar/file",
                "https://misskon.com/1234-x/", ""):
        assert not net.is_4kup_gate_link(url), url


# ---- 中转短链解析 ------------------------------------------------------------

def test_resolve_gate_terabox(monkeypatch):
    """令牌解出 terabox 分享 → 原样返回(由 worker 走 TeraBox 分支)。"""
    token = _token_with_specials(
        {"url": "https://terabox.com/s/1OmrqqD_hO-gzAsjUDqDkHw", "note2": "4kup"})
    seen: list = []
    _patch_redirect(monkeypatch, token, seen)
    url = net.resolve_4kup_gate("https://bit.ly/3U2VFgk")
    assert url == "https://terabox.com/s/1OmrqqD_hO-gzAsjUDqDkHw"
    assert seen and seen[0][0] == "https://bit.ly/3U2VFgk"
    assert seen[0][1].get("allow_redirects") is False   # 自己跟跳转, 拿 Location


def test_resolve_gate_mediafire(monkeypatch):
    token = _token_with_specials(
        {"url": "https://www.mediafire.com/file/u565jqfr9bphwh3/XIUREN_No.4327.rar/file"})
    _patch_redirect(monkeypatch, token)
    assert net.resolve_4kup_gate("https://bit.ly/3Z9vt4X").endswith("XIUREN_No.4327.rar/file")


def test_resolve_gate_uses_key_from_interstitial(monkeypatch):
    """密钥变了也不至于废: 令牌解不开时现场读中转页里的 defaultkey。"""
    token = _token_with_specials({"url": "https://terabox.com/s/abc"}, key="otherkey")
    _patch_redirect(monkeypatch, token)
    monkeypatch.setattr(net, "fetch_html",
                        lambda url, **kw: "config = { defaultkey: 'otherkey', }")
    assert net.resolve_4kup_gate("https://bit.ly/abc") == "https://terabox.com/s/abc"


def test_resolve_gate_needs_password(monkeypatch):
    """解不开又不给密钥 → 明确报「可能需要口令」, 不要静默当没有链接。"""
    token = _token_with_specials({"url": "https://terabox.com/s/abc"}, key="secret")
    _patch_redirect(monkeypatch, token)
    monkeypatch.setattr(net, "fetch_html",
                        lambda url, **kw: "config = { defaultkey: 'maxbong', }")
    with pytest.raises(ValueError, match="口令"):
        net.resolve_4kup_gate("https://bit.ly/abc")


def test_resolve_gate_without_redirect(monkeypatch):
    class _Ok:
        status_code = 200
        headers: dict = {}

    monkeypatch.setattr(net.cr, "get", lambda *a, **kw: _Ok())
    with pytest.raises(ValueError, match="没有跳到中转页"):
        net.resolve_4kup_gate("https://bit.ly/abc")


def test_resolve_gate_rejects_non_url_payload(monkeypatch):
    token = _token_with_specials({"url": "", "zip": "abc"})
    _patch_redirect(monkeypatch, token)
    with pytest.raises(ValueError, match="没给出下载地址"):
        net.resolve_4kup_gate("https://bit.ly/abc")


# ---- worker 分流 -------------------------------------------------------------

def _target(shortlinks):
    return net.HarvestTarget(serial=7580, title="MFStar Vol.076 Mu Yu Qian",
                             model_name="Mu Yu Qian", password="4kup",
                             shortlinks=shortlinks)


def test_worker_gate_lands_on_terabox(monkeypatch):
    """中转短链解出 terabox → 整包走 TeraBox 分支(逐文件展开)。"""
    class FakeTB:
        @staticmethod
        def load_cookie_header(path):
            return "ndus=x"

        @staticmethod
        def _share_page_token(hdr, surl):
            return "tok"

        @staticmethod
        def _shorturlinfo(hdr, surl, tok, ref):
            return {"errno": 0, "shareid": 1, "uk": 2, "sign": "s", "timestamp": 3,
                    "list": [{"isdir": "0", "fs_id": 21,
                              "server_filename": "MFStar_Vol.076.rar",
                              "size": 100, "md5": ""}]}

        @staticmethod
        def _flatten(hdr, surl, tok, ref, entries):
            return entries

    monkeypatch.setattr(net, "resolve_4kup_gate",
                        lambda url, **kw: "https://terabox.com/s/1OmrqqD_hO")
    monkeypatch.setattr(worker.terabox, "load_cookie_header", FakeTB.load_cookie_header)
    monkeypatch.setattr(worker.terabox, "_share_page_token", FakeTB._share_page_token)
    monkeypatch.setattr(worker.terabox, "_shorturlinfo", FakeTB._shorturlinfo)
    monkeypatch.setattr(worker.terabox, "_flatten", FakeTB._flatten)

    from unittest.mock import patch
    with patch.object(worker.settings_store, "harvest_conf",
                      return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(None, None, _target(["https://bit.ly/3U2VFgk"]))
    assert [i["filename"] for i in infos] == ["MFStar_Vol.076.rar"]
    assert infos[0]["terabox"]["fs_id"] == "21"


def test_worker_gate_lands_on_mediafire(monkeypatch):
    """中转短链解出 MediaFire → 走 MF 直链解析(与 ouo 落地同路)。"""
    seen = []

    def fake_mf_info(page_url, **kw):
        seen.append(page_url)
        return {"quick_key": "k", "direct_url": "http://d", "size": 1,
                "sha256": "", "filename": "x.rar"}

    monkeypatch.setattr(net, "resolve_4kup_gate",
                        lambda url, **kw: "https://www.mediafire.com/file/19vc/x.rar")
    monkeypatch.setattr(net, "mediafire_info_from_url", fake_mf_info)
    infos = worker._resolve_infos(None, None, _target(["https://bit.ly/3jQGbhA"]))
    assert seen == ["https://www.mediafire.com/file/19vc/x.rar"]
    assert infos and infos[0]["filename"] == "x.rar"


def test_worker_gate_failure_reports_reason(monkeypatch):
    """中转页解析不出来 → 任务失败文案要带原因, 不能只说「未找到下载短链」。"""
    monkeypatch.setattr(net, "resolve_4kup_gate",
                        lambda url, **kw: (_ for _ in ()).throw(
                            ValueError("短链打不开: boom")))

    class FakeJob:
        serial = 7580

        def __init__(self):
            self.status = ""
            self.error = None

    job = FakeJob()
    finished = {}

    class _S:
        def commit(self):
            pass

    def fake_finish(s, j, status, error=None):
        j.status, j.error = status, error
        finished["status"] = status

    monkeypatch.setattr(worker, "_finish", fake_finish)
    infos = worker._resolve_infos(_S(), job, _target(["https://bit.ly/3U2VFgk"]))
    assert infos is None
    assert finished["status"] == "failed"
    assert job.error == "中转短链解析失败: 短链打不开: boom"
