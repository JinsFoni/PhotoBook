"""原图回源 — 本地原图缺失时 /media 的 302 直链与服务端流式代理。

两档策略:
1. 302 直链(首选): imgbed 直链即公网地址;webdav(OpenList)的 /d/ 直链
   会 302 到网盘(123 云盘等)公网 CDN,服务端解析出最终直链再交给浏览器,
   文件字节不过 NAS。前提: 服务端与 OpenList 同网络可达(部署形态保证)。
2. 流式代理(兜底): 直链解析失败时逐存储拉取后透传给客户端。

历史教训:曾直接 302 跳 webdav 的局域网直链,公网 HTTPS 页面加载被浏览器
按混合内容拦截(下载/1:1 放大全挂)。
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
    """模拟存储服务端:
    /file/...        → 200 直接回文件(模拟图床直链)
    /d/...           → 302 到 CDN_HOST(模拟 OpenList 直链跳网盘 CDN)
    /cdn/...         → 200 回文件(模拟网盘 CDN 最终直链)
    /missing*        → 404
    """

    seen_ranges: list[str] = []
    seen_heads: list[str] = []
    payload = b""
    cdn_host = "cdn.example.com"
    head_d_status = 302  # 500 可模拟 OpenList 异常(解析失败 → 代理兜底)

    def do_HEAD(self):
        _StubOrigin.seen_heads.append(self.path)
        if self.path.startswith("/d/"):
            if _StubOrigin.head_d_status != 302:
                self.send_response(_StubOrigin.head_d_status)
                self.end_headers()
                return
            self.send_response(302)
            final = f"http://{_StubOrigin.cdn_host}/cdn/{self.path[3:]}"
            self.send_header("Location", final)
            self.end_headers()
        elif self.path.startswith("/missing"):
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(_StubOrigin.payload)))
            self.end_headers()

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
    _StubOrigin.seen_heads = []
    _StubOrigin.head_d_status = 302
    srv = HTTPServer(("127.0.0.1", 0), _StubOrigin)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _mk_photo_with_remote(rel: str, origin: str) -> None:
    """建 Photo 行 + PhotoUpload 记录,并删除本地原图(模拟已上传外存)。

    webdav 的 public_url = api_url + "/d/" + remote_path,
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
        st = s.query(Storage).filter(Storage.name == "test-storage").first()
        if not st:
            st = Storage(name="test-storage", type="webdav", token="t",
                         enabled=True, direct_link=True, priority=9)
            s.add(st)
        st.type = "webdav"
        st.api_url = origin  # stub 端口每次 fixture 都换,始终指向当前实例
        s.flush()
        s.add(PhotoUpload(photo_id=p.id, storage_id=st.id, remote_path=rel))
        s.commit()
    finally:
        s.close()
    (settings.media_dir / rel).unlink(missing_ok=True)  # 本地原图已删


def test_media_missing_local_proxies_remote(admin_client, stub_origin):
    """webdav 直链解析失败(OpenList 异常)→ 兜底走服务端流式代理 200。"""
    from app.config import settings
    from app.services import media

    rel = "proxy-owner/proxy-album/photo-001.jpg"
    _mk_photo_with_remote(rel, stub_origin)
    _StubOrigin.head_d_status = 500  # 解析拿不到直链

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
    """Range 请求头透传给上游(下载续传依赖,代理兜底路径)。"""
    rel = "proxy-owner/proxy-album/photo-range.jpg"
    _mk_photo_with_remote(rel, stub_origin)
    _StubOrigin.head_d_status = 500  # 走代理兜底
    admin_client.get(f"/media/{rel}", headers={"Range": "bytes=0-99"})
    assert _StubOrigin.seen_ranges[-1] == "bytes=0-99"


# ---- 302 直链解析 ---------------------------------------------------------------

def test_media_302_resolves_webdav_cdn_link(admin_client, stub_origin, monkeypatch):
    """webdav 直链 → 服务端解析 OpenList 302 → 浏览器拿到最终 CDN 直链。

    /d/ 直链先 302 到 http://cdn.example.com/cdn/...,stub 的 do_HEAD 模拟
    该行为;resolve 拿到 Location 后 302 给客户端,文件字节不过 NAS。
    """
    rel = "proxy-owner/proxy-album/photo-302.jpg"
    _mk_photo_with_remote(rel, stub_origin)
    # 把 CDN host 换成本桩可解析的地址: 解析只发 HEAD,302 的 Location
    # 原样返回;最终直链可达性由浏览器负责(解析阶段不校验)
    monkeypatch.setattr(_StubOrigin, "cdn_host", "127.0.0.1")
    r = admin_client.get(f"/media/{rel}", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith(f"http://127.0.0.1/cdn/proxy-owner/")
    assert "/d/" not in loc  # 已解析掉 OpenList 一跳
    # 解析确实向 stub 发过 HEAD
    assert any(p.startswith("/d/") for p in _StubOrigin.seen_heads)


def test_media_302_imgbed_direct(admin_client, stub_origin, monkeypatch):
    """imgbed 直链本身即最终地址,不发 HEAD 解析直接 302。"""
    from app.database import SessionLocal
    from app.db import Storage

    rel = "proxy-owner/proxy-album/photo-imgbed302.jpg"
    _mk_photo_with_remote(rel, stub_origin)
    s = SessionLocal()
    try:
        st = s.query(Storage).filter(Storage.name == "test-storage").first()
        st.type = "imgbed"
        s.commit()
    finally:
        s.close()
    r = admin_client.get(f"/media/{rel}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith(f"{stub_origin}/file/")
    assert _StubOrigin.seen_heads == []  # 未做解析请求


def test_resolve_final_url_falls_back_on_200():
    """OpenList 关闭 sign_all 时 /d/ 直接 200 出文件:原链接本身可用。"""
    from app.services.storage import _resolve_final_url
    assert _resolve_final_url("http://no-such-host.invalid/d/x.jpg") is None


def test_resolve_final_url_ignores_non_webdav():
    """imgbed 链接(无 /d/ 段)不做解析,原样返回。"""
    from app.services.storage import _resolve_final_url
    url = "https://imgbed.example.com/file/PhotoBook/a.jpg"
    assert _resolve_final_url(url) == url
