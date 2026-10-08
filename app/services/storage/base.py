"""外部存储抽象 — 按 Storage.type 分发到具体 backend 实现。

backend 只做纯 HTTP 交互,不碰 DB;队列/进度/记录在 worker.py。
新增存储类型:实现 StorageBackend 并注册进 BACKENDS。
"""

from __future__ import annotations

import logging
from typing import Protocol

from ...db import Storage

log = logging.getLogger("pb.storage")


class StorageError(Exception):
    """上传/删除等远端操作失败(消息可直接展示)。"""


class StorageBackend(Protocol):
    def upload(self, st: Storage, data: bytes, filename: str,
               remote_folder: str) -> str:
        """上传单个文件(内容已读入内存,多存储分发共享同一份数据)到远端
        目录,返回远端相对路径(/file/ 后那段)。

        remote_folder 已含根目录,如 "PhotoBook/一色雨/coser@xxx"。
        文件名可能被远端改名(加前缀),必须用返回值,不得自行拼接。
        """
        ...

    def delete_batch(self, st: Storage, remote_paths: list[str]) -> None:
        """批量删除远端文件;整体失败抛 StorageError,部分失败记日志。"""
        ...

    def public_url(self, st: Storage, remote_path: str) -> str:
        """远端文件的公开访问 URL。"""
        ...

    def test_connection(self, st: Storage) -> str:
        """连通性测试,返回人类可读结果;失败抛 StorageError。"""
        ...


def get_backend(st: Storage) -> StorageBackend:
    impl = BACKENDS.get(st.type)
    if not impl:
        raise StorageError(f"未知存储类型: {st.type}")
    return impl()


BACKENDS: dict[str, type] = {}

try:
    from . import imgbed as _imgbed
    BACKENDS["imgbed"] = _imgbed.ImgBedBackend
    from . import webdav as _webdav
    BACKENDS["webdav"] = _webdav.WebDavBackend
except Exception:  # pragma: no cover — 依赖缺失不应拖垮主程序
    log.exception("storage backend load failed")
