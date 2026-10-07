"""WebDAV backend — 通过标准 WebDAV 服务端上传(实测 OpenList /dav)。

要点(实测确认):
- 管理通道: PUT 上传 / DELETE 删除 / PROPFIND 测试, Basic 认证。
- public_url 拼服务端公开直链 /d/<路径>(OpenList 模式, 302 到源站, 免认证;
  若服务端开启 sign_all 则直链需带签名, 目前不支持, 表单里有提示)。
- 目录规则与 imgbed 相同: root_dir + 本地 media 前两级目录。
- WebDAV 无批量删除, 逐个 DELETE; 单个失败记日志不中断(尽力而为)。
- PUT 前逐级 MKCOL(幂等, 已存在返回 405/301 忽略), 兼容不允许隐式建目录的服务端。
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from ...db import Storage
from .base import StorageError

log = logging.getLogger("pb.storage.webdav")

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


def _upload_folder(root_dir: str, remote_folder: str) -> str:
    """拼最终上传目录: 根目录 + 照片相对目录,整体去掉首尾斜杠。"""
    root = (root_dir or "").strip().strip("/")
    folder = (remote_folder or "").strip().strip("/")
    parts = [p for p in (root, folder) if p]
    return "/".join(parts)


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


class WebDavBackend:
    def upload(self, st: Storage, local_path: Path, remote_folder: str) -> str:
        folder = _upload_folder(st.root_dir, remote_folder)
        with _client(st) as client:
            _mkcol_all(client, folder)
            with local_path.open("rb") as f:
                resp = client.put(_dav_path(st.root_dir, remote_folder,
                                            local_path.name), content=f)
        if resp.status_code not in (200, 201, 204):
            raise StorageError(
                f"上传失败 HTTP {resp.status_code}: {resp.text[:200]}"
                + ("(根目录需包含挂载名,如 /123云盘/WebDav/PhotoBook)"
                   if resp.status_code == 404 else ""))
        # WebDAV 不会改文件名, 返回 root/relative 约定路径
        return "/".join(p for p in (_upload_folder(st.root_dir, remote_folder),
                                    local_path.name) if p)

    def delete_batch(self, st: Storage, remote_paths: list[str]) -> None:
        """WebDAV 无批量删除, 逐个 DELETE(尽力而为, 404 视为已删)。"""
        if not remote_paths:
            return
        with _client(st) as client:
            for rp in remote_paths:
                resp = client.delete(quote("/dav/" + rp, safe="/"))
                if resp.status_code not in (200, 204, 404):
                    log.warning("webdav delete %s -> HTTP %s", rp, resp.status_code)

    def public_url(self, st: Storage, remote_path: str) -> str:
        base = st.api_url.rstrip("/")
        if base.endswith("/dav"):
            base = base[:-4]
        return f"{base}/d/{remote_path}"

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


def _mkcol_all(client: httpx.Client, folder: str) -> None:
    """逐级建目录,尽力而为(OpenList 支持隐式建目录,MKCOL 可省)。

    已存在时 MKCOL 返回 405,与"该层级不可创建"(如挂载根)无法区分,
    因此失败仅记日志,最终以 PUT 结果为准。
    """
    parts = [p for p in folder.split("/") if p]
    path = "/dav"
    for part in parts:
        path = path.rstrip("/") + "/" + part
        resp = client.request("MKCOL", quote(path, safe="/"))
        if resp.status_code not in (201, 405, 301):
            log.warning("webdav mkcol %s -> HTTP %s", path, resp.status_code)
