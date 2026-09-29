"""缩略图服务 — URL 解析、缓存命中、路径安全。"""

from __future__ import annotations

import pytest

from app.services.media import THUMB_RE, thumb_url


def test_thumb_url_width_only():
    assert thumb_url("demo/x/abc.jpg", 900) == "/t/900/demo/x/abc.jpg.webp"


def test_thumb_url_width_height():
    assert thumb_url("demo/x/abc.jpg", 300, 400) == "/t/300x400/demo/x/abc.jpg.webp"


def test_thumb_url_none_placeholder():
    assert thumb_url(None, 900).startswith("data:image/gif")


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
