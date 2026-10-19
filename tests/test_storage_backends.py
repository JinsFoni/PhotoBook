"""storage backend 协议层 — webdav / openlist 的上传、目录删除、校验。

用一个进程内 stub 服务端同时实现两套协议(同一个 dict 当远端文件系统),
断言的是「请求次数与请求形状」—— 目录级删除、MKCOL/mkdir 去重这些优化
最终就体现在请求数上:

- 同一目录上传 N 张 → 只 MKCOL / fs.mkdir 一次;
- 删写真集 → 1 次 DELETE / fs.remove,不是 N 次;
- 目录里出现快照之外的文件(删完又立刻重新导入上传)→ 拒删,退回逐文件;
- 上传后按目录核对大小 → 能发现截断,重传后恢复。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlsplit

import pytest

from app.database import SessionLocal
from app.db import Collection, Photo, PhotoUpload, Storage
from app.services import storage as storage_svc
from app.services.storage.base import verify_uploads
from app.services.storage.openlist import OpenListBackend
from app.services.storage.webdav import WebDavBackend

USER, PASSWORD, TOKEN = "mario", "Ym1999", "stub-token"


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def reset(self) -> None:
        with self.lock:
            self.files.clear()
            self.dirs.clear()
            self.calls.clear()
        self.dirs.add("root")

    def add(self, path: str, data: bytes = b"x") -> None:
        parent = path.rsplit("/", 1)[0]
        self.mkdir(parent)
        self.files[path] = data

    def mkdir(self, path: str) -> None:
        parts = [p for p in path.strip("/").split("/") if p]
        acc = ""
        for p in parts:
            acc = f"{acc}/{p}" if acc else p
            self.dirs.add(acc)

    def count(self, kind: str) -> int:
        with self.lock:
            return sum(1 for k, _ in self.calls if k == kind)


STATE = _State()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):  # noqa: D401 - 静音测试日志
        pass

    # ---- 基础 -------------------------------------------------------------

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj: dict):
        self._send(200, json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json")

    def _record(self, kind: str, path: str):
        with STATE.lock:
            STATE.calls.append((kind, path))

    def _ok_dav_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Basic ")

    def _ok_api_auth(self) -> bool:
        return self.headers.get("Authorization", "") == TOKEN

    # ---- 路由 -------------------------------------------------------------

    def do_GET(self):
        self._dispatch("GET")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PROPFIND(self):
        self._dispatch("PROPFIND")

    def do_MKCOL(self):
        self._dispatch("MKCOL")

    def _dispatch(self, method: str):
        path = urlsplit(self.path).path
        if path.startswith("/dav"):
            self._dav(method, unquote(path[4:]).strip("/"))
        elif path.startswith("/api/"):
            self._api(method, path)
        else:
            self._send(404)

    # ---- WebDAV -----------------------------------------------------------

    def _dav(self, method: str, path: str):
        if not self._ok_dav_auth():
            self._record("401", path)
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="stub"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._record(method, path)
        if method == "MKCOL":
            if path in STATE.dirs:
                self._send(405)
            else:
                STATE.mkdir(path)
                self._send(201)
        elif method == "PUT":
            parent = path.rsplit("/", 1)[0]
            if parent not in STATE.dirs:
                self._send(409)
                return
            STATE.files[path] = self._body()
            self._send(201)
        elif method == "DELETE":
            if path in STATE.files:
                with STATE.lock:
                    STATE.files.pop(path, None)
                self._send(204)
            elif path in STATE.dirs:
                with STATE.lock:
                    for f in [f for f in STATE.files if f.startswith(path + "/")]:
                        STATE.files.pop(f, None)
                    for d in [d for d in STATE.dirs if d == path or d.startswith(path + "/")]:
                        STATE.dirs.discard(d)
                self._send(204)
            else:
                self._send(404)
        elif method == "PROPFIND":
            self._send(200, self._propfind(path), "application/xml")
        else:
            self._send(405)

    def _propfind(self, path: str) -> bytes:
        if path not in STATE.dirs and path not in STATE.files:
            return b""
        depth = self.headers.get("Depth", "1")
        rows = []

        def entry(p: str, isdir: bool, size: int = 0) -> str:
            href = "/dav/" + quote(p)
            rt = ("<D:resourcetype><D:collection/></D:resourcetype>"
                  if isdir else "<D:resourcetype/>")
            cl = "" if isdir else f"<D:getcontentlength>{size}</D:getcontentlength>"
            return (f"<D:response><D:href>{href}</D:href><D:propstat><D:prop>{rt}{cl}"
                    f"<D:displayname>{p.rsplit('/', 1)[-1]}</D:displayname>"
                    f"</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>"
                    f"</D:response>")

        if path in STATE.dirs:
            rows.append(entry(path, True))
        if depth != "0":
            prefix = path + "/"
            for f in sorted(STATE.files):
                if f.startswith(prefix) and "/" not in f[len(prefix):]:
                    rows.append(entry(f, False, len(STATE.files[f])))
            for d in sorted(STATE.dirs):
                if d.startswith(prefix) and "/" not in d[len(prefix):]:
                    rows.append(entry(d, True))
        return ('<?xml version="1.0" encoding="utf-8"?>'
                '<D:multistatus xmlns:D="DAV:">' + "".join(rows) +
                "</D:multistatus>").encode()

    # ---- OpenList API -----------------------------------------------------

    def _api(self, method: str, path: str):
        body = self._body()
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            data = {}
        if path == "/api/auth/login":
            self._record("login", path)
            if (data.get("username"), data.get("password")) == (USER, PASSWORD):
                self._json({"code": 200, "message": "success",
                            "data": {"token": TOKEN}})
            else:
                self._json({"code": 401, "message": "Invalid username or password"})
            return
        if not self._ok_api_auth():
            self._record("401", path)
            self._json({"code": 401, "message": "token is invalidated"})
            return
        if path == "/api/fs/put" and method == "PUT":
            target = unquote(self.headers.get("File-Path", "")).strip("/")
            self._record("put", target)
            parent = target.rsplit("/", 1)[0]
            if parent not in STATE.dirs:
                self._json({"code": 500, "message": f"object not found; rawPath: /{parent}"})
                return
            STATE.files[target] = body
            self._json({"code": 200, "message": "success", "data": None})
        elif path == "/api/fs/mkdir":
            target = str(data.get("path") or "").strip("/")
            self._record("mkdir", target)
            STATE.mkdir(target)
            self._json({"code": 200, "message": "success", "data": None})
        elif path == "/api/fs/list":
            target = str(data.get("path") or "").strip("/")
            self._record("list", target)
            if target not in STATE.dirs:
                self._json({"code": 500, "message": "object not found"})
                return
            prefix = target + "/"
            content = []
            for f in sorted(STATE.files):
                if f.startswith(prefix) and "/" not in f[len(prefix):]:
                    content.append({"name": f[len(prefix):],
                                    "size": len(STATE.files[f]), "is_dir": False})
            for d in sorted(STATE.dirs):
                if d.startswith(prefix) and "/" not in d[len(prefix):]:
                    content.append({"name": d[len(prefix):], "size": 0, "is_dir": True})
            self._json({"code": 200, "message": "success",
                        "data": {"content": content, "total": len(content)}})
        elif path == "/api/fs/remove":
            target = str(data.get("dir") or "").strip("/")
            names = data.get("names") or []
            self._record("remove", f"{target}:{','.join(names)}")
            with STATE.lock:
                for name in names:
                    full = f"{target}/{name}" if target else name
                    if full in STATE.files:
                        STATE.files.pop(full)
                    else:
                        for f in [f for f in STATE.files if f.startswith(full + "/")]:
                            STATE.files.pop(f, None)
                        for d in [d for d in STATE.dirs if d == full or d.startswith(full + "/")]:
                            STATE.dirs.discard(d)
            self._json({"code": 200, "message": "success", "data": None})
        else:
            self._send(404)


@pytest.fixture()
def remote():
    STATE.reset()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _st(origin: str, kind: str, root: str = "/root") -> Storage:
    return Storage(id=1, name="stub", type=kind, api_url=origin,
                   username=USER, token=PASSWORD, root_dir=root, enabled=True)


# ---- 上传: 目录只建一次 -------------------------------------------------------

def test_webdav_upload_mkcol_once_per_folder(remote):
    st = _st(remote, "webdav")
    be = WebDavBackend()
    for i in range(3):
        assert be.upload(st, b"x" * 10, f"{i}.jpg", "m/a") == f"root/m/a/{i}.jpg"
    assert STATE.count("PUT") == 3
    assert STATE.count("MKCOL") == 3, "root / root/m / root/m/a 各一次"
    assert STATE.files["root/m/a/0.jpg"] == b"x" * 10
    # 同一目录再传不重复 MKCOL
    be.upload(st, b"y", "z.jpg", "m/a")
    assert STATE.count("MKCOL") == 3


def test_openlist_upload_login_and_mkdir_once(remote):
    st = _st(remote, "openlist")
    be = OpenListBackend()
    for i in range(3):
        assert be.upload(st, b"x" * 10, f"{i}.jpg", "m/a") == f"root/m/a/{i}.jpg"
    assert STATE.count("login") == 1, "JWT 进程内缓存, 只登录一次"
    assert STATE.count("mkdir") == 1, "递归建目录, 一本写真集一次"
    assert STATE.count("put") == 3
    assert STATE.files["root/m/a/2.jpg"] == b"x" * 10


def test_openlist_upload_retries_after_token_invalid(remote):
    st = _st(remote, "openlist")
    be = OpenListBackend()
    be.upload(st, b"a", "1.jpg", "m/a")
    # 服务端重启/改密导致 token 失效 → 自动重登并成功
    from app.services.storage import openlist as ol
    with ol._tokens_lock:
        ol._tokens.clear()
    assert be.upload(st, b"b", "2.jpg", "m/a") == "root/m/a/2.jpg"
    assert STATE.count("login") == 2


# ---- 目录级删除 ---------------------------------------------------------------

@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_delete_dir_is_single_request(remote, kind):
    st = _st(remote, kind)
    be = WebDavBackend() if kind == "webdav" else OpenListBackend()
    names = {f"{i:03d}.jpg" for i in range(40)}
    for n in names:
        STATE.add(f"root/m/a/{n}", b"x" * 8)
    assert be.delete_dir(st, "root/m/a", allowed=names) is True
    if kind == "webdav":
        assert STATE.count("DELETE") == 1
        assert STATE.count("PROPFIND") == 1, "删前一次列目录做守卫"
    else:
        assert STATE.count("remove") == 1
        assert STATE.count("list") == 1
    assert not [f for f in STATE.files if f.startswith("root/m/a/")]


@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_delete_dir_refuses_when_extra_files(remote, kind):
    """删完写真集又立刻重新导入上传时, 目录里会有快照之外的新文件。"""
    st = _st(remote, kind)
    be = WebDavBackend() if kind == "webdav" else OpenListBackend()
    names = {"001.jpg", "002.jpg"}
    for n in names:
        STATE.add(f"root/m/a/{n}")
    STATE.add("root/m/a/reimported.jpg")
    assert be.delete_dir(st, "root/m/a", allowed=names) is False
    assert STATE.files["root/m/a/reimported.jpg"] == b"x"
    assert "root/m/a/001.jpg" in STATE.files, "拒删时一个都不能动"


@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_delete_batch_fallback_per_file(remote, kind):
    st = _st(remote, kind)
    be = WebDavBackend() if kind == "webdav" else OpenListBackend()
    for i in range(3):
        STATE.add(f"root/m/a/{i}.jpg")
    be.delete_batch(st, [f"root/m/a/{i}.jpg" for i in range(3)])
    assert not [f for f in STATE.files if f.startswith("root/m/a/")]


# ---- 上传校验 -----------------------------------------------------------------

@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_verify_detects_truncation(remote, kind):
    st = _st(remote, kind)
    be = WebDavBackend() if kind == "webdav" else OpenListBackend()
    be.upload(st, b"x" * 100, "1.jpg", "m/a")
    be.upload(st, b"x" * 100, "2.jpg", "m/a")
    expected = {"root/m/a/1.jpg": 100, "root/m/a/2.jpg": 100}
    assert verify_uploads(be, st, expected) == []

    STATE.files["root/m/a/2.jpg"] = b"x" * 40  # 模拟截断
    bad = verify_uploads(be, st, expected)
    assert bad == ["root/m/a/2.jpg"]

    be.upload(st, b"x" * 100, "2.jpg", "m/a")  # 重传后恢复
    assert verify_uploads(be, st, expected) == []


def test_verify_skips_when_listing_fails(remote, monkeypatch):
    st = _st(remote, "webdav")
    be = WebDavBackend()
    monkeypatch.setattr(be, "list_sizes", lambda *a, **k: None)
    assert verify_uploads(be, st, {"root/m/a/1.jpg": 1}) == []


# ---- 后台清理: 走目录删除 / 竞态回退 -------------------------------------------

def _mk_remote_storage(origin: str, kind: str) -> int:
    s = SessionLocal()
    try:
        st = Storage(name=f"zz-{kind}-stub", type=kind, api_url=origin,
                     username=USER, token=PASSWORD, root_dir="/root", enabled=True)
        s.add(st)
        s.commit()
        return st.id
    finally:
        s.close()


def _mk_uploads(storage_id: int, slug: str, names: list[str]) -> int:
    s = SessionLocal()
    try:
        col = Collection(slug=slug, title=slug, status="draft")
        s.add(col)
        s.flush()
        for i, n in enumerate(names):
            p = Photo(collection_id=col.id, filename=f"{slug}/{n}",
                      width=10, height=10, sort_order=i)
            s.add(p)
            s.flush()
            s.add(PhotoUpload(photo_id=p.id, storage_id=storage_id,
                              remote_path=f"root/{slug}/{n}"))
        s.commit()
        return col.id
    finally:
        s.close()


@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_purge_dir_deletes_whole_folder(remote, kind):
    st_id = _mk_remote_storage(remote, kind)
    names = [f"{i:03d}.jpg" for i in range(30)]
    cid = _mk_uploads(st_id, "zz-purge-dir", names)
    for n in names:
        STATE.add(f"root/zz-purge-dir/{n}", b"x" * 8)
    _drop_collection(cid)  # 真实流程: 先删 DB(photo_uploads 级联), 再清远端

    storage_svc._purge_dir(st_id, "root/zz-purge-dir", names, cid, "zz-purge-dir")

    assert not [f for f in STATE.files if f.startswith("root/zz-purge-dir/")]
    if kind == "webdav":
        assert STATE.count("DELETE") == 1, "30 张 = 1 次目录 DELETE"
        assert STATE.count("PROPFIND") == 1
    else:
        assert STATE.count("remove") == 1, "30 张 = 1 次 fs.remove"
        assert STATE.count("list") == 1
    _cleanup_collection(cid, st_id)


@pytest.mark.parametrize("kind", ["webdav", "openlist"])
def test_purge_falls_back_when_reimported_files_present(remote, kind):
    """目录里混进了快照之外的文件 → 只逐文件删快照里的, 新文件留着。"""
    st_id = _mk_remote_storage(remote, kind)
    names = ["001.jpg", "002.jpg"]
    cid = _mk_uploads(st_id, "zz-purge-race", names)
    for n in names:
        STATE.add(f"root/zz-purge-race/{n}")
    STATE.add("root/zz-purge-race/new-import.jpg")
    _drop_collection(cid)

    storage_svc._purge_dir(st_id, "root/zz-purge-race", names, cid, "zz-purge-race")

    assert "root/zz-purge-race/new-import.jpg" in STATE.files
    assert not any(f.endswith(("001.jpg", "002.jpg")) for f in STATE.files)
    if kind == "webdav":
        assert STATE.count("DELETE") == 2, "守卫拒删 → 退回逐文件"
    else:
        assert STATE.count("remove") == 1, "逐文件兜底按目录批量提交"
    assert "root/zz-purge-race/001.jpg" not in STATE.files
    _cleanup_collection(cid, st_id)


def _drop_collection(cid: int) -> None:
    s = SessionLocal()
    try:
        col = s.get(Collection, cid)
        if col is not None:
            s.delete(col)
        s.commit()
    finally:
        s.close()


def _cleanup_collection(cid: int, st_id: int):
    s = SessionLocal()
    try:
        col = s.get(Collection, cid)
        if col is not None:
            s.delete(col)
        st = s.get(Storage, st_id)
        if st is not None:
            s.query(PhotoUpload).filter_by(storage_id=st_id).delete()
            s.delete(st)
        s.commit()
    finally:
        s.close()
