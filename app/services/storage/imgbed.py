"""CloudFlare ImgBed backend — https://cfbed.sanyue.de/api

要点(实测确认):
- 上传必须带 serverCompress=false,否则 telegram 渠道会对图片做服务端压缩,原图被破坏。
- 返回 [{"src": "<完整链接>"}],文件名会被加时间戳前缀,真实路径以返回值为准。
- 删除走 /api/manage/delete/batch,body {"fileIds": [...]}(相对路径,不含域名)。
- 连通性测试用 /api/manage/list(需要 list 权限的 token;仅 upload 权限时测上传探测)。
"""

from __future__ import annotations

import logging
import re
import uuid

import httpx

from ...db import Storage
from .base import StorageError

log = logging.getLogger("pb.storage.imgbed")

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


def _client(st: Storage) -> httpx.Client:
    if not st.api_url:
        raise StorageError("未配置 API 地址")
    if not st.token:
        raise StorageError("未配置 Token")
    base = st.api_url.rstrip("/")
    return httpx.Client(base_url=base, timeout=_TIMEOUT,
                        headers={"Authorization": f"Bearer {st.token}"})


def _upload_folder(root_dir: str, remote_folder: str) -> str:
    """拼最终上传目录: 根目录 + 照片相对目录,整体去掉首尾斜杠。"""
    root = (root_dir or "").strip().strip("/")
    folder = (remote_folder or "").strip().strip("/")
    parts = [p for p in (root, folder) if p]
    return "/".join(parts)


class ImgBedBackend:
    def upload(self, st: Storage, data: bytes, filename: str,
               remote_folder: str) -> str:
        folder = _upload_folder(st.root_dir, remote_folder)
        with _client(st) as client:
            resp = client.post(
                "/upload",
                params={
                    "uploadChannel": "telegram",
                    "uploadFolder": folder,
                    "serverCompress": "false",
                    "returnFormat": "full",
                },
                files={"file": (filename, data)},
            )
        if resp.status_code != 200:
            raise StorageError(f"上传失败 HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            src = resp.json()[0]["src"]
        except Exception:
            raise StorageError(f"上传返回格式异常: {resp.text[:200]}")
        # src 可能是完整链接或 /file/xxx 路径,统一抽出 /file/ 后的真实路径
        m = re.search(r"/file/(.+)$", src)
        if not m:
            raise StorageError(f"上传返回无法解析: {src[:200]}")
        return m.group(1)

    def delete_batch(self, st: Storage, remote_paths: list[str]) -> None:
        if not remote_paths:
            return
        failed: list[str] = []
        # 单次最多 500 个
        for i in range(0, len(remote_paths), 500):
            chunk = remote_paths[i:i + 500]
            with _client(st) as client:
                resp = client.post("/api/manage/delete/batch",
                                   json={"fileIds": chunk})
            if resp.status_code != 200:
                failed.extend(chunk)
                log.warning("imgbed batch delete HTTP %s: %s",
                            resp.status_code, resp.text[:200])
                continue
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            failed.extend(data.get("failed") or [])
        if failed:
            raise StorageError(f"远端删除失败 {len(failed)} 个文件")

    def public_url(self, st: Storage, remote_path: str) -> str:
        from urllib.parse import quote
        base = st.api_url.rstrip("/")
        # 韩文/[]() 等特殊字符必须 percent-encode(远端路径来自上传返回,原样保留)
        return quote(f"{base}/file/{remote_path}", safe="/:")

    def test_connection(self, st: Storage) -> str:
        import urllib.parse
        root = _upload_folder(st.root_dir, "")
        with _client(st) as client:
            resp = client.get("/api/manage/list",
                              params={"dir": root, "count": 1})
        if resp.status_code == 200 and "files" in (resp.text[:2000] or ""):
            n = "?"
            try:
                n = str(resp.json().get("totalCount", 0))
            except Exception:
                pass
            return f"连接成功,目录 {root or '/'} 下共 {n} 个文件"
        if resp.status_code == 401 or resp.status_code == 403:
            raise StorageError("认证失败: token 无效或缺少 list 权限")
        # list 不可用不代表不能上传 — 用一个 1px 探测图实测上传通道
        return self._probe_upload(st)

    def _probe_upload(self, st: Storage) -> str:
        import io
        import struct
        import uuid
        import zlib

        # 合法 1x1 PNG(逐 chunk 计算 CRC)
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data)))

        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        idat = chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00", 9))
        iend = chunk(b"IEND", b"")
        png = b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend
        probe_name = f"probe_{uuid.uuid4().hex[:8]}.png"
        root = _upload_folder(st.root_dir, "")
        folder = "/".join([p for p in (root, "_probe") if p])
        with _client(st) as client:
            resp = client.post(
                "/upload",
                params={"uploadChannel": "telegram", "uploadFolder": folder,
                        "serverCompress": "false", "returnFormat": "full"},
                files={"file": (probe_name, io.BytesIO(png))},
            )
        if resp.status_code == 200:
            try:
                src = resp.json()[0]["src"]
                m = re.search(r"/file/(.+)$", src)
                if m:
                    # 清理探测文件(尽力而为)
                    try:
                        client.post("/api/manage/delete/batch",
                                    json={"fileIds": [m.group(1)]})
                    except Exception:
                        pass
            except Exception:
                pass
            return "连接成功(list 接口不可用,已实测上传通道)"
        raise StorageError(f"上传探测失败 HTTP {resp.status_code}: {resp.text[:200]}")
