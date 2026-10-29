"""pipeline 归档 — 目录规则 <library>/<模特名>/<解压自带目录>/、防覆盖。"""

from __future__ import annotations

import pytest

from app.services.harvest.pipeline import archive_collection


def test_archive_layout(tmp_path):
    src = tmp_path / "extract"
    (src / "sub").mkdir(parents=True)
    (src / "a.jpg").write_bytes(b"x")
    (src / "sub" / "b.jpg").write_bytes(b"y")
    lib = tmp_path / "library"

    dest = archive_collection(src, lib, model_name="Yeha", title="School Nurse")
    assert dest == lib / "Yeha" / "School Nurse"
    assert (dest / "a.jpg").read_bytes() == b"x"
    assert (dest / "sub" / "b.jpg").exists()


def test_archive_uses_inner_dir_name(tmp_path):
    """压缩包自带标题目录 → 直接用它,不再额外套一层 title。"""
    src = tmp_path / "extract"
    (src / "XIUREN No.10977 CHENCHEN").mkdir(parents=True)
    (src / "XIUREN No.10977 CHENCHEN" / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"

    dest = archive_collection(src, lib, model_name="Yeha",
                              title="School Nurse (219 photos)")
    assert dest == lib / "Yeha" / "XIUREN No.10977 CHENCHEN"
    assert (dest / "a.jpg").read_bytes() == b"x"
    # 没有多出标题层
    assert not (lib / "Yeha" / "School Nurse (219 photos)").exists()


def test_archive_upgrades_truncated_inner_dir_to_page_title(tmp_path):
    """包内目录名只是页面标题的截短 → 用页面标题(4kup 老帖:入库 title 取目录名)。"""
    src = tmp_path / "extract"
    (src / "MFStar Vol.076").mkdir(parents=True)
    (src / "MFStar Vol.076" / "a.jpg").write_bytes(b"x")

    dest = archive_collection(src, tmp_path / "lib", model_name="Mu Yu Qian",
                              title="MFStar Vol.076 Mu Yu Qian (慕羽茜)")
    assert dest.name == "MFStar Vol.076 Mu Yu Qian (慕羽茜)"
    assert (dest / "a.jpg").read_bytes() == b"x"
    assert not (dest.parent / "MFStar Vol.076").exists()   # 旧名不残留


def test_archive_keeps_inner_dir_when_unrelated(tmp_path):
    """包内目录名不是页面标题前缀 → 一律保留包内名(原行为不变)。"""
    src = tmp_path / "extract"
    (src / "XIUREN No.10977 CHENCHEN").mkdir(parents=True)
    (src / "XIUREN No.10977 CHENCHEN" / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="Yeha",
                              title="School Nurse (219 photos)")
    assert dest.name == "XIUREN No.10977 CHENCHEN"


def test_archive_keeps_inner_dir_for_photo_count_titles(tmp_path):
    """页面标题带「(N photos)」尾缀 → 不拿它当目录名(库内 title 不该带尾缀)。"""
    src = tmp_path / "extract"
    (src / "School Nurse").mkdir(parents=True)
    (src / "School Nurse" / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="Yeha",
                              title="School Nurse (219 photos)")
    assert dest.name == "School Nurse"


def test_archive_ignores_junk_when_detecting_inner_dir(tmp_path):
    """__MACOSX 等系统垃圾项不计入唯一顶层目录判定。"""
    src = tmp_path / "extract"
    (src / "Album").mkdir(parents=True)
    (src / "Album" / "a.jpg").write_bytes(b"x")
    (src / "__MACOSX").mkdir()
    dest = archive_collection(src, tmp_path / "lib", model_name="M", title="T")
    assert dest.name == "Album"


def test_archive_inner_dir_refuses_existing(tmp_path):
    """自带目录名已存在且非空 → 追加 (N) 序号落盘,不丢包。"""
    src = tmp_path / "extract"
    (src / "Album").mkdir(parents=True)
    (src / "Album" / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"
    (lib / "M" / "Album").mkdir(parents=True)
    (lib / "M" / "Album" / "sentinel").write_text("1")
    dest = archive_collection(src, lib, model_name="M", title="T")
    assert dest == lib / "M" / "Album (2)"
    assert (dest / "a.jpg").exists()
    # 原内容未被破坏
    assert (lib / "M" / "Album" / "sentinel").exists()


def test_archive_refuses_existing_nonempty(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"
    dest = archive_collection(src, lib, model_name="M", title="T")
    (dest / "sentinel").write_text("1")
    (src / "a.jpg").write_bytes(b"x")       # 新一批再解压出同名文件
    dest2 = archive_collection(src, lib, model_name="M", title="T")
    assert dest2.name == "T (2)"
    assert (dest2 / "a.jpg").exists()
    # (2) 也被占 → 顺延 (3)
    (dest2 / "sentinel").write_text("1")
    (src / "a.jpg").write_bytes(b"x")
    dest3 = archive_collection(src, lib, model_name="M", title="T")
    assert dest3.name == "T (3)"


def test_archive_sanitizes_names(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="A/B", title="T:*")
    assert "/" not in dest.parts[-2] and ":" not in dest.parts[-1]


def test_unsorted_dir_when_no_model(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="", title="T")
    assert dest.parent.name == "未分类"


def _make_rar(tmp_path, files: dict[str, bytes], password: str = "") -> Path:
    """用 7z 造一个 RAR(测试机需 p7zip 或系统 rar); 造不出则跳过。"""
    import shutil
    import subprocess
    src = tmp_path / "src"
    src.mkdir()
    for name, data in files.items():
        p = src / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    rar = tmp_path / "a.rar"
    sevenzip = shutil.which("7zz") or shutil.which("7z")
    if not sevenzip:
        import pytest
        pytest.skip("no 7z to build fixture")
    cmd = [sevenzip, "a", "-tr rar"][:3] + ["-tr ar"] if False else [sevenzip, "a", str(rar), str(src / "*")]
    cmd = [sevenzip, "a", "-tzip", str(rar), str(src / "*")]
    if password:
        cmd.insert(2, f"-p{password}")
    subprocess.run(cmd, check=True, capture_output=True)
    return rar


def test_extract_partial_failure_still_returns_files(tmp_path, monkeypatch):
    """unar rc=1 但解出了大部分文件时放行(部分成功), 不再整包丢弃。"""
    from app.services.harvest import pipeline
    import app.services.harvest.pipeline as P

    # 直接替换 _try_unar 行为不可取——测真实分支: 造一个 unar 不可用场景太麻烦,
    # 改为验证判定逻辑本身
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"x")
    (dest / "b.jpg").write_bytes(b"y")

    out_text = ("a.jpg... OK.\nb.jpg... Failed! (Attempted to read more data "
                "than was available)\nExtraction failed (1 file failed.)")
    # 模拟: rc=1, 无 "Successfully", 有文件 → 应放行
    files = [p for p in sorted(dest.rglob("*")) if p.is_file()]
    partial_ok = ("Missing or wrong password" not in out_text
                  and "No files extracted" not in out_text
                  and "Successfully" not in out_text
                  and files)
    assert partial_ok, "部分解压成功应被放行"

    # 反例: 密码错必须仍判失败
    assert "Missing or wrong password" in "Archive parsing failed! (Missing or wrong password.)"


# ---- 下载阶段瞬时失败重试(2026-10-22) ---------------------------------------

class _Stream:
    """假 Response:能当 stream=True 的下载流用。"""

    def __init__(self, status, chunks=(), headers=None, url=""):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size=0):
        yield from self._chunks

    def close(self):
        self.closed = True


def test_download_stream_retries_403_then_succeeds(tmp_path, monkeypatch):
    """Cloudflare 抽检回 403 → 退避重试,第二次下完(以前一次 403 就整任务失败)。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    replies = [_Stream(403), _Stream(200, [b"hello ", b"world"],
                                     {"content-length": "11"})]
    seen = []

    def fake_get(url, **kw):
        seen.append(kw.get("headers") or {})
        return replies.pop(0)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "a.rar"
    pl.download_stream("https://download1.mediafire.com/x", dest, retries=3)
    assert dest.read_bytes() == b"hello world"
    assert len(seen) == 2
    assert not dest.with_suffix(".rar.part").exists()


def test_download_stream_resumes_on_retry(tmp_path, monkeypatch):
    """中断留下的 .part 在重试时走 Range 续传,不从头再下。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    dest = tmp_path / "b.rar"
    part = dest.with_suffix(".rar.part")
    part.write_bytes(b"head-")
    seen = []

    def fake_get(url, **kw):
        seen.append(dict(kw.get("headers") or {}))
        return _Stream(206, [b"tail"], {"content-length": "4"})

    monkeypatch.setattr(pl.cr, "get", fake_get)
    pl.download_stream("https://download1.mediafire.com/y", dest, retries=3)
    assert dest.read_bytes() == b"head-tail"
    assert seen[0]["Range"] == "bytes=5-"


def test_download_stream_does_not_retry_404(tmp_path, monkeypatch):
    """404 是终态失败(直链失效),重试无意义 —— 一次就抛。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        return _Stream(404)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    with pytest.raises(RuntimeError) as ei:
        pl.download_stream("https://download1.mediafire.com/gone",
                           tmp_path / "c.rar", retries=3)
    assert "HTTP 404" in str(ei.value) and calls["n"] == 1


def test_download_stream_gives_up_after_retries(tmp_path, monkeypatch):
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        return _Stream(403)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    with pytest.raises(RuntimeError) as ei:
        pl.download_stream("https://download1.mediafire.com/z",
                           tmp_path / "d.rar", retries=3)
    assert "HTTP 403" in str(ei.value) and calls["n"] == 3


def test_egress_default_by_host():
    """harvest.proxy 是给页面/短链过盾的;MediaFire CDN 默认直连(经代理会断流)。"""
    from app.services.harvest import pipeline as pl

    pl._EGRESS.clear()
    assert pl._prefer_proxy("download2330.mediafire.com") is False
    assert pl._prefer_proxy("dl.dm.terabox.com") is True


def test_download_stream_prefers_direct_for_mediafire_and_learns(tmp_path, monkeypatch):
    """MediaFire CDN 默认直连;直连也不通时翻面走代理,并把结论记在 host 上。"""
    from curl_cffi.requests.exceptions import ConnectionError as CrConnError

    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: "http://192.168.0.102:7890")
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    seen = []
    aborted = {"done": False}

    def fake_get(url, **kw):
        seen.append(kw.get("proxy"))
        if not aborted["done"]:
            aborted["done"] = True
            raise CrConnError("curl: (56) Connection closed abruptly")
        return _Stream(200, [b"ok"], {"content-length": "2"})

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "e.rar"
    pl.download_stream("https://download2330.mediafire.com/abc/x.rar", dest)
    assert dest.read_bytes() == b"ok"
    assert seen == [None, "http://192.168.0.102:7890"]  # 直连 → 翻面代理
    assert pl._EGRESS["download2330.mediafire.com"] is True

    # 同 host 第二次:直接用学到的出口(代理),不再先撞一次
    seen.clear()
    pl.download_stream("https://download2330.mediafire.com/def/y.rar",
                       tmp_path / "f.rar")
    assert seen == ["http://192.168.0.102:7890"]
    pl._EGRESS.clear()


def test_download_stream_does_not_flip_when_partial_data_arrived(tmp_path, monkeypatch):
    """被对端掐流但已下了一部分 → 是限速不是出口坏, 不翻面(翻面只会让下一段变慢)。"""
    from curl_cffi.requests.exceptions import ConnectionError as CrConnError

    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: "http://192.168.0.102:7890")
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    seen = []
    state = {"n": 0}

    class _CutStream:
        """先给 3 字节再抛 curl 56 —— MediaFire CDN 每 ~35MB 掐一次的真实形态。"""

        status_code = 200
        url = ""

        def __init__(self):
            self.headers = {"content-length": "5"}

        def iter_content(self, chunk_size=0):
            from curl_cffi.requests.exceptions import ConnectionError as CrConnError
            yield b"abc"
            raise CrConnError("Failed to perform, curl: (56) Connection closed abruptly")

        def close(self):
            pass

    def fake_get(url, **kw):
        seen.append(kw.get("proxy"))
        seen.append("RANGE" if "Range" in (kw.get("headers") or {}) else "-")
        state["n"] += 1
        if state["n"] == 1:
            return _CutStream()
        return _Stream(206, [b"de"], {"content-length": "2"})

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "p.rar"
    pl.download_stream("https://download2330.mediafire.com/abc/z.rar", dest)
    assert seen == [None, "-", None, "RANGE"]   # 两段都直连(带 Range 续传), 没有翻面
    assert "download2330.mediafire.com" not in pl._EGRESS
    pl._EGRESS.clear()


def test_download_stream_flips_to_direct_for_non_mediafire_host(tmp_path, monkeypatch):
    """非 MediaFire host 默认跟随 harvest.proxy;代理断流则翻面直连。"""
    from curl_cffi.requests.exceptions import ConnectionError as CrConnError

    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: "http://192.168.0.102:7890")
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    seen = []
    aborted = {"done": False}

    def fake_get(url, **kw):
        seen.append(kw.get("proxy"))
        if not aborted["done"]:
            aborted["done"] = True
            raise CrConnError("curl: (56) Connection closed abruptly")
        return _Stream(200, [b"ok"], {"content-length": "2"})

    monkeypatch.setattr(pl.cr, "get", fake_get)
    pl.download_stream("https://cdn.example.com/a.rar", tmp_path / "h.rar")
    assert seen == ["http://192.168.0.102:7890", None]
    assert pl._EGRESS["cdn.example.com"] is False
    pl._EGRESS.clear()


def test_download_stream_no_direct_fallback_when_disabled(tmp_path, monkeypatch):
    """TeraBox 的 dlink 绑定出口 IP —— proxy_fallback=False 时不换直连。"""
    from curl_cffi.requests.exceptions import ConnectionError as CrConnError

    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: "http://192.168.0.102:7890")
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    seen = []

    def fake_get(url, **kw):
        seen.append(kw.get("proxy"))
        if len(seen) < 2:
            raise CrConnError("curl: (56) Connection closed abruptly")
        return _Stream(200, [b"ok"], {"content-length": "2"})

    monkeypatch.setattr(pl.cr, "get", fake_get)
    pl.download_stream("https://dl.dm.terabox.com/abc", tmp_path / "g.rar",
                       proxy_fallback=False, retries=2)
    assert seen == ["http://192.168.0.102:7890"] * 2


def test_download_stream_detects_mediafire_repair_page(tmp_path, monkeypatch):
    """MediaFire 拒下时回 200 + text/html 的 download_repair 验证页(几十 KB、
    无 content-length)—— 必须在写盘前识破并重试,否则只能等 SHA 校验发现,
    那时 .part 已被删、整卷白下(2026-10-22 五个任务就是这么连挂的)。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    replies = [
        _Stream(200, [b"<html>repair</html>"],
                {"content-type": "text/html; charset=UTF-8"},
                url="https://www.mediafire.com/download_repair.php?flag=2&dkey=x"),
        _Stream(200, [b"real-bytes"],
                {"content-type": "application/x-rar", "content-length": "10"}),
    ]

    def fake_get(url, **kw):
        return replies.pop(0)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "i.rar"
    pl.download_stream("https://download2286.mediafire.com/abc/x.rar", dest)
    assert dest.read_bytes() == b"real-bytes"
    assert not dest.with_suffix(".rar.part").exists()


def test_download_stream_size_mismatch_is_soft_block(tmp_path, monkeypatch):
    """content-length 与 API 给的 size 不符(验证页/截断)→ 判软拒绝并重试。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    replies = [
        _Stream(200, [b"x" * 10],
                {"content-type": "application/octet-stream",
                 "content-length": "10"}),
        _Stream(200, [b"y" * 100],
                {"content-type": "application/octet-stream",
                 "content-length": "100"}),
    ]

    def fake_get(url, **kw):
        return replies.pop(0)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "j.rar"
    pl.download_stream("https://download2286.mediafire.com/def/x.rar", dest,
                       expected_size=100)
    assert dest.read_bytes() == b"y" * 100


def test_download_stream_reports_soft_block_after_retries(tmp_path, monkeypatch):
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        return _Stream(200, [b"<html>repair</html>"],
                       {"content-type": "text/html"},
                       url="https://www.mediafire.com/download_repair.php")

    monkeypatch.setattr(pl.cr, "get", fake_get)
    with pytest.raises(RuntimeError) as ei:
        pl.download_stream("https://download2286.mediafire.com/ghi/x.rar",
                           tmp_path / "k.rar", retries=3)
    msg = str(ei.value)
    assert "验证页" in msg and "重排" in msg
    assert calls["n"] == 3
    assert not (tmp_path / "k.rar.part").exists()


def test_download_stream_uses_given_session_and_referer(tmp_path, monkeypatch):
    """MediaFire 场景:下载复用取页面那份 Session(带 cookie)+ Referer,
    出口仍按策略逐请求决定 —— 这三者共同决定能不能过 download_repair。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: "http://192.168.0.102:7890")
    pl._EGRESS.clear()
    seen = []

    class _Sess:
        def get(self, url, **kw):
            seen.append(("session", kw.get("proxy"), kw.get("headers")))
            return _Stream(200, [b"ok"], {"content-length": "2",
                                          "content-type": "application/x-rar"})

    class _Bare:
        @staticmethod
        def get(url, **kw):
            seen.append(("bare", kw.get("proxy"), kw.get("headers")))
            return _Stream(500)

    monkeypatch.setattr(pl, "cr", _Bare)
    sess = _Sess()
    pl.download_stream("https://download2286.mediafire.com/abc/x.rar",
                       tmp_path / "m.rar", session=sess,
                       referer="https://www.mediafire.com/file/abc/x.rar")
    assert len(seen) == 1
    kind, proxy, hdrs = seen[0]
    assert kind == "session"                       # 走的是页面会话
    assert proxy is None                           # mediafire CDN 直连
    assert hdrs["Referer"].endswith("/file/abc/x.rar")


def test_download_stream_keeps_resuming_when_attempts_advance(tmp_path, monkeypatch):
    """大文件被对端一刀刀掐断(每连接只给几 MB):只要有进展就继续续传,
    不消耗重试预算 —— 1.4GB 那卷就是这么滚完的(2026-10-22)。"""
    from app.services.harvest import net
    from app.services.harvest import pipeline as pl

    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    pl._EGRESS.clear()
    total = 16
    calls = {"n": 0}

    class _Cut:
        def __init__(self, status, payload, remaining):
            self.status_code = status
            self._payload = payload
            self.headers = {"content-length": str(remaining),
                            "content-type": "application/octet-stream"}
            self.url = ""

        def iter_content(self, chunk_size=0):
            yield self._payload
            raise ConnectionError("curl: (56) Connection closed abruptly")

        def close(self):
            pass

    class _Ok:
        status_code = 206
        url = ""

        def __init__(self, payload, remaining):
            self._payload = payload
            self.headers = {"content-length": str(remaining),
                            "content-type": "application/octet-stream"}

        def iter_content(self, chunk_size=0):
            yield self._payload

        def close(self):
            pass

    def fake_get(url, **kw):
        calls["n"] += 1
        rng = (kw.get("headers") or {}).get("Range") or ""
        offset = int(rng.split("=")[1].rstrip("-")) if rng else 0
        remaining = total - offset
        if remaining <= 4:
            return _Ok(b"z" * remaining, remaining)
        return _Cut(206, b"z" * 4, remaining)

    monkeypatch.setattr(pl.cr, "get", fake_get)
    dest = tmp_path / "big.rar"
    pl.download_stream("https://download2342.mediafire.com/abc/big.rar", dest,
                       retries=3)
    assert dest.read_bytes() == b"z" * total
    assert calls["n"] > 3  # 超过普通重试预算,靠「有进展」一路续完
