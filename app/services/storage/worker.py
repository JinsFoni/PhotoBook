"""上传 Worker — DB 表作队列(upload_jobs),daemon 线程按组并行消费。

参照 harvest worker 模式:
- 队列本体是 upload_jobs 表,重启不丢;启动时把 running 重置回 queued。
- 同一写真集的多个存储任务合并成一组执行:逐张读原图到内存,并行分发到
  各存储同时上传(单存储失败只淘汰它自己,其余存储继续)。
- 每个存储在飞上限 UPLOAD_CONCURRENCY 个 PUT: 上传是「一个文件一个请求」,
  WebDAV 与 OpenList 都没有批量上传接口, 并发是唯一能提速的维度。
- 每张成功 commit photos_done + 写 photo_uploads(断点续传依据)。
- 一组传完对远端做一次批量校验(每个目录一次列表),大小不符的重传一次。
- 全部成功后删除本地原图(仅当两档缩略图缓存已在盘,否则保留并记提示);
  随后按"空目录才删"规则清理 media 下的空目录。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ...db import Collection, Photo, PhotoUpload, Storage, UploadJob
from .. import media
from .base import StorageError, TreeBackend, get_backend, verify_uploads

log = logging.getLogger("pb.storage.worker")

_poll_gap = 3.0
_thread: threading.Thread | None = None
_wake = threading.Event()
# 防僵尸线程: 每个正在执行的任务一个 token,过期线程的状态写入会被丢弃
_run_tokens: dict[int, int] = {}

# 每个存储同时在飞的 PUT 数。实测 8 张 ~2MB 图: 123 盘串行 10.1s → 4 路
# 4.6s(2.2x), 115 盘 5.3s → 4.0s(1.3x); 再往上收益递减且容易触发网盘
# 限流(单张耗时抖动本来就大: 236ms ~ 2.1s), 4 路是实测的平衡点。
UPLOAD_CONCURRENCY = 4


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
        except Exception as e:
            if _is_shutdown_error(e):
                # 进程正在退出(容器重启 / compose down): atexit 已经把
                # ThreadPoolExecutor 置成 shutting down, 主线程这时 submit()
                # 必然抛错。这不是任务本身的失败 —— 放回队列, 下次启动续传
                # (photo_uploads 行就是断点, 重跑只补缺的那几张)。
                n = _requeue_jobs(job_ids)
                log.warning("upload group %s 被进程退出打断, %d 个任务已重新排队",
                            job_ids, n)
                return  # executor 已全局关闭, 再循环也没有意义
            log.exception("upload group %s crashed", job_ids)
            for jid in job_ids:
                _fail_job(jid, "内部错误(详见日志)")
        time.sleep(0.1)


# 解释器退出时 concurrent.futures.thread 的 atexit 钩子会先把所有
# ThreadPoolExecutor 置成 shutting down, 之后任何 submit() 都抛这句。
_SHUTDOWN_RUNTIME_ERROR = "cannot schedule new futures after shutdown"


def _is_shutdown_error(e: BaseException) -> bool:
    """这个异常是否只是「进程正在退出」, 而不是任务自身出了问题。"""
    return isinstance(e, RuntimeError) and _SHUTDOWN_RUNTIME_ERROR in str(e)


def _requeue_jobs(job_ids: list[int]) -> int:
    """把被进程退出打断的任务放回队列。返回放回的数量。

    只动还在 `running` 的: 同组里已经 failed(真失败)的保持原状。
    photos_done 不用重置 —— 下一轮开跑时会按 photo_uploads 重算。
    """
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        n = 0
        for jid in job_ids:
            job = s.get(UploadJob, jid)
            if job and job.status == "running":
                job.status, job.error = "queued", None
                n += 1
        s.commit()
        return n
    finally:
        s.close()


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
    """执行同写真集的一组存储任务:每存储最多 UPLOAD_CONCURRENCY 个 PUT 在飞。

    - 照片之间不再串行: 主线程按序读原图并提交上传, 每个存储一条有界在飞
      队列(先进先出), 队满就先收最早的结果 —— 这样内存里最多只有
      「并发数」张原图, 而 4 路并发能把 123 盘的上传时间压到 1/2;
    - DB 只由主线程写(每张成功即 commit), 断点续传语义与串行版一致;
    - 单存储单张失败 → 该存储任务 failed 并退出本组, 其余存储继续;
    - 本地原图缺失 → 仍需要它的存储任务 failed(其余继续);
    - 收尾对每个目录做一次远端校验(大小), 不符的重传一次再判失败。
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

        executor = ThreadPoolExecutor(
            max_workers=max(1, UPLOAD_CONCURRENCY * len(active)),
            thread_name_prefix="upload")
        inflight: dict[int, deque] = {jid: deque() for jid in active}
        uploaded: dict[int, dict[str, tuple[str, int]]] = {jid: {} for jid in active}

        def settle(jid: int) -> None:
            """收掉某存储最早的一个上传结果(写 DB 只发生在这个线程)。"""
            entry = active.get(jid)
            if entry is None:
                inflight[jid].clear()
                return
            j, st, _backend = entry
            if not inflight[jid]:
                return
            p, _name, size, fut = inflight[jid].popleft()
            if _run_tokens.get(jid) != tokens[jid]:
                # 已被新一轮启动取代,停止写该任务状态
                active.pop(jid, None)
                return
            try:
                remote_path = fut.result()
            except Exception as e:
                log.exception("upload failed: %s %s -> %s", c.slug, p.filename, st.name)
                j.status, j.error = "failed", f"上传失败: {e}"
                active.pop(jid, None)
                return
            s.add(PhotoUpload(photo_id=p.id, storage_id=st.id, remote_path=remote_path))
            j.photos_done += 1
            needing[jid].discard(p.id)
            uploaded[jid][remote_path] = (p.filename, size)
            s.commit()

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

            for jid, (_j, st, backend) in targets:
                # 背压: 先收最早的结果腾出名额, 保证每个存储的在飞数不超过上限
                while jid in active and len(inflight[jid]) >= UPLOAD_CONCURRENCY:
                    settle(jid)
                if jid not in active:
                    continue  # 该存储刚失败, 不再为它提交
                inflight[jid].append(
                    (p, local.name, len(data),
                     executor.submit(backend.upload, st, data, local.name, remote_root)))

        for jid in list(inflight):
            while jid in active and inflight[jid]:
                settle(jid)

        # 远端校验: 每个目录一次列表请求, 大小不一致的重传一次
        for jid, (j, st, backend) in list(active.items()):
            if j.status != "running" or not uploaded[jid]:
                continue
            _verify_job(s, st, backend, j, uploaded[jid], remote_root)
        s.commit()  # 校验判失败的状态也要落库

        # 收尾 1: 校验通过的标记完成
        finished: list[tuple[UploadJob, Storage]] = []
        for jid, (j, st, _backend) in list(active.items()):
            if j.status != "running":
                continue
            j.status = "done"
            s.commit()
            finished.append((j, st))
            log.info("upload done: %s -> %s (%d photos)",
                     c.slug, st.name, j.photos_total)

        # 收尾 2: 本组全部落定之后才删本地原图。原图是所有存储共用的唯一
        # 字节来源 —— 只要同写真集还有存储任务排队/在跑/失败, 删掉就补不回
        # 来。实测 123 盘 fs/put 会「回 200 但文件不落地」, 校验判该存储失败,
        # 而另一个存储的收尾已经把原图删了, 只能从备份存储回补。
        for j, st in finished:
            _delete_local_originals(s, st, photos, j)
            s.commit()
    finally:
        if executor:
            executor.shutdown(wait=False)
        s.close()


def _verify_job(s, st: Storage, backend, job: UploadJob,
                files: dict[str, tuple[str, int]], remote_root: str) -> None:
    """校验本次上传的远端文件大小;不符的重传一次,仍不符则判任务失败。

    只支持能列目录的后端(webdav / openlist), 且按目录批量查 —— 一本 300 张
    的写真集只多 1 个 PROPFIND / fs/list 请求, 不是 300 个。
    """
    if not isinstance(backend, TreeBackend) or not files:
        return
    bad = verify_uploads(backend, st, {rp: size for rp, (_rel, size) in files.items()})
    if not bad:
        return
    log.warning("upload verify: %d/%d files mismatched on %s, retrying",
                len(bad), len(files), st.name)
    for rp in list(bad):
        rel, _size = files[rp]
        local = media.abs_path(rel)
        if not local.is_file():
            continue
        try:
            got = backend.upload(st, local.read_bytes(), local.name, remote_root)
        except Exception:
            log.exception("re-upload after verify failed: %s -> %s", rel, st.name)
            continue
        if got != rp:  # 理论上不会(两家都不改名), 保守地把 DB 记录也跟着改
            s.query(PhotoUpload).filter(
                PhotoUpload.storage_id == st.id,
                PhotoUpload.remote_path == rp).update(
                {"remote_path": got}, synchronize_session=False)
            files[got] = files.pop(rp)
    bad = verify_uploads(backend, st, {rp: size for rp, (_rel, size) in files.items()})
    if bad:
        # 校验没过的文件把 photo_uploads 行撤掉: 上传时按 200 就记了行, 但远端
        # 没落地。留着行会让「重试」把它当成已上传直接跳过, 任务变绿而文件仍
        # 然缺 —— 撤行后重试才会真的重传。
        s.query(PhotoUpload).filter(
            PhotoUpload.storage_id == st.id,
            PhotoUpload.remote_path.in_(bad)).delete(synchronize_session=False)
        job.photos_done = max(0, job.photos_done - len(bad))
        job.status = "failed"
        job.error = (f"{len(bad)} 张远端校验失败(大小不一致): "
                     f"{bad[0].rsplit('/', 1)[-1]}")
        log.warning("upload verify failed: %s -> %s (%d files)",
                    job.collection_id, st.name, len(bad))


def _originals_needed(s, job: UploadJob) -> str | None:
    """同写真集还有别的存储任务没成功时, 返回原因(本地原图不能删)。

    原图删了就没了: 上传 123 盘时实测过「fs/put 回 200 但文件没落地」,
    校验判该存储失败, 此时若另一个存储的收尾已经把原图删掉, 这批照片就
    再也没法补传 —— 只能从备份存储把字节捞回来。
    """
    enabled = select(Storage.id).where(Storage.enabled == True)  # noqa: E712
    others = s.scalars(select(UploadJob).where(
        UploadJob.collection_id == job.collection_id,
        UploadJob.id != job.id,
        UploadJob.storage_id.in_(enabled))).all()
    for o in others:
        if o.status == "failed":
            return "其他存储上传失败"
        if o.status in ("queued", "running"):
            return "其他存储任务未完成"
    return None


def _delete_local_originals(s, st, photos: list[Photo], job: UploadJob) -> None:
    """全部上传成功后尝试删本地原图。

    只删满足三个条件的:
    0. 同写真集的其他存储任务都已成功(见 _originals_needed);
    1. 该照片已上传到所有启用的存储(否则排队中的其他存储 job 会拿不到本地文件);
    2. 缩略图缓存(900/2400)已在盘(否则缩略图永远无法再生)。
    不满足的保留本地并在 job.error 里提示。
    """
    reason = _originals_needed(s, job)
    if reason:
        job.error = f"完成,保留本地原图({reason})"
        log.info("keep originals: %s -> %s (%s)", job.collection_id, st.name, reason)
        return

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
