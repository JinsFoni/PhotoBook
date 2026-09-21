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
