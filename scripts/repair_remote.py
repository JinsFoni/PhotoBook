"""体检 + 修复:DB 记着「已上传」但远端其实没有的文件。

为什么需要:网盘的 fs/put / PUT 会「回 200 但文件不落地」。1.9.0 之前上传后
不做校验, 这类静默丢失在库里留下一批 broken image —— 站点直链 302 到网盘,
文件不在就 404。照片的本地原图在上传成功后已删, 所以唯一的字节来源是**另一
个存储**(通常 115 那份是完整的备份盘)。

做法:按写真集逐目录 list 一次(不是逐文件), 找出缺失项; 缺失项的字节依次
从「本地原图 → 其它存储」取, 校验大小后重新上传到目标存储, 再 list 复核。

用法(容器内):
  PYTHONPATH=/app python scripts/repair_remote.py --dry-run          # 只体检
  PYTHONPATH=/app python scripts/repair_remote.py                    # 修复全部存储
  PYTHONPATH=/app python scripts/repair_remote.py --storage 1        # 只修 123
  PYTHONPATH=/app python scripts/repair_remote.py --collection 13 28 # 只修指定写真集

退出码: 0 = 没有修不回来的缺失; 1 = 有缺失既不在本地、也不在任何备份存储。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from app.db import Photo, PhotoUpload, Storage
from app.database import SessionLocal
from app.services import media
from app.services.storage.base import TreeBackend, get_backend

_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
_MAX_BYTES = 200 * 1024 * 1024  # 单张原图上限, 防呆(最大实测 ~30MB)


def _rel_in_root(st: Storage, remote_path: str) -> str:
    """DB 里的 remote_path → 去掉根目录后的相对路径。"""
    rp = remote_path.strip("/")
    root = (st.root_dir or "").strip().strip("/")
    return rp[len(root) + 1:] if root and rp.startswith(root + "/") else rp


def _list_dirs(backend, st: Storage, dirs: set[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for d in sorted(dirs):
        listing = backend.list_sizes(st, d)
        if listing is None:
            print(f"    !! 列目录失败, 跳过: {d}", flush=True)
            continue
        out[d] = listing
    return out


def _download_from(st: Storage, remote_path: str, expect: int | None) -> bytes | None:
    """用某个存储的公开直链把字节取回来(webdav 需带 Basic 认证)。"""
    backend = get_backend(st)
    url = backend.public_url(st, remote_path)
    headers = {}
    if st.type == "webdav" and st.username:
        import base64
        raw = f"{st.username}:{st.token}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"    !! 取字节失败 HTTP {resp.status_code}: {url[:90]}", flush=True)
            return None
        data = resp.content
    except Exception as e:  # noqa: BLE001
        print(f"    !! 取字节异常: {e}", flush=True)
        return None
    if len(data) > _MAX_BYTES:
        print(f"    !! 文件过大, 不处理: {len(data)}", flush=True)
        return None
    if expect is not None and len(data) != expect:
        print(f"    !! 取回的字节数 {len(data)} != 备份列表 {expect}, 丢弃", flush=True)
        return None
    return data


def _fetch_bytes(s, photo: Photo, target: Storage, remote_path: str,
                 others: list[tuple[Storage, object]]) -> bytes | None:
    """按「本地原图 → 其它存储」的顺序找字节; 返回 None 表示找不到。"""
    local = media.abs_path(photo.filename)
    if local.is_file():
        data = local.read_bytes()
        print(f"    来源=本地原图 ({len(data)} B)", flush=True)
        return data
    for st, backend in others:
        if st.id == target.id:
            continue
        if not isinstance(backend, TreeBackend):
            continue
        row = s.scalar(select(PhotoUpload).where(
            PhotoUpload.photo_id == photo.id, PhotoUpload.storage_id == st.id))
        if row is None:
            continue
        d = "/".join(row.remote_path.strip("/").split("/")[:-1])
        name = row.remote_path.strip("/").rsplit("/", 1)[-1]
        listing = backend.list_sizes(st, d)
        if not listing or name not in listing:
            continue
        data = _download_from(st, row.remote_path, listing[name])
        if data is not None:
            print(f"    来源={st.name} ({len(data)} B)", flush=True)
            return data
    return None


def _audit_storage(s, st: Storage, collection_ids: list[int] | None,
                   dry_run: bool, others: list[tuple[Storage, object]]) -> dict:
    backend = get_backend(st)
    if not isinstance(backend, TreeBackend):
        print(f"[{st.name}] 该类型不支持列目录, 跳过", flush=True)
        return {"dirs": 0, "missing": 0, "repaired": 0, "unrecoverable": 0}
    stats = {"dirs": 0, "missing": 0, "repaired": 0, "unrecoverable": 0}

    rows = s.execute(
        select(Photo.id, Photo.collection_id, Photo.filename, PhotoUpload.remote_path)
        .join(PhotoUpload, PhotoUpload.photo_id == Photo.id)
        .where(PhotoUpload.storage_id == st.id)).all()
    if collection_ids:
        wanted = set(collection_ids)
        rows = [r for r in rows if r.collection_id in wanted]
    if not rows:
        print(f"[{st.name}] 没有上传记录", flush=True)
        return stats

    # 分组用「完整远端目录」(含根目录) —— list_sizes / delete_dir 都吃这个;
    # upload 要的是「不含根目录」的相对路径, 由 _rel_in_root 现算。
    by_dir: dict[str, list[tuple]] = {}
    for r in rows:
        by_dir.setdefault(r.remote_path.strip("/").rpartition("/")[0], []).append(r)

    t0 = time.time()
    for i, (d, items) in enumerate(sorted(by_dir.items()), 1):
        listing = backend.list_sizes(st, d)
        if listing is None:
            print(f"[{st.name}] !! 列目录失败, 跳过: {d}", flush=True)
            continue
        stats["dirs"] += 1
        for pid, cid, filename, remote_path in items:
            name = remote_path.strip("/").rsplit("/", 1)[-1]
            if name in listing:
                continue
            stats["missing"] += 1
            print(f"[{st.name}] 缺 {remote_path}", flush=True)
            if dry_run:
                stats["unrecoverable"] += 1  # dry-run 只报数, 别当真的失败
                continue
            photo = s.get(Photo, pid)
            data = _fetch_bytes(s, photo, st, remote_path, others)
            if data is None:
                stats["unrecoverable"] += 1
                print("    !! 找不到可用字节, 只能人工补", flush=True)
                continue
            remote_root = "/".join(_rel_in_root(st, remote_path).split("/")[:-1])
            try:
                got = backend.upload(st, data, name, remote_root)
            except Exception as e:  # noqa: BLE001
                stats["unrecoverable"] += 1
                print(f"    !! 上传失败: {e}", flush=True)
                continue
            after = backend.list_sizes(st, d) or {}
            if after.get(name) == len(data):
                stats["repaired"] += 1
                print(f"    已修复 ({len(data)} B)", flush=True)
            else:
                stats["unrecoverable"] += 1
                print(f"    !! 复核仍不符(远端 {after.get(name)} != {len(data)})", flush=True)
        if i % 25 == 0:
            print(f"  ... {st.name} {i}/{len(by_dir)} 目录, 缺 {stats['missing']}, "
                  f"修复 {stats['repaired']}, {time.time() - t0:.0f}s", flush=True)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="体检/修复远端缺失文件")
    ap.add_argument("--dry-run", action="store_true", help="只体检, 不写远端")
    ap.add_argument("--storage", type=int, action="append",
                    help="只处理指定存储 id(可多次);默认全部启用存储")
    ap.add_argument("--collection", type=int, action="append",
                    help="只处理指定写真集 id(可多次)")
    args = ap.parse_args(argv)

    s = SessionLocal()
    try:
        all_st = list(s.scalars(select(Storage).where(Storage.enabled == True)).all())  # noqa: E712
        targets = [st for st in all_st if not args.storage or st.id in args.storage]
        if not targets:
            print("没有可处理的存储")
            return 0
        others = [(st, get_backend(st)) for st in all_st]
        total = {"dirs": 0, "missing": 0, "repaired": 0, "unrecoverable": 0}
        for st in targets:
            print(f"\n===== {st.name} (id={st.id}, {st.type}) =====", flush=True)
            got = _audit_storage(s, st, args.collection, args.dry_run, others)
            for k in total:
                total[k] += got[k]
        print(f"\n合计: 目录 {total['dirs']}, 缺失 {total['missing']}, "
              f"修复 {total['repaired']}, 修不回 {total['unrecoverable']}"
              f"{' (dry-run 未写入)' if args.dry_run else ''}")
        return 1 if total["unrecoverable"] and not args.dry_run else 0
    finally:
        s.close()


if __name__ == "__main__":
    raise SystemExit(main())
