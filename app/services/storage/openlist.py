"""OpenList API backend — 通过 /api/fs/* 直接管理网盘(实测 123 云盘 / 115 网盘)。

与 webdav backend 的区别:只走 OpenList 的 HTTP API,不走 /dav。两者能力相同
(上传 / 删除 / 目录枚举 / 整目录删除),差别在协议细节:

- 认证: POST /api/auth/login 用用户名+密码换 JWT,之后请求头
  `Authorization: <token>`(不带 Bearer)。token 进程内缓存到过期前;
  万一被服务端提前作废(重启/改密),收到 code=401 自动重登一次。
- 上传: PUT /api/fs/put, 目标路径放在 `File-Path` 头里 —— 必须
  percent-encode, HTTP 头放不下中文(httpx 会直接抛 UnicodeEncodeError)。
  目录不存在时 123 盘会自动补建, 115 盘直接报错, 所以统一先 fs/mkdir。
- 建目录: POST /api/fs/mkdir 一次递归建好整条路径且幂等, 但实测一次要
  1.2s(123)/2.6s(115), 因此同样走进程内缓存, 一本写真集只付一次。
- 删除: POST /api/fs/remove {dir, names[]}; names 里给目录名即递归删除,
  删整本写真集 = 1 次请求。
- 列表: POST /api/fs/list(分页) —— 上传后校验文件大小、删目录前列目录
  做守卫都用它。
- 注意: 这套 API **永远回 HTTP 200**, 成败看 body 里的 code; 路径不存在
  是 code=500 + "object not found"。所以判断一律基于 code/message,
  不能看 status_code。
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from urllib.parse import quote

import httpx

from ...db import Storage
from .base import (CreatedDirs, StorageError, dir_cache_key, join_folder,
                   split_by_dir)

log = logging.getLogger("pb.storage.openlist")

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
_RETRY_DELAYS = (1.5, 4.0)
_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_PAGE = 500

_DIRS = CreatedDirs()

# token 缓存: {(api_url, username, password): (jwt, 过期时刻 monotonic)}
_tokens: dict[tuple, tuple[str, float]] = {}
_tokens_lock = threading.Lock()


def _base(st: Storage) -> str:
    if not st.api_url:
        raise StorageError("未配置服务地址")
    base = st.api_url.rstrip("/")
    if base.endswith("/dav"):
        base = base[:-4]
    return base


def _client(st: Storage) -> httpx.Client:
    return httpx.Client(base_url=_base(st), timeout=_TIMEOUT)


def _token_key(st: Storage) -> tuple:
    return (_base(st), st.username or "", st.token or "")


def _jwt_exp(token: str) -> float:
    """JWT 的 exp(epoch 秒);解析失败按 6 小时算。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:
        return 0.0


def _token(st: Storage, client: httpx.Client) -> str:
    key = _token_key(st)
    with _tokens_lock:
        hit = _tokens.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
    if not st.username or not st.token:
        raise StorageError("未配置 OpenList 用户名或密码")
    try:
        resp = client.post("/api/auth/login",
                           json={"username": st.username, "password": st.token})
    except httpx.HTTPError as e:
        raise StorageError(f"登录 OpenList 失败: {e}")
    body = _body(resp)
    if body.get("code") != 200:
        raise StorageError(f"登录 OpenList 失败: {body.get('message') or body.get('code')}")
    token = str((body.get("data") or {}).get("token") or "")
    if not token:
        raise StorageError("登录 OpenList 失败: 响应里没有 token")
    ttl = _jwt_exp(token) - time.time() - 60
    if ttl < 300:  # 拿不到 exp(或马上过期)时按 6 小时缓存
        ttl = 6 * 3600
    with _tokens_lock:
        _tokens[key] = (token, time.monotonic() + ttl)
    return token


def _forget_token(st: Storage) -> None:
    with _tokens_lock:
        _tokens.pop(_token_key(st), None)


def _body(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        raise StorageError(f"响应格式异常 HTTP {resp.status_code}: {resp.text[:200]}")
    if not isinstance(data, dict):
        raise StorageError(f"响应格式异常: {resp.text[:200]}")
    return data


def _not_found(body: dict) -> bool:
    msg = str(body.get("message") or "").lower()
    return body.get("code") in (404,) or "not found" in msg or "object not found" in msg


def _retryable(body: dict) -> bool:
    return body.get("code") in _RETRYABLE_CODES and not _not_found(body)


def _fail(what: str, body: dict) -> StorageError:
    msg = str(body.get("message") or "").strip()[:200]
    return StorageError(f"{what}失败: {msg or 'code=%s' % body.get('code')}")


def _call(st: Storage, method: str, path: str, *, what: str, **kw) -> dict:
    """发一次 API 调用: 自动带 token, code=401 重登一次, 网络错误重试。"""
    last: dict = {}
    extra = dict(kw)
    base_headers = dict(extra.pop("headers", None) or {})
    for attempt in range(3):
        if attempt:
            time.sleep(_RETRY_DELAYS[attempt - 1])
        with _client(st) as client:
            headers = dict(base_headers)
            headers["Authorization"] = _token(st, client)
            try:
                resp = client.request(method, path, headers=headers, **extra)
            except httpx.HTTPError as e:
                last = {"code": -1, "message": str(e)}
                log.warning("openlist %s network error (attempt %d): %s",
                            what, attempt + 1, e)
                continue
        body = _body(resp)
        if body.get("code") == 401 and attempt == 0:
            _forget_token(st)  # token 被作废: 重登后再试
            continue
        if body.get("code") != 200 and _retryable(body) and attempt < 2:
            last = body
            log.warning("openlist %s retryable: %s", what, body.get("message"))
            continue
        return body
    return last


def _ensure_dirs(st: Storage, folder: str) -> None:
    """递归建目录(OpenList 一次调用建整条路径, 幂等), 已建过的跳过。"""
    if not folder:
        return
    key = dir_cache_key(st)
    if _DIRS.ready(key, folder):
        return
    body = _call(st, "POST", "/api/fs/mkdir", what="mkdir", json={"path": "/" + folder})
    if body.get("code") == 200:
        _DIRS.mark(key, folder)
        return
    raise _fail(f"创建目录 {folder} ", body)


class OpenListBackend:
    def upload(self, st: Storage, data: bytes, filename: str,
               remote_folder: str) -> str:
        folder = join_folder(st.root_dir, remote_folder)
        target = "/" + "/".join(p for p in (folder, filename) if p)
        last: dict = {}
        for attempt in range(3):
            if attempt:
                time.sleep(_RETRY_DELAYS[attempt - 1])
            _ensure_dirs(st, folder)
            body = _call(st, "PUT", "/api/fs/put", what=f"put {filename}",
                         content=data,
                         headers={"File-Path": quote(target, safe="/")})
            if body.get("code") == 200:
                # 远端不改名, 返回 root/relative 约定路径
                return "/".join(p for p in (folder, filename) if p)
            last = body
            if not _retryable(body):
                break
        msg = str(last.get("message") or "")[:200]
        raise StorageError(
            f"上传失败: {msg or 'code=%s' % last.get('code')}"
            + ("(根目录需包含挂载名,如 /123云盘/OpenList/PhotoBook)"
               if _not_found(last) else ""))

    def delete_batch(self, st: Storage, remote_paths: list[str]) -> None:
        """按目录分组批量删除; 整组失败时退回逐个删, 仍是尽力而为。"""
        if not remote_paths:
            return
        failed: list[str] = []
        for d, names in split_by_dir(remote_paths).items():
            body = _call(st, "POST", "/api/fs/remove", what="remove",
                         json={"dir": "/" + d, "names": names})
            if body.get("code") == 200 or _not_found(body):
                continue
            log.warning("openlist batch remove %s -> %s", d, body.get("message"))
            for name in names:  # 整组失败: 逐个重试, 少删一个是一个
                one = _call(st, "POST", "/api/fs/remove", what="remove",
                            json={"dir": "/" + d, "names": [name]})
                if one.get("code") != 200 and not _not_found(one):
                    failed.append(f"{d}/{name}")
        if failed:
            raise StorageError(f"远端删除失败 {len(failed)} 个文件")

    # ---- TreeBackend -----------------------------------------------------

    def list_sizes(self, st: Storage, remote_dir: str) -> dict[str, int] | None:
        """fs/list 分页列目录: {名字: 字节数}, 子目录 -1。"""
        folder = (remote_dir or "").strip("/")
        if not folder:
            return {}
        out: dict[str, int] = {}
        page = 1
        while True:
            body = _call(st, "POST", "/api/fs/list", what="list",
                         json={"path": "/" + folder, "page": page,
                               "per_page": _PAGE, "refresh": False})
            if body.get("code") != 200:
                if _not_found(body):
                    return {}
                log.warning("openlist list %s -> %s", folder, body.get("message"))
                return None
            data = body.get("data") or {}
            items = data.get("content") or []
            for e in items:
                name = str(e.get("name") or "")
                if not name:
                    continue
                out[name] = -1 if e.get("is_dir") else int(e.get("size") or 0)
            total = int(data.get("total") or 0)
            if len(items) < _PAGE or len(out) >= total:
                break
            page += 1
        return out

    def delete_dir(self, st: Storage, remote_dir: str,
                   allowed: set[str] | None = None) -> bool:
        """fs/remove 删目录(递归) —— 1 次请求删完整本写真集。"""
        folder = (remote_dir or "").strip("/")
        if not folder:
            return False
        if allowed is not None:
            listing = self.list_sizes(st, folder)
            if listing is None:
                return False  # 列不出来就不敢盲删
            unexpected = [n for n in listing if n not in allowed]
            if unexpected:
                log.info("openlist dir delete skipped: %s has %d unexpected entries",
                         folder, len(unexpected))
                return False
        parent, _, name = folder.rpartition("/")
        body = _call(st, "POST", "/api/fs/remove", what="remove dir",
                     json={"dir": "/" + parent, "names": [name]})
        if body.get("code") == 200 or _not_found(body):
            _DIRS.forget(dir_cache_key(st), folder)
            return True
        log.warning("openlist delete dir %s -> %s", folder, body.get("message"))
        return False

    def public_url(self, st: Storage, remote_path: str) -> str:
        return quote(f"{_base(st)}/d/{remote_path.lstrip('/')}", safe="/:")

    def test_connection(self, st: Storage) -> str:
        root = (st.root_dir or "").strip("/")
        body = _call(st, "POST", "/api/fs/list", what="test",
                     json={"path": "/" + root, "page": 1, "per_page": 1})
        if body.get("code") == 200:
            total = int((body.get("data") or {}).get("total") or 0)
            return f"连接成功,根目录 {st.root_dir or '/'} 可访问(共 {total} 项)"
        msg = str(body.get("message") or "")[:200]
        if body.get("code") == 401:
            raise StorageError("认证失败: OpenList 用户名或密码错误")
        if _not_found(body):
            raise StorageError(
                f"根目录不存在: {st.root_dir or '/'}"
                "(OpenList 路径需包含挂载名,如 /123云盘/媒体库/PhotoBook)")
        raise StorageError(f"连接失败: {msg or body.get('code')}")
