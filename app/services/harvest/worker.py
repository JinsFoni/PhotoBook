"""采集 Worker — 串行队列消费者 + APScheduler 定时扫描。

对内只暴露:scan_once() / enqueue_manual(url) / worker(后台线程)。
队列本体是 harvest_jobs 表,单线程消费,保证同一时间只有一个任务。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from pathlib import Path

from .. import media, settings_store
from ...db import Collection, HarvestHistory, HarvestJob
from ...database import SessionLocal
from . import net, pipeline
from .filters import check_title

log = logging.getLogger("harvest")

_stop = threading.Event()
_thread: threading.Thread | None = None
_watchdog: threading.Thread | None = None

# 进行中任务进度停滞判定阈值(秒): 超过则视为卡死, 重置回 queued 重跑。
# 断点续传已下载部分不白费(.part 保留, download_stream 自动 Range 续传)。
STALE_SECONDS = 30 * 60

# 任务运行所有权: job_id -> token。看门狗重置卡死任务时删除记录,
# 僵尸线程(卡死后网络复通)复苏后 token 不匹配, 不得写终态/清文件,
# 避免覆盖新运行的状态或误删新运行的 .part。
_run_tokens: dict[int, str] = {}

_scan_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


# ---- 队列操作 ---------------------------------------------------------------

# 未落终态的任务状态(浏览器联动判定「下载中」也用它)
ACTIVE_JOB_STATES = ("queued", "parsing", "downloading", "extracting")


def enqueue(s, serial: int, url: str, source: str = "auto") -> HarvestJob | None:
    """入队(历史去重 + 排队去重)。返回新任务或 None。"""
    if s.get(HarvestHistory, serial):
        return None
    exists = s.scalar(select(HarvestJob).where(HarvestJob.serial == serial,
                                               HarvestJob.status.in_(ACTIVE_JOB_STATES)))
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
    # 历史表 serial 为主键: 同一任务二次 _finish(如 done 后 import 失败改判 failed)
    # 用合并写入, 保留最新状态
    s.merge(HarvestHistory(serial=job.serial, status=status, title=job.title))


def _run_job(job_id: int) -> None:
    """执行单个任务(独立 session,串行调用)。

    token = 运行所有权。看门狗发现进度停滞会撤销 token 并把任务重置回
    queued —— 卡死线程多半阻塞在网络读上, join 不动, 只能放任它挂着;
    旧线程若之后复苏, token 不匹配, 不得写终态或清理文件
    (此时新运行可能已在跑同一任务)。
    """
    token = uuid.uuid4().hex
    _run_tokens[job_id] = token
    s = SessionLocal()
    library_root = None
    archive_tmp = None
    serial: int | None = None
    archive_files: list[Path] = []     # 压缩包落点(下载开始前赋值, 分卷多个)
    archive_done = False               # 只有下载完整结束才允许删包
    try:
        job = s.get(HarvestJob, job_id)
        if not job or job.status not in ("queued", "failed"):
            return
        serial = job.serial
        job.status = "parsing"
        job.started_at = _now()
        job.updated_at = job.started_at
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

        # 4. 解析短链 → 直链。分卷压缩会挂多条短链(标题带 "1 / 2"),
        #    必须全下,只下第一卷解压必缺卷;任一卷解析失败整任务失败
        #    (缺卷的包解出来也是废的,不值得半成品)
        if not target.shortlinks:
            _finish(s, job, "failed", "详情页未找到下载短链")
            s.commit()
            return
        infos = []
        for link in target.shortlinks:
            try:
                direct_page = net.resolve_ouo(link)
            except net.UnsupportedHostError as e:
                _finish(s, job, "failed", str(e))
                s.commit()
                return
            if not direct_page:
                _finish(s, job, "failed", f"短链解析失败: {link}")
                s.commit()
                return
            if net.MF_FOLDER_RE.search(direct_page):
                # 落地是 MediaFire 文件夹(分卷包发布方把所有卷放一夹): API 展开逐卷
                folder_files = net.mediafire_folder_files(direct_page)
                if not folder_files:
                    _finish(s, job, "failed", f"文件夹为空: {direct_page}")
                    s.commit()
                    return
                infos.extend(folder_files)
                continue
            info = net.mediafire_info_from_url(direct_page)
            if not info["direct_url"]:
                _finish(s, job, "failed", f"未获取到直链: {info['filename']}")
                s.commit()
                return
            infos.append(info)

        # 5. 逐卷下载(流式 + 进度 + 断点续传)。进度跨卷累加:
        #    bytes_done = 前面各卷已下字节数 + 当前卷进度
        job.status = "downloading"
        job.bytes_total = sum(i["size"] for i in infos)
        s.commit()

        archive_tmp = library_root / "_tmp"
        archive_tmp.mkdir(parents=True, exist_ok=True)
        archive_files = [archive_tmp / (i["filename"] or f"{job.serial}-{n}.rar")
                         for n, i in enumerate(infos)]
        done_offset = 0  # 已完整落盘的卷累计字节数(进度跨卷累加)

        def progress(done: int, total: int) -> None:
            job.bytes_done = done_offset + done
            job.bytes_total = total or job.bytes_total
            job.updated_at = _now()
            try:
                s.commit()
            except Exception:
                s.rollback()

        for info, archive_file in zip(infos, archive_files):
            # 上次跑到后段失败: 已完整落盘的卷直接复用(大小核对), 不重下
            if archive_file.exists() and info["size"] \
                    and archive_file.stat().st_size == info["size"]:
                done_offset += info["size"]
                continue
            pipeline.download_stream(info["direct_url"], archive_file,
                                     expected_sha256=info["sha256"],
                                     max_bytes=4 * 1024**3,
                                     on_progress=progress,
                                     stream_key=job_id)
            done_offset += archive_file.stat().st_size
        archive_done = True  # 全部卷 SHA256 已过, 此后失败可删包(失败重试会重新下载)

        # 6. 解压 + 归档。多卷包(RAR .part1.rar / 7z .001 / zip 分卷)从
        #    首卷解; 首卷选择: 命中已知首卷特征的优先, 否则按文件名排序取第一
        def _volume_key(p: Path):
            name = p.name.lower()
            for rank, pat in enumerate((".part1.rar", ".part01.rar", ".001",
                                        ".zip", ".7z", ".rar")):
                if name.endswith(pat):
                    return rank, name
            return 99, name

        work_dir = archive_tmp / f"work-{job.serial}"
        if work_dir.exists():
            import shutil
            shutil.rmtree(work_dir)
        pipeline.extract_archive(min(archive_files, key=_volume_key),
                                 work_dir, target.password)
        final_dir = pipeline.archive_collection(work_dir, library_root,
                                                model_name=target.model_name,
                                                title=target.title or f"serial-{job.serial}",
                                                unsorted_dir=str(conf["harvest.unsorted_dir"]))
        _finish(s, job, "done")
        file_count = len(list(final_dir.rglob('*')))
        job.error = f"→ {file_count} 个文件"
        s.commit()

        # 7. 导入平台(library → media + 建库)。导入后写真置 processing
        #    (前台不可见),缩略图队列生成 900/2400 两档后才翻转 published。
        #    导入失败 → 任务判 failed 并记录归档残留路径:删除该任务时
        #    会连带清理(残留未入库, 不删就是孤儿);重试也能走 failed 重跑路径
        try:
            from ...config import settings as app_settings
            from .. import library_import
            r = library_import.import_album(
                s, final_dir, app_settings.media_dir, library_root=library_root,
                unsorted_dir=str(conf["harvest.unsorted_dir"]),
                tags=target.tags, thumbs=False)
            if r["skipped"]:
                job.error = "→ 已导入过,跳过"
            else:
                extra = f",跳过 {r['videos']} 个视频" if r["videos"] else ""
                job.collection_slug = r["slug"]
                # 序号落到写真集上: 浏览器联动脚本按 source_serial 精确判定「已入库」
                col = s.scalar(select(Collection).where(Collection.slug == r["slug"]))
                if col is not None:
                    col.source_serial = job.serial
                s.commit()  # 先落库释放写锁: queue_import_thumbs 用独立连接写状态
                nq = media.queue_import_thumbs(r["slug"])
                job = s.get(HarvestJob, job_id)
                broken = r.get("broken") or []
                extra += f",损坏跳过 {len(broken)} 张" if broken else ""
                job.error = f"→ {r['photos']} 张已入库{extra},缩略图生成中#{nq}"
            s.commit()
        except Exception as e:
            log.exception("import failed for %s", final_dir)
            job = s.get(HarvestJob, job_id)
            if job:
                _finish(s, job, "failed", f"→ 入库失败: {str(e)[:80]}")
                # 残留目录记录到任务上, 删除 failed 任务时一并清理
                job.archive_dir = str(final_dir)
                s.commit()
    except FileExistsError:
        if _run_tokens.get(job_id) == token:  # 僵尸线程不得写终态
            job = s.get(HarvestJob, job_id)
            if job:
                _finish(s, job, "exists")
                s.commit()
    except Exception as e:
        if _run_tokens.get(job_id) == token:
            log.exception("job %s failed", job_id)
            job = s.get(HarvestJob, job_id)
            if job:
                _finish(s, job, "failed", str(e)[:500])
                s.commit()
        else:
            # 看门狗已重置本任务(解堵 close 引发的异常属预期): 静默退出
            log.warning("job #%s: stale thread exception ignored (token revoked): %s",
                        job_id, str(e)[:120])
    finally:
        # 清理本次运行产物: work 目录一律删; 压缩包只在下载完整后才删
        # (中断的包删了就白下, 重试还能续传)。*.part 一律保留 — 失败重试的
        # 断点续传基础, 孤儿由 _prune_tmp 按期兑底。旧版在这里无差别 glob
        # 删除, 把续传功能静默废掉了(#127 391MB 白下)。
        # 僵尸防护: token 已被看门狗撤销 → 新运行可能正在跑同一任务,
        # 旧线程不得清理(*.part / 半截包是新运行的续传基础)。
        if _run_tokens.get(job_id) == token:
            try:
                _cleanup_run(archive_tmp, serial,
                             archive_files if archive_done else [])
                _prune_tmp(archive_tmp or (library_root / "_tmp" if library_root else None))
            except Exception:
                pass
            _run_tokens.pop(job_id, None)
        else:
            log.warning("job #%s: stale thread exited, cleanup skipped", job_id)
        s.close()


def _cleanup_run(archive_tmp, serial: int | None,
                 archive_files: list[Path]) -> None:
    """清理一次任务运行的产物(仅本任务的, 不碰其他任务的续传文件)。

    - work-{serial} 目录: 一律删(解压产物, 归档后已无价值)
    - 本任务下载完的压缩包(含全部分卷): 删(已入库, 留着只占空间)
    - *.part / 未完成包: 保留 — 重试的断点续传基础
    """
    import shutil
    if not archive_tmp:
        return
    if serial is not None:
        shutil.rmtree(archive_tmp / f"work-{serial}", ignore_errors=True)
    for f in archive_files:
        f.unlink(missing_ok=True)


def _prune_tmp(archive_tmp) -> None:
    """_tmp 孤儿兑底: 只清无主的工作目录(>7 天)与零字节 .part。

    目录名里的运行标记(work-<serial>)不带时间, 用目录 mtime 判岁数;
    有主(存在对应任务记录且运行中)的绝不碰。保留一切可续传的 .part。
    """
    import shutil
    if not archive_tmp:
        return
    s = SessionLocal()
    try:
        active_serials = set(s.scalars(select(HarvestJob.serial).where(
            HarvestJob.status.in_(ACTIVE_JOB_STATES))).all())
    finally:
        s.close()
    now = datetime.now(timezone.utc).timestamp()
    try:
        for d in archive_tmp.glob("work-*"):
            try:
                mtime = d.stat().st_mtime
            except OSError:
                continue
            if d.name not in {f"work-{x}" for x in active_serials} and now - mtime > 7 * 86400:
                shutil.rmtree(d, ignore_errors=True)
        for p in archive_tmp.glob("*.part"):
            try:
                if p.stat().st_size == 0:
                    p.unlink(missing_ok=True)
            except OSError:
                continue
    except Exception:
        log.exception("prune _tmp failed")


def _recover_and_watchdog() -> None:
    """启动恢复 + 空闲看门狗, 防「downloading 永久卡住」两类场景:

    ① 启动时上次运行未完成(容器重启/进程被杀) → 进行中任务重置回 queued。
       在 start_worker 里启动时同步执行一次。
    ② 运行中 worker 线程意外死亡(如 iter_content 阻塞超时未生效) →
       消费循环里周期执行: updated_at 超时未更新的进行中任务重置回 queued。
    """
    s = SessionLocal()
    try:
        stale = sys.modules[__name__].STALE_SECONDS  # 运行时可调(测试缩短)
        cutoff = datetime.now(timezone.utc).timestamp() - stale
        rows = s.scalars(select(HarvestJob).where(
            HarvestJob.status.in_(ACTIVE_JOB_STATES))).all()
        reset: list[int] = []
        for job in rows:
            ref = job.updated_at or job.started_at or job.created_at
            if ref is not None and ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)  # SQLite 存的是 naive UTC
            if ref is None or ref.timestamp() < cutoff:
                reset.append(job.id)
        for job_id in reset:
            job = s.get(HarvestJob, job_id)
            if job is None:
                continue
            job.status = "queued"
            job.error = "进度停滞/上次运行中断, 自动重新排队(已下载部分续传)"
            s.commit()
            # 解堵: close 卡死线程阻塞中的下载流(实测能立刻抛异常退出)
            pipeline.close_stream(job_id)
            # 撤销所有权: 卡死的旧线程复苏后不得再碰这个任务
            _run_tokens.pop(job_id, None)
            log.warning("watchdog reset job #%s (%s) -> queued", job_id, job.serial)
        if rows and not reset:
            log.info("watchdog: %d active job(s) healthy", len(rows))
    except Exception:
        log.exception("watchdog pass failed")
    finally:
        s.close()


def _consume_loop() -> None:
    """串行消费:取最早排队任务 → 执行 → 重试逻辑(失败不阻塞队列)。

    看门狗在独立线程(_watchdog_loop)运行: _run_job 同步阻塞在本循环里,
    下载线程卡死时循环自身冻结, 内嵌看门狗永远轮不到执行(1.0.26 缺陷)。
    """
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


def _watchdog_loop() -> None:
    """独立看门狗线程: 每 60s 扫描一次进度停滞的活动任务。

    与消费循环分离 —— 下载线程卡死会把 _run_job/消费循环一起冻结,
    看门狗必须有自己的线程才能真正执行到(任务 #1 事故教训)。
    """
    while not _stop.wait(timeout=60.0):
        _recover_and_watchdog()


def start_worker() -> None:
    """启动后台消费线程 + 看门狗线程 + APScheduler 定时扫描。

    消费线程无条件启动(手动提交的任务要随时处理);
    定时扫描仅在 HARVEST_ENABLED=1 时注册(后台「定时扫描开启」开关仍逐轮生效)。
    """
    global _thread, _watchdog
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    # 上次运行遗留的进行中任务(容器重启/被杀): 立即恢复回 queued,
    # .part 断点续传, 已下载部分不白费
    _recover_and_watchdog()
    _thread = threading.Thread(target=_consume_loop, name="harvest-worker", daemon=True)
    _thread.start()
    _watchdog = threading.Thread(target=_watchdog_loop, name="harvest-watchdog", daemon=True)
    _watchdog.start()

    from ...config import settings
    if not settings.harvest_enabled:
        log.info("harvest worker started (scheduled scan disabled by HARVEST_ENABLED)")
        return

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
