"""WebDAV backend — 通过标准 WebDAV 协议管理远端(实测 OpenList /dav)。

要点(实测确认):
- 只走 WebDAV 的四个动词: PUT / DELETE / MKCOL / PROPFIND, Basic 认证,
  不碰服务端的 /api/* —— 换成 OpenList 或别的 WebDAV 服务端行为一致。
- 上传目录 = root_dir + 写真集相对目录; PUT 前逐级 MKCOL(幂等, 已存在
  返回 405/301), 已建过的目录走进程内缓存, 不重复请求。
- 删除写真集: 目录与写真集一一对应, 直接 DELETE 整个目录 = 1 次请求
  (RFC 4918 要求集合递归删除)。删之前 PROPFIND 列一次目录做守卫,
  见 base.TreeBackend.delete_dir 的说明; 目录里混进快照之外的文件时
  退回逐文件删除。
- public_url 拼服务端公开直链 /d/<路径>(OpenList 模式, 302 到源站, 免认证;
  若服务端开启 sign_all 则直链需带签名, 目前不支持, 表单里有提示)。
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlparse

import httpx

from ...db import Storage
from .base import (CreatedDirs, StorageError, dir_cache_key, join_folder,
                   split_by_dir)

log = logging.getLogger("pb.storage.webdav")

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)

# 网盘驱动瞬时抖动(高频 PUT 偶发 405/429/5xx)视为可重试
_RETRYABLE = {405, 429, 500, 502, 503, 504}
_RETRY_DELAYS = (2.0, 5.0)

_DIRS = CreatedDirs()

_DAV = "{DAV:}"


def _upload_folder(root_dir: str, remote_folder: str) -> str:
    """兼容旧名: 拼最终上传目录(实现在 base.join_folder)。"""
    return join_folder(root_dir, remote_folder)


def _client(st: Storage) -> httpx.Client:
    if not st.api_url:
        raise StorageError("未配置服务地址")
    if not st.username or not st.token:
        raise StorageError("未配置 WebDAV 用户名或密码")
    base = st.api_url.rstrip("/")
    if base.endswith("/dav"):
        base = base[:-4]
    return httpx.Client(base_url=base, timeout=_TIMEOUT,
                        auth=(st.username, st.token))


def _dav_path(root_dir: str, remote_folder: str, name: str = "") -> str:
    """拼 /dav 下的完整路径, 中文目录名 percent-encode(实测必要)。"""
    folder = _upload_folder(root_dir, remote_folder)
    path = "/dav/" + folder if folder else "/dav"
    if name:
        path = path.rstrip("/") + "/" + name
    return quote(path, safe="/")


def _ensure_dirs(client: httpx.Client, st: Storage, folder: str) -> None:
    """逐级建目录,已建过的跳过(进程内缓存)。

    已存在时 MKCOL 返回 405,与"该层级不可创建"(如挂载根)无法区分,
    因此 405 也记为已建好; 其他失败只记日志,最终以 PUT 结果为准
    (OpenList 会自动补建父目录, 部分服务端不允许 MKCOL 但允许 PUT)。
    """
    if not folder:
        return
    key = dir_cache_key(st)
    if _DIRS.ready(key, folder):
        return
    acc = ""
    for part in folder.split("/"):
        if not part:
            continue
        acc = f"{acc}/{part}" if acc else part
        if _DIRS.ready(key, acc):
            continue
        resp = client.request("MKCOL", quote("/dav/" + acc, safe="/"))
        if resp.status_code in (201, 301, 405):
            _DIRS.mark(key, acc)
        else:
            log.warning("webdav mkcol %s -> HTTP %s", acc, resp.status_code)


class WebDavBackend:
    def upload(self, st: Storage, data: bytes, filename: str,
               remote_folder: str) -> str:
        folder = _upload_folder(st.root_dir, remote_folder)
        # 网盘驱动(115 等)偶发对瞬时高频 PUT 返回 405/429/5xx,
        # 退避重试两次,避免单张抖动让整个任务失败(断点续传会跳过已成功的)。
        # 网络异常(超时/连接中断,如实测容器重启瞬间)同样可重试 —— 否则
        # 一次抖动就把整个任务判死, 断点续传失去意义。
        last: httpx.Response | None = None
        for attempt in range(3):
            if attempt:
                time.sleep(_RETRY_DELAYS[attempt - 1])
            with _client(st) as client:
                _ensure_dirs(client, st, folder)
                try:
                    last = client.put(_dav_path(st.root_dir, remote_folder, filename),
                                      content=data)
                except httpx.HTTPError:
                    if attempt == 2:
                        raise
                    log.warning("webdav upload %s network error (attempt %d), retrying",
                                filename, attempt + 1)
                    continue
            if last.status_code in (200, 201, 204):
                # WebDAV 不会改文件名, 返回 root/relative 约定路径
                return "/".join(p for p in (folder, filename) if p)
            if last.status_code not in _RETRYABLE:
                break
        code = last.status_code if last is not None else 0
        body = last.text[:200] if last is not None else ""
        raise StorageError(
            f"上传失败 HTTP {code}: {body}"
            + ("(根目录需包含挂载名,如 /123云盘/WebDav/PhotoBook)"
               if code == 404 else ""))

    def delete_batch(self, st: Storage, remote_paths: list[str]) -> None:
        """逐个 DELETE(WebDAV 无批量删除; 404 视为已删)。

        这是目录级删除的兜底路径 —— 目录里混进了快照之外的文件、或服务端
        不支持集合删除时才会走到这里, 所以保持串行, 由调用方并发分批。
        """
        if not remote_paths:
            return
        with _client(st) as client:
            for rp in remote_paths:
                resp = client.delete(quote("/dav/" + rp.lstrip("/"), safe="/"))
                if resp.status_code not in (200, 204, 404):
                    log.warning("webdav delete %s -> HTTP %s", rp, resp.status_code)

    # ---- TreeBackend -----------------------------------------------------

    def list_sizes(self, st: Storage, remote_dir: str) -> dict[str, int] | None:
        """PROPFIND Depth:1 列目录: {名字: 字节数}, 子目录 -1。"""
        folder = (remote_dir or "").strip("/")
        if not folder:
            return {}
        url = quote("/dav/" + folder, safe="/")
        with _client(st) as client:
            resp = client.request("PROPFIND", url, headers={"Depth": "1"})
        if resp.status_code == 404:
            return {}
        if resp.status_code not in (200, 207):
            log.warning("webdav propfind %s -> HTTP %s", folder, resp.status_code)
            return None
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            log.warning("webdav propfind %s -> invalid xml", folder)
            return None
        self_path = "/dav/" + folder
        out: dict[str, int] = {}
        for node in root.findall(f"{_DAV}response"):
            href = _href_path(node.findtext(f"{_DAV}href") or "")
            if not href or href == self_path:
                continue  # 目录自身
            name = href.rsplit("/", 1)[-1]
            if not name:
                continue
            prop = node.find(f"{_DAV}propstat/{_DAV}prop")
            if prop is None:
                continue
            rtype = prop.find(f"{_DAV}resourcetype")
            if rtype is not None and rtype.find(f"{_DAV}collection") is not None:
                out[name] = -1
                continue
            raw = prop.findtext(f"{_DAV}getcontentlength") or ""
            out[name] = int(raw) if raw.strip().isdigit() else -1
        return out

    def delete_dir(self, st: Storage, remote_dir: str,
                   allowed: set[str] | None = None) -> bool:
        """DELETE 整个集合(RFC 4918 递归) —— 1 次请求删完整本写真集。"""
        folder = (remote_dir or "").strip("/")
        if not folder:
            return False
        if allowed is not None:
            listing = self.list_sizes(st, folder)
            if listing is None:
                return False  # 列不出来就不敢盲删
            unexpected = [n for n in listing if n not in allowed]
            if unexpected:
                log.info("webdav dir delete skipped: %s has %d unexpected entries",
                         folder, len(unexpected))
                return False
        with _client(st) as client:
            resp = client.delete(quote("/dav/" + folder, safe="/"))
        if resp.status_code in (200, 204, 404):
            _DIRS.forget(dir_cache_key(st), folder)
            return True
        # 207 / 5xx = 部分删除失败, 交给逐文件兜底(它会重试未被删掉的)
        log.warning("webdav delete dir %s -> HTTP %s", folder, resp.status_code)
        return False

    def public_url(self, st: Storage, remote_path: str) -> str:
        base = st.api_url.strip().rstrip("/")
        if base.endswith("/dav"):
            base = base[:-4]
        # 中文/[]()/空格等必须 percent-encode,否则浏览器请求或 Location 头会坏
        return quote(f"{base}/d/{remote_path.lstrip('/')}", safe="/:")

    def test_connection(self, st: Storage) -> str:
        root = _dav_path(st.root_dir, "")
        with _client(st) as client:
            resp = client.request("PROPFIND", root, headers={"Depth": "0"})
        if resp.status_code in (207, 200):
            return f"连接成功,根目录 {st.root_dir or '/'} 可访问"
        if resp.status_code == 401:
            raise StorageError("认证失败: WebDAV 用户名或密码错误")
        if resp.status_code == 404:
            raise StorageError(
                f"根目录不存在: {st.root_dir or '/'}"
                "(WebDAV 路径需包含挂载名,如 /123云盘/WebDav/PhotoBook)")
        raise StorageError(f"连接失败 HTTP {resp.status_code}: {resp.text[:200]}")


def _href_path(href: str) -> str:
    """PROPFIND 的 href → 解码后的绝对路径(去掉域名与尾斜杠)。"""
    if not href:
        return ""
    path = urlparse(href).path or href
    return unquote(path).rstrip("/")
