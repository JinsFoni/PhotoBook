"""TeraBox 分支 — cookie 加载 / surl 解析 / 下载源分流(本地逻辑,不发网络请求)。

真实端到端(4kup 页面 → terabox dlink → 下载 → 4kup 密码解压)已在开发时
人工验证;这里覆盖回归面:纯函数与 worker 分流决策。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from app.services.harvest import net, terabox, worker
from app.services.harvest.filters import FilterResult

# ---- cookie 文件加载 ---------------------------------------------------------

NETSCAPE = """# Netscape HTTP Cookie File
# This is a generated file! Do not edit.

.terabox.com\tTRUE\t/\tTRUE\t1810933410\tndus\tYzA8fake
.dm.terabox.com\tTRUE\t/\tTRUE\t1823905476\t__stripe_mid\t400fccd9
.terabox.com\tTRUE\t/\tFALSE\t1823904042\tPANWEB\t1
.dm.terabox.com\tTRUE\t/\tFALSE\t1823904044\tTSID\tyj4pkm8
"""


def _write_cookie(tmp_path: Path, text: str) -> str:
    p = tmp_path / "cookies.txt"
    p.write_text(text, "utf-8")
    return str(p)


def test_load_cookie_header_keeps_terabox_only(tmp_path):
    hdr = terabox.load_cookie_header(_write_cookie(tmp_path, NETSCAPE))
    assert "ndus=YzA8fake" in hdr
    assert "TSID=yj4pkm8" in hdr
    assert "__stripe_mid" in hdr


def test_load_cookie_header_missing_ndus(tmp_path):
    text = NETSCAPE.replace("\tndus\tYzA8fake\n", "\n")
    with pytest.raises(terabox.TeraboxError, match="ndus"):
        terabox.load_cookie_header(_write_cookie(tmp_path, text))


def test_load_cookie_header_missing_file():
    with pytest.raises(terabox.TeraboxError, match="不存在"):
        terabox.load_cookie_header("/nonexistent/cookies.txt")


def test_load_cookie_header_empty_disabled():
    with pytest.raises(terabox.TeraboxError):
        terabox.load_cookie_header("")


def test_download_file_uses_same_egress_as_resolve(monkeypatch, tmp_path):
    """dlink 绑定解析出口 IP: 下载必须跟随 harvest.proxy(与解析同出口)。

    NAS 实录: 解析走代理, 下载 use_proxy=False 直连 → CDN 302 /error/302.html;
    与解析同走代理 → 200。
    """
    captured = {}

    def fake_download_stream(url, dest, *, expected_sha256="", max_bytes=0,
                             on_progress=None, stream_key=None,
                             use_proxy=True, headers=None,
                             retries=3, proxy_fallback=True):
        captured["use_proxy"] = use_proxy
        captured["headers"] = headers
        captured["proxy_fallback"] = proxy_fallback
        return dest

    import unittest.mock as mock
    from app.services.harvest import pipeline as harvest_pipeline
    with mock.patch.object(harvest_pipeline, "download_stream",
                           fake_download_stream):
        f = terabox.TeraBoxFile(fs_id="1", filename="a.rar", size=1,
                                dlink="https://dm-d.terabox.com/x")
        terabox.download_file("ndus=x", f, tmp_path / "a.rar")
    assert captured["use_proxy"] is True
    # 换出口(代理→直连)会让 dlink 签名失效 → 必须显式关掉这条兜底
    assert captured["proxy_fallback"] is False
    assert captured["headers"]["Cookie"] == "ndus=x"
    assert captured["headers"]["Referer"] == terabox.API_HOST + "/"


# ---- surl / 域识别 -----------------------------------------------------------

def test_parse_surl():
    assert terabox.parse_surl("https://1024terabox.com/s/19erS_KtZWnO8hvaraWCavg") \
        == "19erS_KtZWnO8hvaraWCavg"
    assert terabox.parse_surl("https://dm.terabox.com/sharing/link?surl=0Y8ZvbwJrqOO4n35IAOVLQ") \
        == "0Y8ZvbwJrqOO4n35IAOVLQ"
    assert terabox.parse_surl("https://terasharelink.com/s/1abcDEF123") == "1abcDEF123"


def test_is_terabox_url():
    for url in ("https://1024terabox.com/s/abc", "https://www.terabox.app/s/abc",
                "https://terasharelink.com/s/abc", "https://mirrobox.com/s/abc"):
        assert terabox.is_terabox_url(url), url
    assert not terabox.is_terabox_url("https://www.mediafire.com/file/abc/x.rar/file")
    assert not terabox.is_terabox_url("")


# ---- 4kup 详情页解析 ---------------------------------------------------------

FOURKUP_HTML = """
<html><head>
<meta property="og:title" content="[JP] Toyoda Runa (&#35920;&#30000;&#12523;&#12490;) &#36969&#21002">
</head><body>
<article id="post-53150" class="post-53150 post type-post status-publish">
  <h1 class="entry-title">[JP] Toyoda Runa (豊田ルナ) 週刊少年マガジン</h1>
  <time class="entry-date published" datetime="2026-10-17T05:11:01+00:00"></time>
  <div class='download-box'>
  <p id='download'><a href='https://1024terabox.com/s/19erS_KtZWnO8hvaraWCavg'>Download</a></p>
  </div>
  <span><a href="https://4kup.net/category/korean/" rel="category tag">Korean</a>,
  <a href="https://4kup.net/category/le/" rel="category tag">LE</a></span>
</article>
</body></html>
"""


def test_4kup_parse_title_model_and_links():
    target = net.parse_4kup_detail_page("https://4kup.net/le-gms-006a-gms/",
                                        existing_html=FOURKUP_HTML)
    assert target.serial == 53150
    assert target.model_name == "Toyoda Runa"
    # 原生名一并带出 → import_album 写 models.stage_name(前台「又名 …」)
    # (这份 fixture 的 og:title 用数字实体写的, 原生名以解析结果为准)
    assert target.model_native and target.model_native in target.title
    assert target.password == "4kup"
    assert target.shortlinks == ["https://1024terabox.com/s/19erS_KtZWnO8hvaraWCavg"]
    assert "Korean" in target.tags and "LE" in target.tags
    assert target.published == "2026.10.17"


def test_4kup_parse_publisher_code_title():
    # [LE] GMS-006A GMS:GMS 曾被当「系列名」判无人名,2026-10-27 用户确认
    # 它是模特名(假模特 le 那批就是这么来的),现在按名字位抽出。
    html = FOURKUP_HTML.replace("[JP] Toyoda Runa (豊田ルナ) 週刊少年マガジン",
                                "[LE] GMS-006A GMS")
    html = html.replace(
        "[JP] Toyoda Runa (&#35920;&#30000;&#12523;&#12490;) &#36969&#21002",
        "[LE] GMS-006A GMS")
    target = net.parse_4kup_detail_page("https://4kup.net/post-53150",
                                        existing_html=html)
    assert target.model_name == "GMS"


def test_4kup_serial_fallback_via_page():
    # slug 无数字 → 序号从页面 post id 取
    target = net.parse_4kup_detail_page("https://4kup.net/some-slug/",
                                        existing_html=FOURKUP_HTML)
    assert target.serial == 53150


def test_4kup_scan_list_page_parsing():
    listing = """
    <article id="post-53150" class="post-53150 post type-post hentry">
      <h2 class="entry-title"><a href="https://4kup.net/le-gms-006a-gms/">T1</a></h2>
    </article>
    <article id="post-53149" class="post-53149 post type-post hentry">
      <h2 class="entry-title"><a href="https://4kup.net/yin-tian-tian-5/">T2</a></h2>
    </article>
    <a href="https://4kup.net/page/2/"></a>
    """
    import unittest.mock as mock
    with mock.patch.object(net, "fetch_html", return_value=listing):
        links, has_next = net.scan_4kup_list_page("https://4kup.net/")
    assert links == [(53149, "https://4kup.net/yin-tian-tian-5/"),
                     (53150, "https://4kup.net/le-gms-006a-gms/")]
    assert has_next


# ---- worker 下载源分流 -------------------------------------------------------

def _target(shortlinks):
    return net.HarvestTarget(serial=1, title="T", model_name="M",
                             password="", shortlinks=shortlinks)


def test_resolve_infos_prefers_mediafire(monkeypatch):
    """同时挂 mediafire 与 terabox → 只走 mediafire(ouo 短链解析后进 MF)。"""
    calls = []

    def fake_resolve_ouo(link):
        return "https://www.mediafire.com/file/abc123/x.rar/file"

    def fake_mf_info(page_url, **kw):
        calls.append(page_url)
        return {"quick_key": "k", "direct_url": "http://d", "size": 1,
                "sha256": "", "filename": "x.rar"}

    monkeypatch.setattr(net, "resolve_ouo", fake_resolve_ouo)
    monkeypatch.setattr(net, "mediafire_info_from_url", fake_mf_info)
    infos = worker._resolve_infos(None, None, _target([
        "https://ouo.io/AbCdEf123",                  # ouo(锚文本标 mediafire)
        "https://1024terabox.com/s/aaa",
    ]))
    assert infos and infos[0]["filename"] == "x.rar"
    assert not any(i.get("terabox") for i in infos)


def test_resolve_infos_terabox_when_no_mediafire(monkeypatch):
    """只挂 terabox(4kup 形态)→ 走 TeraBox,逐文件展开。"""
    import json

    class FakeTB:
        @staticmethod
        def load_cookie_header(path):
            assert path  # 配置了 cookie 文件才走到这里
            return "ndus=x"

        @staticmethod
        def _share_page_token(hdr, surl):
            return "tok"

        @staticmethod
        def _shorturlinfo(hdr, surl, tok, ref):
            return {"errno": 0, "shareid": 1, "uk": 2, "sign": "s", "timestamp": 3,
                    "list": [{"isdir": "0", "fs_id": 11, "server_filename": "a.part1.rar",
                              "size": 100, "md5": ""},
                             {"isdir": "0", "fs_id": 12, "server_filename": "a.part2.rar",
                              "size": 50, "md5": "d41d"}]}

        @staticmethod
        def _flatten(hdr, surl, tok, ref, entries):
            return entries

    import app.services.harvest as pkg
    monkeypatch.setattr(worker.terabox, "load_cookie_header", FakeTB.load_cookie_header)
    monkeypatch.setattr(worker.terabox, "_share_page_token", FakeTB._share_page_token)
    monkeypatch.setattr(worker.terabox, "_shorturlinfo", FakeTB._shorturlinfo)
    monkeypatch.setattr(worker.terabox, "_flatten", FakeTB._flatten)

    from unittest.mock import patch
    with patch.object(worker.settings_store, "harvest_conf",
                      return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(None, None, _target(
            ["https://1024terabox.com/s/19erS_KtZWnO8hvaraWCavg"]))
    assert [i["filename"] for i in infos] == ["a.part1.rar", "a.part2.rar"]
    assert all(i["direct_url"] == "" and i.get("terabox") for i in infos)
    assert infos[0]["terabox"]["fs_id"] == "11"


class _FakeSession:
    """_resolve_infos 异常路径的 commit 收口(真实 session 不进单测)。"""

    def commit(self):
        pass


def test_resolve_infos_unsupported_host(monkeypatch):
    """链接落地 pixeldrain 等不支持平台 → 报平台名落 failed。"""
    def fake_resolve(link):
        raise net.UnsupportedHostError("Pixeldrain")
    monkeypatch.setattr(net, "resolve_ouo", fake_resolve)

    class FakeJob:
        serial = 999999
        def __init__(self):
            self.status = ""
            self.error = None
    job = FakeJob()
    finished = {}

    def fake_finish(s, j, status, error=None):
        j.status = status
        j.error = error
        finished["status"] = status
    monkeypatch.setattr(worker, "_finish", fake_finish)
    infos = worker._resolve_infos(_FakeSession(), job,
                                  _target(["https://pixeldrain.com/u/1"]))
    assert infos is None
    assert finished["status"] == "failed"
    assert "Pixeldrain" in (job.error or "")


# ---- titlemodel(标题抽模特名,docs/model-name 规则) -------------------------

def test_titlemodel_pairs_and_coser():
    f = worker.__dict__ and __import__(
        "app.services.harvest.titlemodel", fromlist=["model_name_from_title"])
    assert f.model_name_from_title("[JP] Toyoda Runa (豊田ルナ) 週刊少年マガジン") \
        == ("Toyoda Runa", "豊田ルナ")
    assert f.model_name_from_title("Coser@洛璃LoLiSAMA 碧蓝航线 信浓赛车")[0] \
        == "洛璃LoLiSAMA"
    assert f.model_name_from_title("[内购无水印] 鱼子酱Fish 秀人网模特 惊红之舞")[0] \
        == "鱼子酱Fish"
    assert f.model_name_from_title("[AIGirl] 芭喜mila 0916")[0] == "芭喜mila"
    assert f.model_name_from_title("[LE] LEHC-037 Min.E")[0] == "Min.E"


def test_titlemodel_rejects_series_names():
    f = __import__("app.services.harvest.titlemodel", fromlist=["model_name_from_title"])
    assert f.model_name_from_title("[JP] BLT MONSTER Round 8") == ("", "")
    assert f.model_name_from_title("[JP] 別冊SPA! 旬撮GIRL Vol.25") == ("", "")


# ---- 镜像容错:MediaFire 死链 → terabox 备份(2026-10-23 任务 707) ----------

class _FakeTB2:
    """terabox 解析打桩(与 _2 号用例同形,单独一份免互相牵连)。"""

    @staticmethod
    def load_cookie_header(path):
        assert path
        return "ndus=x"

    @staticmethod
    def _share_page_token(hdr, surl):
        return "tok"

    @staticmethod
    def _shorturlinfo(hdr, surl, tok, ref):
        return {"errno": 0, "shareid": 1, "uk": 2, "sign": "s", "timestamp": 3,
                "list": [{"isdir": "0", "fs_id": 77,
                          "server_filename": "Coser@Hane Ame - 早期白皮合集.rar",
                          "size": 599003486, "md5": "630a77c7"}]}

    @staticmethod
    def _flatten(hdr, surl, tok, ref, entries):
        return entries


def _patch_tb2(monkeypatch):
    monkeypatch.setattr(worker.terabox, "load_cookie_header", _FakeTB2.load_cookie_header)
    monkeypatch.setattr(worker.terabox, "_share_page_token", _FakeTB2._share_page_token)
    monkeypatch.setattr(worker.terabox, "_shorturlinfo", _FakeTB2._shorturlinfo)
    monkeypatch.setattr(worker.terabox, "_flatten", _FakeTB2._flatten)


MF_DEAD = "https://www.mediafire.com/error.php?errno=378&quickkey=9jl0q201vahwb25"
TB_MIRROR = "https://www.terabox.app/sharing/link?surl=PbnyWjeMu5R3QvEEVVemAg"


def _fake_finish(monkeypatch):
    """_finish 打到假 job 上,返回记录 dict。"""
    class FakeJob:
        serial = 999998
        def __init__(self):
            self.status = ""
            self.error = None
    job = FakeJob()
    rec = {}

    def fake_finish(s, j, status, error=None):
        j.status = status
        j.error = error
        rec["status"] = status
        rec["error"] = error
    monkeypatch.setattr(worker, "_finish", fake_finish)
    return job, rec


def test_resolve_infos_mediafire_dead_falls_back_to_terabox(monkeypatch):
    """第一条 ouo 落地 MediaFire 错误页、第二条是 TeraBox 备份 → 走 TeraBox。

    707 实录:详情页挂 omuODmK(MediaFire, 已下架) 与 RFzVQAV(TeraBox 备份)。
    以前第一条一失败就整任务判死,备份白放着。
    """
    def fake_resolve(link):
        if "omuODmK" in link:
            raise net.MediaFireDeadError("MediaFire 文件已被下架(违规或上传者删除)(errno=378)",
                                         MF_DEAD)
        raise net.UnsupportedHostError("TeraBox", TB_MIRROR)

    monkeypatch.setattr(net, "resolve_ouo", fake_resolve)
    _patch_tb2(monkeypatch)
    job, rec = _fake_finish(monkeypatch)
    with mock.patch.object(worker.settings_store, "harvest_conf",
                           return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(_FakeSession(), job,
                                      _target(["https://ouo.io/omuODmK",
                                               "https://ouo.io/RFzVQAV"]))
    assert infos, rec
    assert infos[0]["filename"].endswith(".rar")
    assert infos[0]["size"] == 599003486
    assert infos[0]["terabox"]["surl"] == "PbnyWjeMu5R3QvEEVVemAg"
    assert "status" not in rec  # 没落失败终态


def test_resolve_infos_uses_backup_shortlink_when_mediafire_dead(monkeypatch):
    """锚文本标 TeraBox 的备用短链:主链下架时被启用(707 的真实形态)。

    解析器按锚文本把 non-mediafire 的链收进 backup_shortlinks —— 老逻辑
    直接把它们丢掉,于是备份链永远没机会被用。
    """
    def fake_resolve(link):
        if "omuODmK" in link:
            raise net.MediaFireDeadError("MediaFire 文件已被下架(违规或上传者删除)(errno=378)",
                                         MF_DEAD)
        raise net.UnsupportedHostError("TeraBox", TB_MIRROR)

    monkeypatch.setattr(net, "resolve_ouo", fake_resolve)
    _patch_tb2(monkeypatch)
    job, rec = _fake_finish(monkeypatch)
    target = _target(["https://ouo.io/omuODmK"])
    target.backup_shortlinks = ["https://ouo.io/RFzVQAV"]
    with mock.patch.object(worker.settings_store, "harvest_conf",
                           return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(_FakeSession(), job, target)
    assert infos, rec
    assert infos[0]["terabox"]["surl"] == "PbnyWjeMu5R3QvEEVVemAg"
    assert "status" not in rec


def test_resolve_infos_backup_not_touched_when_mediafire_ok(monkeypatch):
    """主链好使时绝不解析备用链(省掉一次 30-50s 的 ouo 解析)。"""
    seen = []

    def fake_resolve(link):
        seen.append(link)
        return "https://www.mediafire.com/file/abc/x.rar/file"

    monkeypatch.setattr(net, "resolve_ouo", fake_resolve)
    monkeypatch.setattr(net, "mediafire_info_from_url",
                        lambda page_url, **kw: {"quick_key": "k", "direct_url": "http://d",
                                                "size": 1, "sha256": "",
                                                "filename": "x.rar"})
    target = _target(["https://ouo.io/main1"])
    target.backup_shortlinks = ["https://ouo.io/backup1"]
    infos = worker._resolve_infos(_FakeSession(), None, target)
    assert infos and infos[0]["filename"] == "x.rar"
    assert seen == ["https://ouo.io/main1"], seen


def test_resolve_infos_mediafire_dead_without_backup_reports_reason(monkeypatch):
    """MediaFire 下架且无备份 → 报「已被下架(errno=378)」,不是含糊的解析失败。"""
    monkeypatch.setattr(net, "resolve_ouo",
                        lambda link, **kw: (_ for _ in ()).throw(
                            net.MediaFireDeadError(
                                "MediaFire 文件已被下架(违规或上传者删除)(errno=378)",
                                MF_DEAD)))
    job, rec = _fake_finish(monkeypatch)
    infos = worker._resolve_infos(_FakeSession(), job, _target(["https://ouo.io/omuODmK"]))
    assert infos is None
    assert rec["status"] == "failed"
    assert "下架" in rec["error"] and "errno=378" in rec["error"]


def test_resolve_infos_discards_partial_volumes(monkeypatch):
    """分卷只拿到一部分、另一条镜像死掉 → 整批判失败,且关掉已开会话(不混下)。"""
    class FakeSess:
        closed = False
        def close(self):
            FakeSess.closed = True

    def fake_resolve(link):
        if "vol2" in link:
            raise net.MediaFireDeadError("MediaFire 文件已被下架(errno=378)", MF_DEAD)
        return "https://www.mediafire.com/file/abc/f.part1.rar/file"

    monkeypatch.setattr(net, "resolve_ouo", fake_resolve)
    monkeypatch.setattr(net, "mediafire_info_from_url",
                        lambda page_url, **kw: {"quick_key": "k", "direct_url": "http://d",
                                                "size": 10, "sha256": "",
                                                "filename": "f.part1.rar",
                                                "_session": FakeSess()})
    job, rec = _fake_finish(monkeypatch)
    infos = worker._resolve_infos(_FakeSession(), job,
                                  _target(["https://ouo.io/vol1", "https://ouo.io/vol2"]))
    assert infos is None
    assert rec["status"] == "failed"
    assert "下架" in rec["error"]
    assert FakeSess.closed, "残缺分卷的页面会话必须关掉"


# ---- 760: MediaFire 页面异常 + 直挂 TeraBox 备份 -----------------------------

TB_DIRECT = "https://terabox.com/s/1Y96hEf0OjWQO_yOyS_6qTg"


def test_resolve_infos_mf_page_error_falls_back_to_direct_terabox(monkeypatch):
    """760 实录:MF 页面回 HTTP 400(RuntimeError 穿透) + 同页直挂 TeraBox
    备份 → 整包改走 TeraBox,不判死。

    修复前三处一起坑:直挂 terabox 链接解析器没收;MF 的 RuntimeError 不是
    MediaFireDeadError,直接穿透 _resolve_infos;于是「文件两个源都完好」
    的任务被记成 failed。
    """
    monkeypatch.setattr(net, "resolve_ouo",
                        lambda link, **kw: "https://www.mediafire.com/file/6g0gnjr4z5gjjbp/x.rar/file")

    def boom(page_url, **kw):
        raise RuntimeError("MediaFire 页面取不到(HTTP 400): https://www.mediafire.com/file/…")

    monkeypatch.setattr(net, "mediafire_info_from_url", boom)
    _patch_tb2(monkeypatch)
    job, rec = _fake_finish(monkeypatch)
    with mock.patch.object(worker.settings_store, "harvest_conf",
                           return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(_FakeSession(), job,
                                      _target(["https://ouo.io/oL053g", TB_DIRECT]))
    assert infos, rec
    assert infos[0]["terabox"]["surl"] == "1Y96hEf0OjWQO_yOyS_6qTg"
    assert "status" not in rec


def test_resolve_infos_mf_page_error_reported_not_raised(monkeypatch):
    """MF 页面异常(非 DeadError)在无备份时按失败收口:报错文案落库,异常不再
    穿透 _resolve_infos(以前会一路冒到 _run_job,连 failed 文案都没有)。"""
    monkeypatch.setattr(net, "resolve_ouo",
                        lambda link, **kw: "https://www.mediafire.com/file/bad1/x.rar/file")

    def fake_mf_info(page_url, **kw):
        raise RuntimeError("MediaFire 页面取不到(HTTP 400): https://www.mediafire.com/file/bad1/")

    monkeypatch.setattr(net, "mediafire_info_from_url", fake_mf_info)
    job, rec = _fake_finish(monkeypatch)
    infos = worker._resolve_infos(_FakeSession(), job, _target(["https://ouo.io/bad"]))
    assert infos is None
    assert rec["status"] == "failed"
    assert "HTTP 400" in rec["error"]


def test_resolve_infos_direct_terabox_link_in_backup_list(monkeypatch):
    """备用清单里放直挂 terabox 链接(非 ouo)→ 直接归到 TeraBox 分支,
    不会当成 MediaFire 页面去解析(以前会撞 "无法提取 quick_key")。"""
    monkeypatch.setattr(net, "resolve_ouo",
                        lambda link, **kw: (_ for _ in ()).throw(
                            net.MediaFireDeadError("MediaFire 文件已被下架(errno=378)",
                                                   MF_DEAD)))

    def no_mf(page_url, **kw):
        raise AssertionError(f"不该把 terabox 链接当 MediaFire 页面: {page_url}")

    monkeypatch.setattr(net, "mediafire_info_from_url", no_mf)
    _patch_tb2(monkeypatch)
    job, rec = _fake_finish(monkeypatch)
    target = _target(["https://ouo.io/omuODmK"])
    target.backup_shortlinks = [TB_DIRECT]
    with mock.patch.object(worker.settings_store, "harvest_conf",
                           return_value={"harvest.terabox_cookie_file": "/tmp/c.txt"}):
        infos = worker._resolve_infos(_FakeSession(), job, target)
    assert infos, rec
    assert infos[0]["terabox"]["surl"] == "1Y96hEf0OjWQO_yOyS_6qTg"


def test_misskon_direct_terabox_collected_from_real_page_shape():
    """760 详情页的真实形态:ouo(MF) + 直挂 terabox.com/s/… —— 两条都收。"""
    html = """
    <h1 class="name post-title entry-title">[JP] M: T (79 photos)</h1>
    <div class="entry">
      <p><a href="https://ouo.io/oL053g" class="shortc-button">Download link: MediaFire</a></p>
      <p><a href="https://terabox.com/s/1Y96hEf0OjWQO_yOyS_6qTg">Download link: Terabox</a></p>
    </div>
    """
    t = net.parse_misskon_detail_page(
        "https://misskon.com/120000-jp-m-79-photos/", existing_html=html)
    assert t.shortlinks == ["https://ouo.io/oL053g", TB_DIRECT]
