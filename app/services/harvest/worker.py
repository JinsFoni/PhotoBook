"""采集 Worker — 串行队列消费者 + APScheduler 定时扫描。

对内只暴露:scan_once() / enqueue_manual(url) / worker(后台线程)。
队列本体是 harvest_jobs 表,单线程消费,保证同一时间只有一个任务。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .. import settings_store
from ...db import HarvestHistory, HarvestJob
from ...database import SessionLocal
from . import net, pipeline
from .filters import check_title

log = logging.getLogger("harvest")

_stop = threading.Event()
_thread: threading.Thread | None = None
_scan_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


# ---- 队列操作 ---------------------------------------------------------------

def enqueue(s, serial: int, url: str, source: str = "auto") -> HarvestJob | None:
    """入队(历史去重 + 排队去重)。返回新任务或 None。"""
    if s.get(HarvestHistory, serial):
        return None
    exists = s.scalar(select(HarvestJob).where(HarvestJob.serial == serial,
                                               HarvestJob.status.in_(["queued", "parsing", "downloading", "extracting"])))
    if exists:
        return None
    job = HarvestJob(serial=serial, url=url, source=source, status="queued")
    s.add(job)
    s.flush()
    return job


def enqueue_manual(url: str) -> tuple[bool, str]:
    """手动提交详情页 URL。返回 (ok, message)。消息按当前请求语言翻译。"""
    from urllib.parse import urlparse
    from ...i18n import t

    host = urlparse(url).netloc.lower()
    if "buondua.com" not in host:
        return False, t("仅支持 buondua.com 详情页链接")
    try:
        serial = net._serial_from_url(url)
    except ValueError as e:
        return False, str(e)
    s = SessionLocal()
    try:
        if s.get(HarvestHistory, serial):
            return False, t("该写真(序号 {s})已处理过", s=serial)
        job = enqueue(s, serial, url, source="manual")
        if not job:
            return False, t("任务已在队列中")
        return True, t("已加入队列(序号 {s})", s=serial)
    finally:
        s.commit()
        s.close()


# ---- 扫描 -------------------------------------------------------------------

def scan_once(pages: int | None = None) -> dict:
    """扫一轮列表页 → 新序号入队。返回统计。"""
    with _scan_lock:
        s = SessionLocal()
        stats = {"scanned_pages": 0, "seen": 0, "enqueued": 0, "stopped_early": False}
        try:
            conf = settings_store.harvest_conf(s)
            base = "https://buondua.com"
            max_pages = pages if pages is not None else int(conf["harvest.pages_per_round"])
            start = int(conf.get("harvest.start", 0))
            for _ in range(max_pages):
                url = base + "/" if start == 0 else f"{base}/?start={start}"
                links, _has_next = net.scan_list_page(url)
                stats["scanned_pages"] += 1
                stats["seen"] += len(links)
                new_count = 0
                for serial, path in links:
                    job = enqueue(s, serial, base + path, source="auto")
                    if job:
                        new_count += 1
                stats["enqueued"] += new_count
                # 整页均为已处理 → 提前停止(§29)
                if new_count == 0 and links:
                    stats["stopped_early"] = True
                    break
                if not links:
                    break
                start += 20
            return stats
        except Exception as e:
            log.warning("scan failed: %s", e)
            stats["error"] = str(e)
            return stats
        finally:
            s.commit()
            s.close()


# ---- 任务执行 ---------------------------------------------------------------

def _finish(s, job: HarvestJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.error = error
    job.finished_at = _now()
    s.add(HarvestHistory(serial=job.serial, status=status, title=job.title))


def _run_job(job_id: int) -> None:
    """执行单个任务(独立 session,串行调用)。"""
    s = SessionLocal()
    library_root = None
    archive_tmp = None
    try:
        job = s.get(HarvestJob, job_id)
        if not job or job.status not in ("queued", "failed"):
            return
        job.status = "parsing"
        job.started_at = _now()
        s.commit()

        conf = settings_store.harvest_conf(s)
        library_root = __import__("pathlib").Path(str(conf["library.dir"]))
        library_root.mkdir(parents=True, exist_ok=True)

        # 1. 解析详情页(tag → 模特名,出品方/分类 tag 由排除词跳过)
        detail_html = net.fetch_html(job.url)
        target = net.parse_detail_page(
            job.url, existing_html=detail_html,
            model_exclude=str(conf["harvest.model_exclude"]))
        job.title = target.title
        job.model_name = target.model_name
        s.commit()

        # 2. 标题 + 标签过滤(黑白名单)
        fr = check_title(target.title,
                         str(conf["harvest.whitelist"]), str(conf["harvest.blacklist"]),
                         tags=target.tags)
        if not fr.allowed:
            _finish(s, job, "skipped", f"过滤命中: {fr.keyword}")
            s.commit()
            return

        # 3. 已存在预检:① library 里已有同名目录 ② DB 里已导入过(重试时避免白下 1GB)
        #    (权威判定仍在 archive_collection 的 FileExistsError 与 import_album 的 slug 幂等)
        from .filters import sanitize_path_part
        model_part = sanitize_path_part(target.model_name) if target.model_name else sanitize_path_part(str(conf["harvest.unsorted_dir"]))
        title_part = sanitize_path_part(target.title or f"serial-{job.serial}")
        dest_dir = library_root / model_part / title_part
        if dest_dir.exists() and any(dest_dir.iterdir()):
            _finish(s, job, "exists")
            s.commit()
            return
        from .. import library_import
        if library_import.collection_exists(s, target.model_name, title_part,
                                            str(conf["harvest.unsorted_dir"])):
            _finish(s, job, "exists")
            s.commit()
            return

        # 4. 解析短链 → 直链
        if not target.shortlinks:
            _finish(s, job, "failed", "详情页未找到下载短链")
            s.commit()
            return
        link = target.shortlinks[0]
        direct_page = net.resolve_ouo(link)
        if not direct_page:
            _finish(s, job, "failed", "短链解析失败")
            s.commit()
            return
        info = net.mediafire_info_from_url(direct_page)
        if not info["direct_url"]:
            _finish(s, job, "failed", "未获取到直链")
            s.commit()
            return

        # 5. 下载(流式 + 进度)
        job.status = "downloading"
        job.bytes_total = info["size"]
        s.commit()

        archive_tmp = library_root / "_tmp"
        archive_tmp.mkdir(parents=True, exist_ok=True)
        archive_file = archive_tmp / (info["filename"] or f"{job.serial}.rar")

        def progress(done: int, total: int) -> None:
            job.bytes_done = done
            job.bytes_total = total or job.bytes_total
            try:
                s.commit()
            except Exception:
                s.rollback()

        pipeline.download_stream(info["direct_url"], archive_file,
                                 expected_sha256=info["sha256"],
                                 max_bytes=4 * 1024**3,
                                 on_progress=progress)

        # 6. 解压 + 归档
        work_dir = archive_tmp / f"work-{job.serial}"
        if work_dir.exists():
            import shutil
            shutil.rmtree(work_dir)
        pipeline.extract_archive(archive_file, work_dir, target.password)
        final_dir = pipeline.archive_collection(work_dir, library_root,
                                                model_name=target.model_name,
                                                title=target.title or f"serial-{job.serial}",
                                                unsorted_dir=str(conf["harvest.unsorted_dir"]))
        _finish(s, job, "done")
        file_count = len(list(final_dir.rglob('*')))
        job.error = f"→ {final_dir.name}({file_count} 文件)"
        s.commit()

        # 7. 导入平台(library → media + 建库),导入即 published 立即可见。
        #    导入失败只记状态,不把采集任务判失败(文件仍在 library,可手动重扫)
        try:
            from ...config import settings as app_settings
            from .. import library_import
            r = library_import.import_album(
                s, final_dir, app_settings.media_dir, library_root=library_root,
                unsorted_dir=str(conf["harvest.unsorted_dir"]))
            if r["skipped"]:
                job.error = f"→ {final_dir.name}(已导入过,跳过)"
            else:
                extra = f",跳过 {r['videos']} 个视频" if r["videos"] else ""
                job.error = f"→ {final_dir.name}({r['photos']} 张已入库{extra})"
            s.commit()
        except Exception as e:
            log.exception("import failed for %s", final_dir)
            job = s.get(HarvestJob, job_id)
            if job:
                job.error = f"→ {final_dir.name}(入库失败: {str(e)[:120]})"
                s.commit()
    except FileExistsError:
        job = s.get(HarvestJob, job_id)
        if job:
            _finish(s, job, "exists")
            s.commit()
    except Exception as e:
        log.exception("job %s failed", job_id)
        job = s.get(HarvestJob, job_id)
        if job:
            _finish(s, job, "failed", str(e)[:500])
            s.commit()
    finally:
        # 清理:压缩包与临时工作目录一律删除(不保留)
        import shutil
        try:
            if archive_tmp and archive_tmp.exists():
                for p in archive_tmp.glob("*.part"):
                    p.unlink(missing_ok=True)
                for p in archive_tmp.glob("*.rar"):
                    p.unlink(missing_ok=True)
                for p in archive_tmp.glob("*.zip"):
                    p.unlink(missing_ok=True)
                for d in archive_tmp.glob("work-*"):
                    shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
        s.close()


def _consume_loop() -> None:
    """串行消费:取最早排队任务 → 执行 → 重试逻辑(失败不阻塞队列)。"""
    while not _stop.is_set():
        s = SessionLocal()
        try:
            job = s.scalar(select(HarvestJob)
                           .where(HarvestJob.status == "queued")
                           .order_by(HarvestJob.id).limit(1))
            if not job:
                s.close()
                _stop.wait(timeout=3.0)
                continue
            job_id = job.id
        finally:
            s.commit()
            s.close()
        _run_job(job_id)


def start_worker() -> None:
    """启动后台消费线程 + APScheduler 定时扫描。"""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_consume_loop, name="harvest-worker", daemon=True)
    _thread.start()

    from apscheduler.schedulers.background import BackgroundScheduler

    def scheduled_scan() -> None:
        s = SessionLocal()
        try:
            conf = settings_store.harvest_conf(s)
            if not conf["harvest.enabled"]:
                return
        finally:
            s.close()
        try:
            scan_once()
        except Exception:
            log.exception("scheduled scan failed")

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(scheduled_scan, "interval",
                  hours=6, id="harvest-scan",
                  next_run_time=datetime.now(timezone.utc))
    # 动态周期:每次触发后按配置重排
    def _reschedule() -> None:
        s = SessionLocal()
        try:
            conf = settings_store.harvest_conf(s)
            hours = float(conf["harvest.interval_hours"])
        finally:
            s.close()
        job = sched.get_job("harvest-scan")
        if job and abs(job.trigger.interval.total_seconds() - hours * 3600) > 1:
            job.reschedule(trigger="interval", hours=hours)

    sched.add_job(_reschedule, "interval", minutes=5, id="harvest-resched")
    sched.start()
    log.info("harvest worker started (interval=%sh)", 6)


def stop_worker() -> None:
    _stop.set()


def worker_running() -> bool:
    return bool(_thread and _thread.is_alive())
