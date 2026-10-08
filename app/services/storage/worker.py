"""上传 Worker — DB 表作队列(upload_jobs),daemon 线程按组并行消费。

参照 harvest worker 模式:
- 队列本体是 upload_jobs 表,重启不丢;启动时把 running 重置回 queued。
- 同一写真集的多个存储任务合并成一组执行: 逐张读原图到内存,并行分发到
  各存储同时上传(单存储失败只淘汰它自己,其余存储继续)。
- 每张成功 commit photos_done + 写 photo_uploads(断点续传依据)。
- 全部成功后删除本地原图(仅当两档缩略图缓存已在盘,否则保留并记提示);
  随后按"空目录才删"规则清理 media 下的空目录。
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ...db import Collection, Photo, PhotoUpload, Storage, UploadJob
from .. import media
from .base import StorageError, get_backend

log = logging.getLogger("pb.storage.worker")

_poll_gap = 3.0
_thread: threading.Thread | None = None
_wake = threading.Event()
# 防僵尸线程: 每个正在执行的任务一个 token,过期线程的状态写入会被丢弃
_run_tokens: dict[int, int] = {}


def ensure_worker() -> None:
    """启动上传 worker(daemon)。幂等。"""
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_consume_loop, name="upload-worker", daemon=True)
    _thread.start()


def recover_stuck_running() -> int:
    """启动自愈:把 running 任务重置回 queued。返回重置数量。"""
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        jobs = s.scalars(select(UploadJob).where(UploadJob.status == "running")).all()
        for j in jobs:
            j.status = "queued"
            _run_tokens.pop(j.id, None)
        s.commit()
        n = len(jobs)
    except Exception:
        s.rollback()
        log.exception("recover upload jobs failed")
        return 0
    finally:
        s.close()
    if n:
        log.warning("recovered %d stuck upload job(s)", n)
        _wake.set()
    return n


def enqueue_collection(collection_id: int, storage_ids: list[int]) -> int:
    """为写真集 × 每个存储建上传任务(queued),返回新建数量。

    已有活跃/完成任务且照片未变化的重复入队是安全的: worker 对已上传过的
    照片直接跳过(photo_uploads 唯一约束),total 只统计缺的部分。
    """
    from ...database import SessionLocal

    if not storage_ids:
        return 0
    s = SessionLocal()
    created = 0
    try:
        c = s.get(Collection, collection_id)
        if not c:
            return 0
        total = len(c.photos)
        if total == 0:
            return 0
        for sid in storage_ids:
            if not s.get(Storage, sid):
                continue
            active = s.scalar(select(UploadJob).where(
                UploadJob.collection_id == collection_id,
                UploadJob.storage_id == sid,
                UploadJob.status.in_(("queued", "running"))))
            if active:
                continue
            job = UploadJob(collection_id=collection_id, storage_id=sid,
                            status="queued", photos_total=total)
            s.add(job)
            created += 1
        s.commit()
    finally:
        s.close()
    if created:
        ensure_worker()
        _wake.set()
    return created


def _consume_loop() -> None:
    while True:
        from ...database import SessionLocal

        job_ids: list[int] = []
        s = SessionLocal()
        try:
            first = s.scalar(select(UploadJob).where(UploadJob.status == "queued")
                             .order_by(UploadJob.id).limit(1))
            if first is None:
                s.close()
                _wake.wait(timeout=_poll_gap)
                _wake.clear()
                continue
            # 同一写真集的所有 queued 存储任务合并成一组,按张并行分发
            jobs = s.scalars(select(UploadJob).where(
                UploadJob.status == "queued",
                UploadJob.collection_id == first.collection_id)
                .order_by(UploadJob.id)).all()
            for j in jobs:
                j.status = "running"
                job_ids.append(j.id)
            s.commit()
        finally:
            s.close()
        try:
            _run_group(job_ids)
        except Exception:
            log.exception("upload group %s crashed", job_ids)
            for jid in job_ids:
                _fail_job(jid, "内部错误(详见日志)")
        time.sleep(0.1)


def _fail_job(job_id: int, error: str) -> None:
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        job = s.get(UploadJob, job_id)
        if job and job.status == "running":
            job.status = "failed"
            job.error = error
            s.commit()
    finally:
        s.close()


def _run_group(job_ids: list[int]) -> None:
    """执行同写真集的一组存储任务:逐张读原图,并行分发到各存储同时上传。

    - 单存储单张失败 → 该存储任务 failed 并退出本组,其余存储继续;
    - 每张成功即 commit(photo_uploads + photos_done),断点续传不受影响;
    - 本地原图缺失 → 仍需要它的存储任务 failed(其余继续)。
    """
    from ...database import SessionLocal

    s = SessionLocal()
    executor: ThreadPoolExecutor | None = None
    try:
        jobs = {j.id: j for j in s.query(UploadJob).filter(
            UploadJob.id.in_(job_ids or [0]),
            UploadJob.status == "running").all()}
        if not jobs:
            return
        tokens = {jid: _run_tokens.get(jid, 0) + 1 for jid in jobs}
        _run_tokens.update(tokens)

        c = s.get(Collection, next(iter(jobs.values())).collection_id)
        if not c:
            for j in jobs.values():
                j.status, j.error = "failed", "写真集已不存在"
            s.commit()
            return
        photos = list(c.photos)
        if not photos:
            for j in jobs.values():
                j.status, j.error = "failed", "写真集没有照片"
            s.commit()
            return

        # 校验各存储与 backend,无效的任务直接 failed
        active: dict[int, tuple[UploadJob, Storage, object]] = {}
        for jid, j in jobs.items():
            st = s.get(Storage, j.storage_id)
            if not st:
                j.status, j.error = "failed", "存储已不存在"
            elif not st.enabled:
                j.status, j.error = "failed", "存储已被停用"
            else:
                try:
                    active[jid] = (j, st, get_backend(st))
                except StorageError as e:
                    j.status, j.error = "failed", str(e)
        s.commit()
        if not active:
            return

        # remote_folder = <模特slug>/<写真目录>,即 photo.filename 的前两级
        parts = photos[0].filename.split("/")
        remote_root = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]

        # 每存储的断点续传基线: 已上传过的照片直接跳过
        needing: dict[int, set[int]] = {}  # job_id -> 待上传 photo_id 集合
        for jid, (j, st, _backend) in active.items():
            done_ids = set(s.scalars(select(PhotoUpload.photo_id).where(
                PhotoUpload.storage_id == st.id,
                PhotoUpload.photo_id.in_([p.id for p in photos] or [0]))).all())
            j.photos_total = len(photos)
            j.photos_done = len(done_ids)
            j.error = None
            needing[jid] = {p.id for p in photos} - done_ids
        s.commit()

        executor = ThreadPoolExecutor(max_workers=len(active),
                                      thread_name_prefix="upload")
        for p in photos:
            if not active:
                break
            targets = [(jid, entry) for jid, entry in active.items()
                       if p.id in needing[jid]]
            if not targets:
                continue
            local = media.abs_path(p.filename)
            if not local.is_file():
                # 原图本地已删但远端记录缺失: 无法补传,涉及的存储任务失败
                for jid, (j, _st, _backend) in targets:
                    j.status, j.error = "failed", f"本地原图缺失: {p.filename}"
                    del active[jid]
                s.commit()
                continue
            data = local.read_bytes()

            futures = {jid: executor.submit(backend.upload, st, data,
                                            local.name, remote_root)
                       for jid, (_j, st, backend) in targets}
            for jid, fut in futures.items():
                entry = active.get(jid)
                if entry is None:
                    continue
                j, st, _backend = entry
                if _run_tokens.get(jid) != tokens[jid]:
                    # 已被新一轮启动取代,停止写该任务状态
                    del active[jid]
                    continue
                try:
                    remote_path = fut.result()
                except Exception as e:
                    log.exception("upload failed: %s %s -> %s",
                                  c.slug, p.filename, st.name)
                    j.status, j.error = "failed", f"上传失败: {e}"
                    del active[jid]
                    continue
                s.add(PhotoUpload(photo_id=p.id, storage_id=st.id,
                                  remote_path=remote_path))
                j.photos_done += 1
                needing[jid].discard(p.id)
            s.commit()

        # 收尾: 仍存活的任务尝试删本地原图并标记完成
        for jid, (j, st, _backend) in list(active.items()):
            if j.status != "running":
                continue
            _delete_local_originals(s, st, photos, j)
            j.status = "done"
            s.commit()
            log.info("upload done: %s -> %s (%d photos)",
                     c.slug, st.name, j.photos_total)
    finally:
        if executor:
            executor.shutdown(wait=False)
        s.close()


def _delete_local_originals(s, st, photos: list[Photo], job: UploadJob) -> None:
    """全部上传成功后尝试删本地原图。

    只删满足两个条件的:
    1. 该照片已上传到所有启用的存储(否则排队中的其他存储 job 会拿不到本地文件);
    2. 缩略图缓存(900/2400)已在盘(否则缩略图永远无法再生)。
    不满足的保留本地并在 job.error 里提示。
    """
    enabled_ids = s.scalars(select(Storage.id).where(Storage.enabled == True)).all()  # noqa: E712
    photo_ids = [p.id for p in photos]
    # photo_id -> 已上传的存储数
    counts: dict[int, int] = {}
    for pid, in s.query(PhotoUpload.photo_id).filter(
            PhotoUpload.storage_id.in_(enabled_ids or [0]),
            PhotoUpload.photo_id.in_(photo_ids or [0])).all():
        counts[pid] = counts.get(pid, 0) + 1

    kept = 0
    for p in photos:
        if counts.get(p.id, 0) < len(enabled_ids):
            kept += 1
            continue
        if not media.thumb_cache_ready(p.filename):
            kept += 1
            continue
        local = media.abs_path(p.filename)
        if not local.is_file():
            continue  # 已被同组其他存储任务的收尾删除,不算保留
        try:
            local.unlink()
        except OSError:
            kept += 1
    media.cleanup_empty_dirs(photos[0].filename if photos else "")
    if kept:
        job.error = (f"完成,{kept} 张保留本地原图"
                     f"(还有其他存储队列未完成,或缩略图缓存缺失)")
        log.info("upload done with %d kept: %s -> %s", kept, job.collection_id, st.name)


# ---- 供 serve_media / 删除联动使用的查询辅助 ---------------------------------

def remote_paths_of_collection(collection_id: int, storage_id: int) -> list[str]:
    """一个写真集在某存储上的全部远端路径(删除联动用)。"""
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        rows = s.execute(
            select(PhotoUpload.remote_path)
            .join(Photo, Photo.id == PhotoUpload.photo_id)
            .where(Photo.collection_id == collection_id,
                   PhotoUpload.storage_id == storage_id)).scalars().all()
        return list(rows)
    finally:
        s.close()
