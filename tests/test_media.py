"""缩略图服务 — URL 解析、缓存命中、路径安全。"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from PIL import Image

from app.services.media import (
    PREHEAT_SHORT,
    PREHEAT_WIDTHS,
    THUMB_RE,
    thumb_url,
)


def test_thumb_url_width_only():
    assert thumb_url("demo/x/abc.jpg", 900) == "/t/900/demo/x/abc.jpg.webp"


def test_thumb_url_width_height():
    assert thumb_url("demo/x/abc.jpg", 300, 400) == "/t/300x400/demo/x/abc.jpg.webp"


def test_thumb_url_short_side():
    assert thumb_url("demo/x/abc.jpg", 2400, short=True) == "/t/s2400/demo/x/abc.jpg.webp"


def test_thumb_url_none_placeholder():
    assert thumb_url(None, 900).startswith("data:image/gif")


def test_lightbox_display_tier_is_preheated():
    """灯箱显示档必须落在后端预热的档位里,且用短边语义。

    两者曾各自演化: 前端按屏宽取 1800/2400, 后端只预热 900/1800 —— 于是
    1440px 以上的桌面每一次开灯箱都打在未预热的 2400 上, 服务端现场解码
    230~900ms, 还连带把同进程的其他请求一起卡住。"""
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "app.js").read_text("utf-8")
    m = re.search(r"var LB_W = (\d+);", js)
    assert m, "app.js 里找不到灯箱档位常量 LB_W"
    assert int(m.group(1)) in PREHEAT_SHORT
    assert re.search(r'"/t/s" \+ w \+ "/"', js) or '"/t/s"' in js, \
        "灯箱缩放档必须走短边语义 /t/s{w}/"


def test_thumb_re_short_side():
    m = THUMB_RE.match("s2400/demo/x/abc.jpg")
    assert m and m.group(1) == "s" and m.group(2) == "2400" and m.group(3) is None

def test_thumb_re_rejects_short_side_with_crop():
    # 短边与裁剪语法互斥:显示档必须完整构图
    assert THUMB_RE.match("s2400x1600/demo/x/abc.jpg") is not None  # 正则可匹配…
    m = THUMB_RE.match("s2400x1600/demo/x/abc.jpg")
    assert m and m.group(3) == "1600"  # …但 serve_thumb 会拒绝(见 404 测试)


def test_thumb_re_width_only():
    m = THUMB_RE.match("900/demo/x/abc.jpg")
    assert m and m.group(1) == "" and m.group(2) == "900" and m.group(4) == "demo/x/abc"


def test_thumb_re_width_height():
    m = THUMB_RE.match("300x400/demo/x/abc.jpg")
    assert m and m.group(2) == "300" and m.group(3) == "400"


def test_thumb_re_rejects_garbage():
    assert THUMB_RE.match("abc/demo/x.jpg") is None
    assert THUMB_RE.match("900/demo/x.gif") is None


def test_thumbnail_served_and_cached(admin_client):
    url = thumb_url("demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg", 300)
    r1 = admin_client.get(url)
    assert r1.status_code == 200 and r1.headers["content-type"] == "image/webp"
    r2 = admin_client.get(url)  # 第二次走缓存文件
    assert r2.status_code == 200 and r2.headers["content-type"] == "image/webp"


def test_short_side_landscape_clamps_height(admin_client):
    """s 前缀短边钳制:横图钳高(短边=高),等比不裁。"""
    from app.services import media

    # 从库里找一张真横图(种子集多竖图)
    src = None
    for p in sorted((media.settings.media_dir / "demo").rglob("*.jpg")):
        if p.name in ("avatars",):
            continue
        with Image.open(p) as im:
            if im.size[0] > im.size[1] and im.size[1] >= 64:
                src = p.relative_to(media.settings.media_dir).as_posix()
                break
    assert src, "demo 种子里没找到横图"
    url = thumb_url(src, 32, short=True)
    r = admin_client.get(url)
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.size[1] == 32                 # 高(短边)= 32
        assert out.size[0] > 32                  # 宽(长边)按比例,不裁
    assert media._cache_path(32, None, 78, src, short=True).is_file()


def test_short_side_portrait_clamps_width(admin_client):
    """s 前缀短边钳制:竖图钳宽(短边=宽),与旧钳宽档结果一致。"""
    from app.services import media

    src = "demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg"  # 1200×1798 竖图
    url = thumb_url(src, 32, short=True)
    r = admin_client.get(url)
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.size[0] == 32
        assert out.size[1] == round(32 * 1798 / 1200)


def test_short_side_no_upscale(admin_client):
    """只缩不放:源图短边已小于目标时原样输出。"""
    from app.services import media

    src = "demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg"
    p = media.abs_path(src)
    with Image.open(p) as im:
        sw, sh = im.size
    short = min(sw, sh)
    url = thumb_url(src, short * 10, short=True)  # 目标短边远大于源
    r = admin_client.get(url)
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.size == (sw, sh)


def test_short_side_with_crop_404(admin_client):
    """短边与 x{h} 裁剪语法互斥,组合请求 404。"""
    assert admin_client.get("/t/s2400x1600/demo/x/abc.jpg.webp").status_code == 404


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

    def fake_ensure(rel, w, h=None, q=None, short=False):
        calls.append(rel)
        return False  # 全命中缓存
    monkeypatch.setattr(media, "ensure_cached", fake_ensure)
    monkeypatch.setattr(media, "_load_libc", lambda: None)

    done, generated = media._preheat_files(["a.jpg", "b.jpg", "c.jpg"], batch=1)

    assert done == 3
    assert generated == 0
    assert len(calls) == 9      # 3 张 × 3 档(900 钳宽 + s2400/s900 短边)
    assert sleeps == []         # 全命中 → 零睡眠


def test_preheat_pauses_when_generating(monkeypatch, clean_preheat_event):
    """实际生成缩略图时保留原有节流睡眠。"""
    import time
    from app.services import media

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    calls: list[str] = []

    def fake_ensure(rel, w, h=None, q=None, short=False):
        calls.append(rel)
        return True  # 每档都真生成

    monkeypatch.setattr(media, "ensure_cached", fake_ensure)
    monkeypatch.setattr(media, "_load_libc", lambda: None)

    done, generated = media._preheat_files(["a.jpg", "b.jpg"], batch=4)

    assert done == 2
    assert generated == 6            # 2 张 × 3 档(900 钳宽 + s2400/s900 短边)
    assert len(calls) == 6
    assert sleeps == [media._preheat_gap] * 2  # 每张都节流


def test_preheat_stops_on_shutdown_event(monkeypatch, clean_preheat_event):
    """停机事件置位后巡检提前退出。"""
    import time
    from app.services import media

    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(media, "ensure_cached", lambda rel, w, h=None, q=None, short=False: False)
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
