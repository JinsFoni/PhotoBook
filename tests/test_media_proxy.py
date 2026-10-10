"""原图回源代理 — 本地原图缺失时 /media 流式代理远端存储。

历史教训:曾用 302 跳远端直链,但 WebDAV 类存储(OpenList)的直链是
局域网地址,公网 HTTPS 页面加载被浏览器按混合内容拦截(下载/1:1 放大
全挂)。改为服务端代理,容器到存储的连通性已被缩略图回源路径验证。
"""

from __future__ import annotations

import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image


def _jpeg_bytes(w=40, h=60, color=(120, 40, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


class _StubOrigin(BaseHTTPRequestHandler):
    """模拟远端存储原图:按 path 返回固定 JPEG,记录收到的 Range。"""

    seen_ranges: list[str] = []
    payload = b""

    def do_GET(self):
        if self.path.startswith("/missing"):
            self.send_response(404)
            self.end_headers()
            return
        _StubOrigin.seen_ranges.append(self.headers.get("Range", ""))
        self.send_response(200)
        self.send_header("Content-Type", "image/png")  # 故意给错类型,代理应按扩展名纠正
        self.send_header("Content-Length", str(len(_StubOrigin.payload)))
        self.end_headers()
        self.wfile.write(_StubOrigin.payload)

    def log_message(self, *a):  # 静默
        pass


@pytest.fixture()
def stub_origin():
    _StubOrigin.payload = _jpeg_bytes()
    _StubOrigin.seen_ranges = []
    srv = HTTPServer(("127.0.0.1", 0), _StubOrigin)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _mk_photo_with_remote(rel: str, origin: str) -> None:
    """建 Photo 行 + PhotoUpload 记录,并删除本地原图(模拟已上传外存)。

    imgbed 的 public_url = api_url + "/file/" + remote_path,
    故 api_url 指向 stub origin,remote_path 存相对路径。"""
    from app.database import SessionLocal
    from app.db import Collection, Model, Photo, PhotoUpload, Storage
    from app.config import settings

    owner, album = rel.split("/")[:2]
    s = SessionLocal()
    try:
        m = s.query(Model).filter(Model.name == owner).first()
        if not m:
            m = Model(name=owner, slug=owner)
            s.add(m)
            s.flush()
        c = s.query(Collection).filter(Collection.slug == album).first()
        if not c:
            c = Collection(slug=album, title=album, model_id=m.id,
                           published_at="2026.10.01", status="published")
            s.add(c)
            s.flush()
        p = Photo(collection_id=c.id, filename=rel, sort_order=0)
        s.add(p)
        s.flush()
        st = s.query(Storage).filter(Storage.type == "imgbed").first()
        if not st:
            st = Storage(name="test-imgbed", type="imgbed", token="t",
                         enabled=True, direct_link=True, priority=9)
            s.add(st)
        st.api_url = origin  # stub 端口每次 fixture 都换,始终指向当前实例
        s.flush()
        s.add(PhotoUpload(photo_id=p.id, storage_id=st.id, remote_path=rel))
        s.commit()
    finally:
        s.close()
    (settings.media_dir / rel).unlink(missing_ok=True)  # 本地原图已删


def test_media_missing_local_proxies_remote(admin_client, stub_origin):
    """本地原图缺失 + 有远端记录 → 200 代理回源(不再 302/404)。"""
    from app.config import settings
    from app.database import SessionLocal
    from app.db import Photo
    from app.services import media

    rel = "proxy-owner/proxy-album/photo-001.jpg"
    _mk_photo_with_remote(rel, stub_origin)

    r = admin_client.get(f"/media/{rel}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"  # 按扩展名纠正上游的 image/png
    assert r.content == _StubOrigin.payload           # 字节一致(流式透传)
    assert "max-age=31536000" in r.headers["cache-control"]
    assert (settings.media_dir / rel).exists() is False  # 不落盘
    media._cache_path(1, 1, 88, rel).unlink(missing_ok=True)


def test_media_missing_no_remote_404(admin_client):
    """本地缺失且无远端记录 → 维持 404。"""
    assert admin_client.get("/media/proxy-owner/x/none.jpg").status_code == 404


def test_media_range_forwarded(admin_client, stub_origin):
    """Range 请求头透传给上游(下载续传依赖)。"""
    rel = "proxy-owner/proxy-album/photo-range.jpg"
    _mk_photo_with_remote(rel, stub_origin)
    admin_client.get(f"/media/{rel}", headers={"Range": "bytes=0-99"})
    assert _StubOrigin.seen_ranges[-1] == "bytes=0-99"
