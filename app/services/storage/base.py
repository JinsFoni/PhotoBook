"""外部存储抽象 — 按 Storage.type 分发到具体 backend 实现。

backend 只做纯 HTTP 交互,不碰 DB;队列/进度/记录在 worker.py。
新增存储类型:实现 StorageBackend 并注册进 BACKENDS。

能力分两层:
- StorageBackend: 上传 / 逐文件删除 / 直链 / 连通性,所有类型必须实现;
- TreeBackend: 目录枚举 + 整目录删除(webdav / openlist 实现)。远端目录与
  写真集一一对应,整目录删除 = 1 次请求代替 N 次,是「删写真集」的主要加速点。

TreeBackend 的 delete_dir 带 allowed 守卫:先列一次目录,发现快照之外的
文件就拒删(那说明写真集刚被重新导入并上传过),交给调用方逐文件处理。
列表 + 删除都是常数次请求, 通常远快于 N 次单个删除。
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

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


@runtime_checkable
class TreeBackend(Protocol):
    """支持目录枚举与整目录删除的后端(webdav / openlist)。

    上传目录 = 根目录 + 写真集的两级相对目录,与写真集一一对应,
    所以删写真集时按目录删,请求数从「张数」降到「1」。
    """

    def list_sizes(self, st: Storage, remote_dir: str) -> dict[str, int] | None:
        """列远端目录: {文件名: 字节数},子目录记 -1;目录不存在返回 {}。

        列表本身失败(服务端抖动/不支持)返回 None —— 调用方按
        「不可校验 / 不可安全删目录」处理,不要当成空目录。
        """
        ...

    def delete_dir(self, st: Storage, remote_dir: str,
                   allowed: set[str] | None = None) -> bool:
        """一次请求删掉整个目录(含内容)。

        allowed 非空时先列目录,发现 allowed 之外的文件就拒删并返回 False
        —— 删写真集是后台异步的,期间同一本写真集可能被重新导入并上传,
        照单全删会把新文件一起删掉。返回 True 表示目录已不存在或已删净。
        """
        ...


# ---- 目录已创建缓存(MKCOL / fs/mkdir 去重) ----------------------------------
#
# 一次 MKCOL / fs/mkdir 在该服务端上并不便宜: 实测 115 盘建一级目录 2.6s,
# 123 盘 1.2s, 而一本写真集的每一张照片上传前都得确认目录存在。进程内记下
# 「已建好」的目录, 命中即 0 请求。键含存储配置(api_url/root_dir), 改配置
# 自然失效; 删掉目录后 forget() 连子孙一起清掉。


class CreatedDirs:
    def __init__(self, limit: int = 50000):
        self._lock = threading.Lock()
        self._sets: dict[tuple, set[str]] = {}
        self._count = 0
        self._limit = limit

    def ready(self, key: tuple, folder: str) -> bool:
        with self._lock:
            return folder in self._sets.get(key, ())

    def mark(self, key: tuple, folder: str) -> None:
        """记下 folder 及其所有祖先(它们必然也建好了)。"""
        parts = [p for p in folder.split("/") if p]
        if not parts:
            return
        with self._lock:
            s = self._sets.get(key)
            if s is None:
                s = self._sets[key] = set()
            acc = ""
            for part in parts:
                acc = f"{acc}/{part}" if acc else part
                if acc not in s:
                    s.add(acc)
                    self._count += 1
            if self._count > self._limit:  # 极端情况:整体清空,重新学习
                self._sets.clear()
                self._count = 0

    def forget(self, key: tuple, folder: str) -> None:
        """目录被删后失效,连子孙一起(下次上传重新建)。"""
        with self._lock:
            s = self._sets.get(key)
            if not s:
                return
            prefix = folder.rstrip("/") + "/"
            for p in [x for x in s if x == folder or x.startswith(prefix)]:
                s.discard(p)
                self._count -= 1


def dir_cache_key(st: Storage) -> tuple:
    return (st.id, (st.api_url or "").rstrip("/"), (st.root_dir or "").strip("/"))


def join_folder(root_dir: str, remote_folder: str) -> str:
    """拼最终上传目录: 根目录 + 照片相对目录,整体去掉首尾斜杠。"""
    root = (root_dir or "").strip().strip("/")
    folder = (remote_folder or "").strip().strip("/")
    parts = [p for p in (root, folder) if p]
    return "/".join(parts)


def split_by_dir(remote_paths: list[str]) -> dict[str, list[str]]:
    """按父目录分组: {远端目录: [文件名, ...]}。"""
    out: dict[str, list[str]] = {}
    for rp in remote_paths:
        rp = rp.strip("/")
        if not rp:
            continue
        d, _, name = rp.rpartition("/")
        if name:
            out.setdefault(d, []).append(name)
    return out


def verify_uploads(backend, st: Storage, expected: dict[str, int]) -> list[str]:
    """批量校验远端文件大小, 返回不一致的远端路径。

    每个目录只列一次(不是每张一次), 所以正常情况下一本写真集只多花 1 个请求。
    列表失败时跳过该目录(记日志), 不把服务端抖动误判成文件缺失。
    """
    if not isinstance(backend, TreeBackend) or not expected:
        return []
    bad: list[str] = []
    for d, files in split_by_dir(list(expected)).items():
        listing = backend.list_sizes(st, d)
        if listing is None:
            log.warning("verify skipped, cannot list %s", d)
            continue
        for name in files:
            rp = f"{d}/{name}" if d else name
            if listing.get(name) != expected[rp]:
                bad.append(rp)
    return bad


BACKENDS: dict[str, type] = {}

# 各 backend 的模块/类名。延迟到第一次 get_backend 才导入 —— backend 模块
# 自己会 import base, 若在 base 模块末尾直接 import 它们, 而调用方恰好先
# import 了某个 backend, 就会撞上「半初始化模块」的循环导入。
_BACKEND_SPECS = (
    ("imgbed", ".imgbed", "ImgBedBackend"),
    ("openlist", ".openlist", "OpenListBackend"),
    ("webdav", ".webdav", "WebDavBackend"),
)
_loaded = False
_load_lock = threading.Lock()


def _load_backends() -> None:
    global _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        import importlib

        for name, mod, cls in _BACKEND_SPECS:
            if name in BACKENDS:
                continue
            try:
                BACKENDS[name] = getattr(importlib.import_module(mod, __package__), cls)
            except Exception:  # pragma: no cover — 依赖缺失不应拖垮主程序
                log.exception("storage backend load failed: %s", name)
        _loaded = True


def get_backend(st: Storage) -> StorageBackend:
    _load_backends()
    impl = BACKENDS.get(st.type)
    if not impl:
        raise StorageError(f"未知存储类型: {st.type}")
    return impl()
