"""缩略图服务 — URL 解析、缓存命中、路径安全。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.media import PREHEAT_WIDTHS, THUMB_RE, thumb_url


def test_thumb_url_width_only():
    assert thumb_url("demo/x/abc.jpg", 900) == "/t/900/demo/x/abc.jpg.webp"


def test_thumb_url_width_height():
    assert thumb_url("demo/x/abc.jpg", 300, 400) == "/t/300x400/demo/x/abc.jpg.webp"


def test_thumb_url_none_placeholder():
    assert thumb_url(None, 900).startswith("data:image/gif")


def test_lightbox_display_tier_is_preheated():
    """灯箱显示档必须落在后端预热的档位里。

    两者曾各自演化: 前端按屏宽取 1800/2400, 后端只预热 900/1800 —— 于是
    1440px 以上的桌面每一次开灯箱都打在未预热的 2400 上, 服务端现场解码
    230~900ms, 还连带把同进程的其他请求一起卡住。"""
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "app.js").read_text("utf-8")
    m = re.search(r"var LB_W = (\d+);", js)
    assert m, "app.js 里找不到灯箱档位常量 LB_W"
    assert int(m.group(1)) in PREHEAT_WIDTHS


def test_thumb_re_width_only():
    m = THUMB_RE.match("900/demo/x/abc.jpg")
    assert m and m.group(1) == "900" and m.group(2) is None and m.group(3) == "demo/x/abc"


def test_thumb_re_width_height():
    m = THUMB_RE.match("300x400/demo/x/abc.jpg")
    assert m and m.group(1) == "300" and m.group(2) == "400"


def test_thumb_re_rejects_garbage():
    assert THUMB_RE.match("abc/demo/x.jpg") is None
    assert THUMB_RE.match("900/demo/x.gif") is None


def test_thumbnail_served_and_cached(admin_client):
    url = thumb_url("demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg", 300)
    r1 = admin_client.get(url)
    assert r1.status_code == 200 and r1.headers["content-type"] == "image/webp"
    r2 = admin_client.get(url)  # 第二次走缓存文件
    assert r2.status_code == 200 and r2.headers["content-type"] == "image/webp"


def test_thumbnail_missing_source_404(admin_client):
    assert admin_client.get("/t/300/demo/nope/none.jpg.webp").status_code == 404


# ---- 预热巡检：热启动零停顿，冷启动照常节流 ----

@pytest.fixture
def clean_preheat_event():
    """其他测试的 TestClient 关闭时 lifespan 会 set 停机事件，先清干净。"""
    from app.services import media
    media._preheat_done.clear()
    yield
    media._preheat_done.clear()


def test_preheat_zero_pause_when_cache_hits(monkeypatch, clean_preheat_event):
    """缓存全部命中时预热循环不应睡眠（热重启几秒内巡完）。"""
    import time
    from app.services import media

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    calls: list[str] = []

    def fake_ensure(rel, w, h=None, q=None):
        calls.append(rel)
        return False  # 全命中缓存

    monkeypatch.setattr(media, "ensure_cached", fake_ensure)
    monkeypatch.setattr(media, "_load_libc", lambda: None)

    done, generated = media._preheat_files(["a.jpg", "b.jpg", "c.jpg"], batch=1)

    assert done == 3
    assert generated == 0
    assert len(calls) == 6      # 3 张 × 2 档
    assert sleeps == []         # 全命中 → 零睡眠


def test_preheat_pauses_when_generating(monkeypatch, clean_preheat_event):
    """实际生成缩略图时保留原有节流睡眠。"""
    import time
    from app.services import media

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    calls: list[str] = []

    def fake_ensure(rel, w, h=None, q=None):
        calls.append(rel)
        return True  # 每档都真生成

    monkeypatch.setattr(media, "ensure_cached", fake_ensure)
    monkeypatch.setattr(media, "_load_libc", lambda: None)

    done, generated = media._preheat_files(["a.jpg", "b.jpg"], batch=4)

    assert done == 2
    assert generated == 4            # 2 张 × 2 档
    assert len(calls) == 4
    assert sleeps == [media._preheat_gap] * 2  # 每张都节流


def test_preheat_stops_on_shutdown_event(monkeypatch, clean_preheat_event):
    """停机事件置位后巡检提前退出。"""
    import time
    from app.services import media

    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(media, "ensure_cached", lambda rel, w, h=None, q=None: False)
    monkeypatch.setattr(media, "_load_libc", lambda: None)

    media._preheat_done.set()
    try:
        done, generated = media._preheat_files(["a.jpg", "b.jpg"], batch=1)
        assert (done, generated) == (0, 0)  # 第一张之前就退出
    finally:
        media._preheat_done.clear()


# ---- 截断图宽容解码 ----

def _make_jpeg(tmp_path, w=60, h=80, quality=90):
    """生成一张真 JPEG, 供截断实验用。"""
    import io
    from PIL import Image
    im = Image.new("RGB", (w, h), (180, 60, 60))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    p = tmp_path / "trunc.jpg"
    p.write_bytes(buf.getvalue())
    return p


def test_truncated_jpeg_thumbnail_served(admin_client, tmp_path, monkeypatch):
    """截断(缺尾部 EOI)的 JPEG: 宽容重试后仍能出图, 不再 500。

    图像数据本体完整、仅尾部缺十几个字节的坏图, 是采集包里的真实案例。"""
    from app.services import media

    src = _make_jpeg(tmp_path)
    data = src.read_bytes()
    truncated = tmp_path / "broken.jpg"
    truncated.write_bytes(data[:-64])  # 掐掉尾部 64 字节(小图要掐进扫描数据才触发截断错误)

    # 确认严格解码确实失败(否则本测试没测到目标场景)
    with pytest.raises(Exception):
        im = media.Image.open(truncated)
        im.load()  # open 是惰性的, 不 load 不解码

    rel = "demo/x/broken.jpg"
    dest = media.settings.media_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(truncated.read_bytes())
    try:
        r = admin_client.get(media.thumb_url(rel, 32))
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
        assert media._cache_path(32, None, 78, rel).is_file()  # 缓存已写出
    finally:
        dest.unlink(missing_ok=True)
        media._cache_path(32, None, 78, rel).unlink(missing_ok=True)


def test_garbage_file_still_500(admin_client, tmp_path):
    """彻底的垃圾文件(宽容模式也解不开)依旧报错, 不静默。"""
    from app.services import media

    rel = "demo/x/garbage.jpg"
    dest = media.settings.media_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"this is not an image at all")
    try:
        r = admin_client.get(media.thumb_url(rel, 32))
        assert r.status_code == 500
        assert not media._cache_path(32, None, 78, rel).is_file()
    finally:
        dest.unlink(missing_ok=True)
