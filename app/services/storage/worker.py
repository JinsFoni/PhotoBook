"""上传 Worker — DB 表作队列(upload_jobs),daemon 线程串行消费。

参照 harvest worker 模式:
- 队列本体是 upload_jobs 表,重启不丢;启动时把 running 重置回 queued。
- 逐张上传,每张成功 commit photos_done + 写 photo_uploads(断点续传依据)。
- 全部成功后删除本地原图(仅当两档缩略图缓存已在盘,否则保留并记提示);
  随后按"空目录才删"规则清理 media 下的空目录。
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select

from ...db import Collection, Photo, PhotoUpload, Storage, UploadJob
from .. import media, settings_store
from .base import StorageError, get_backend

log = logging.getLogger("pb.storage.worker")

_poll_gap = 3.0
_thread: threading.Thread | None = None
_wake = threading.Event()
# 防僵尸线程: 每个正在执行的 job 一个 token,过期线程的状态写入会被丢弃
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

        job_id = None
        s = SessionLocal()
        try:
            job = s.scalar(select(UploadJob).where(UploadJob.status == "queued")
                           .order_by(UploadJob.id).limit(1))
            if job is None:
                s.close()
                _wake.wait(timeout=_poll_gap)
                _wake.clear()
                continue
            job_id = job.id
            job.status = "running"
            s.commit()
        finally:
            s.close()
        try:
            _run_job(job_id)
        except Exception:
            log.exception("upload job %s crashed", job_id)
            _fail_job(job_id, "内部错误(详见日志)")
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


def _run_job(job_id: int) -> None:
    """执行单个上传任务。逐张上传,单张失败即终止(可重试,已传的跳过)。"""
    from ...database import SessionLocal

    token = _run_tokens.get(job_id, 0) + 1
    _run_tokens[job_id] = token

    s = SessionLocal()
    try:
        job = s.get(UploadJob, job_id)
        if not job or job.status != "running":
            return
        c = s.get(Collection, job.collection_id)
        st = s.get(Storage, job.storage_id)
        if not c or not st:
            job.status = "failed"
            job.error = "写真集或存储已不存在"
            s.commit()
            return
        if not st.enabled:
            job.status = "failed"
            job.error = "存储已被停用"
            s.commit()
            return
        photos = list(c.photos)
        try:
            backend = get_backend(st)
        except StorageError as e:
            job.status = "failed"
            job.error = str(e)
            s.commit()
            return

        done_before = s.query(PhotoUpload).filter(
            PhotoUpload.storage_id == st.id,
            PhotoUpload.photo_id.in_([p.id for p in photos] or [0])).count()
        job.photos_total = len(photos)
        job.photos_done = done_before
        job.error = None
        s.commit()

        slug = c.slug
        # remote_folder = <模特slug>/<写真目录>,即 photo.filename 的前两级
        remote_root = ""
        if photos:
            parts = photos[0].filename.split("/")
            remote_root = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]

        for p in photos:
            if _run_tokens.get(job_id) != token:
                return  # 已被新一轮启动取代,停止写状态
            exists = s.query(PhotoUpload).filter(
                PhotoUpload.photo_id == p.id,
                PhotoUpload.storage_id == st.id).first()
            if exists:
                continue
            local = media.abs_path(p.filename)
            if not local.is_file():
                # 原图本地已删但远端记录缺失: 无法补传,标记失败
                job.status = "failed"
                job.error = f"本地原图缺失: {p.filename}"
                s.commit()
                return
            try:
                remote_path = backend.upload(st, local, remote_root)
            except Exception as e:
                log.exception("upload failed: %s %s", slug, p.filename)
                job.status = "failed"
                job.error = f"上传失败: {e}"
                s.commit()
                return
            s.add(PhotoUpload(photo_id=p.id, storage_id=st.id,
                              remote_path=remote_path))
            job.photos_done += 1
            s.commit()

        _delete_local_originals(s, st, photos, job)
        if job.status == "running":
            job.status = "done"
            s.commit()
            log.info("upload done: %s -> %s (%d photos)",
                     slug, st.name, job.photos_total)
    finally:
        s.close()


def _delete_local_originals(s, st, photos: list[Photo], job: UploadJob) -> None:
    """全部上传成功后删本地原图。

    只删缩略图缓存(900/2400)已在盘的: 缓存缺失的图保留本地,否则缩略图
    永远无法再生成(灯箱/下载已由 serve_media 302 兜底,不受影响)。
    缓存缺失即失败判定过严会永不删盘,这里选择保留 + error 提示。
    """
    kept = 0
    for p in photos:
        if not media.thumb_cache_ready(p.filename):
            kept += 1
            continue
        try:
            media.abs_path(p.filename).unlink()
        except OSError:
            kept += 1
    media.cleanup_empty_dirs(photos[0].filename if photos else "")
    if kept:
        job.error = f"完成,但 {kept} 张因缩略图缓存缺失保留本地原图"


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
