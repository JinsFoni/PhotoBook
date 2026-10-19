"""PikPak Worker — 串行队列消费者。

与 harvest worker 的差异: 直链已由油猴脚本解析好, 本模块不抓详情页、
不解短链, 直接下载。写盘结构沿用 harvest 的约定:
``<library>/<模特名>/<写真标题>/<文件>`` —— 「一个勾选项就是一个写真集」,
模特名与 tag 由脚本推送(不解析详情页, 见用户 2026-10 决定)。

PikPak 勾选的文件夹本身就是写真集(文件夹里是写真图片), 所以脚本把勾选项
递归展开成文件清单连同直链一起推过来: worker 逐个下载到同一个写真目录,
子目录结构原样保留; 勾选项是压缩包时也要解压归档(见 _run_job)。

队列本体是 pikpak_jobs 表(一行 = 一个勾选项) + pikpak_files(该勾选项展开
后的文件直链), 单线程消费, 同一时间只有一个写真集在下载。
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from ...db import HarvestJob, PikPakFile, PikPakJob
from ...database import SessionLocal
from .. import library_import, media, settings_store
from ..harvest import pipeline
from ..harvest.filters import sanitize_path_part

log = logging.getLogger("pikpak")

_stop = threading.Event()
_thread: threading.Thread | None = None
_watchdog: threading.Thread | None = None

# 未落终态的任务状态(浏览器联动判定「下载中」也用它)
ACTIVE_JOB_STATES = ("queued", "downloading", "extracting")

# 看门狗停滞阈值(秒): 超过则重置回 queued 重跑。断点续传不白费。
STALE_SECONDS = 30 * 60

# 这些后缀一律按压缩包处理(下载后解压归档, 不解压就当普通文件归档)
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".001"}

# 任务运行所有权: job_id -> token。看门狗重置卡死任务时删除记录,
# 僵尸线程(卡死后网络复通)复苏后 token 不匹配, 不得写终态/清文件。
_run_tokens: dict[int, str] = {}

# 单个文件大小上限(8G): 写真相册不会有比这更大的单张图
MAX_FILE_BYTES = 8 * 1024**3

# 图片目录下载并发数: PikPak CDN 按连接限速(~0.9MB/s/连接, 2026-10 实测,
# 多路可线性叠加), 4 路已把一本写真压到 ~2 分钟; 再高收益小且可能触发限流
DOWNLOAD_CONCURRENCY = 4

# 单文件尝试次数: PikPak CDN 会随机 reset 连接(同一链接实测单次成功率约四成,
# 与并发无关), 一次失败不代表文件不可达。小步退避重试, 否则一本写真会
# 残缺入库(换 IP/节点不可控, 重试是最省事的兜底)。
DOWNLOAD_ATTEMPTS = 8
RETRY_BACKOFF = 0.4     # 秒, 第 n 次重试等待 min(RETRY_BACKOFF*n, 2)

# 下载走 harvest.proxy(设置里为空则直连)。PikPak CDN 直连会随机 reset TLS
# 连接(实测单次成功率约四成), 经代理稳定得多 —— 用户 2026-10 确认。
PIKPAK_USE_PROXY = True


def _now():
    return datetime.now(timezone.utc)


def _tags_from_job(job: PikPakJob) -> list[str]:
    """tags 列(逗号分隔) → 显示名列表。"""
    if not job.tags:
        return []
    return [t.strip() for t in job.tags.split(",") if t.strip()]


# ---- 入队 -------------------------------------------------------------------

def enqueue_batch(items: list[dict], *, model_name: str = "",
                  tags: list[str] | None = None) -> tuple[int, int, str]:
    """批量入队。items: [{file_id, name, files:[{file_id, url, rel, size}], size}]。

    items 里的每一项 = 用户在 PikPak 上勾选的一个文件或文件夹(files 是该勾选项
    展开后的直链清单; 压缩包/单文件也走 files, 只有一个元素)。
    model_name / tags 是整批共享的脚本配置(PikPak 勾选项没有模特名信息,
    由用户手填; 空 = 未分类)。返回 (入队数, 跳过数, batch_id)。
    同 file_id 已在队列/已下载 → 跳过(去重)。
    """
    tags_text = ",".join(t.strip() for t in (tags or []) if t.strip())
    batch_id = uuid.uuid4().hex
    s = SessionLocal()
    added = skipped = 0
    try:
        for it in items:
            file_id = (it.get("file_id") or it.get("id") or "").strip()
            if not file_id:
                skipped += 1
                continue
            # 已入队(未终态) → 跳过
            exist = s.scalar(select(PikPakJob.id).where(
                PikPakJob.file_id == file_id,
                PikPakJob.status.in_(ACTIVE_JOB_STATES)).limit(1))
            if exist:
                skipped += 1
                continue
            # 已下载过(终态里已有这个勾选项)→ 不重复入队
            done = s.scalar(select(PikPakJob.id).where(
                PikPakJob.file_id == file_id).limit(1))
            if done:
                skipped += 1
                continue
            files = it.get("files") or []
            clean = []
            for f in files:
                url = (f.get("url") or "").strip()
                if not url:
                    continue
                clean.append({
                    "file_id": (f.get("file_id") or f.get("id") or "").strip()[:64],
                    "url": url[:2000],
                    "rel": (f.get("rel") or f.get("name") or "").strip()[:500],
                    "size": int(f.get("size") or 0),
                })
            if not clean:
                # 勾选项没带任何可用直链(脚本没解析出来)→ 不入队
                skipped += 1
                continue
            name = (it.get("name") or file_id or "pikpak")[:255]
            is_archive = _looks_like_archive(clean) or _looks_like_archive_by_name(name)
            job = PikPakJob(
                batch_id=batch_id,
                name=name,
                file_id=file_id[:64],
                is_archive=is_archive,
                size=sum(f["size"] for f in clean),
                model_name=(model_name or "").strip()[:120] or None,
                tags=tags_text[:500] or None,
                status="queued",
                files_total=len(clean),
            )
            s.add(job)
            s.flush()
            s.add_all([PikPakFile(job_id=job.id, **f) for f in clean])
            added += 1
        s.commit()
        return added, skipped, batch_id
    finally:
        s.close()


def _looks_like_archive(files: list[dict]) -> bool:
    """展开后的清单本身是压缩包(根层就一个压缩文件)。"""
    if len(files) != 1:
        return False
    return Path(files[0]["rel"]).suffix.lower() in ARCHIVE_SUFFIXES


def _looks_like_archive_by_name(name: str) -> bool:
    return Path(name).suffix.lower() in ARCHIVE_SUFFIXES


# ---- 任务执行 ---------------------------------------------------------------

def _finish(s, job: PikPakJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.error = error
    job.finished_at = _now()


def _album_root(s, job: PikPakJob, library_root: Path) -> Path:
    """写真目录: <library>/<模特名>/<写真标题>/。

    标题取勾选项名(文件夹名 / 压缩包名), 与 harvest 的 archive_collection
    口径一致: 模特名缺失时落未分类目录。
    """
    conf = settings_store.harvest_conf(s)
    model_part = sanitize_path_part(job.model_name) if job.model_name \
        else sanitize_path_part(str(conf["harvest.unsorted_dir"]))
    return library_root / model_part / sanitize_path_part(job.name)


def _album_has_content(album_dir: Path) -> bool:
    """写真目录里是否真的有文件。

    不能用 any(iterdir()): 下载失败时已经把 rel 里的子目录 mkdir 出来了,
    空目录会让预检误判「已存在」, 一张图都没下到的任务反而被标 done。
    """
    return album_dir.exists() and any(
        p.is_file() for p in album_dir.rglob("*")
        if not p.name.startswith(".") and p.name not in ("Thumbs.db", ".DS_Store"))


def _skip_if_imported(s, job: PikPakJob, album_dir: Path,
                      *, resumed: bool = False) -> str | None:
    """已归档过 / 已导入过 → 返回跳过理由, 否则 None。

    resumed=True 表示上次运行中断后重跑。此时目录里的文件是半成品,
    不能据此判定「整包已存在」—— 否则剩余文件永远补不齐, 任务还会被
    误标 done(容器重启/看门狗重置后实测)。
    """
    if not resumed and _album_has_content(album_dir):
        _settle_pending_files(s, job.id)
        return "→ 已存在,跳过"
    conf = settings_store.harvest_conf(s)
    if library_import.collection_exists(
            s, job.model_name or "", job.name,
            str(conf["harvest.unsorted_dir"])):
        _settle_pending_files(s, job.id)
        return "→ 已导入过,跳过"
    return None


def _settle_pending_files(s, job_id: int) -> None:
    """整包跳过的任务: 把还没下载的文件行一并标记, 不留「永远排队」的孤儿。"""
    s.query(PikPakFile).where(
        PikPakFile.job_id == job_id,
        PikPakFile.status == "queued").update({"status": "done"})
    s.commit()


def _run_job(job_id: int) -> None:
    """执行单个任务(独立 session,串行调用)。

    token = 运行所有权, 见 harvest.worker._run_job 同款注释。
    """
    token = uuid.uuid4().hex
    _run_tokens[job_id] = token
    s = SessionLocal()
    library_root: Path | None = None
    album_dir: Path | None = None
    archive_file: Path | None = None
    try:
        job = s.get(PikPakJob, job_id)
        if not job or job.status != "queued":
            return
        # started_at 有值 = 不是首次运行(中断续跑/看门狗重置/手动重推)
        resumed = job.started_at is not None
        job.status = "downloading"
        job.started_at = _now()
        # 重跑会重新过一遍全部文件行(已落盘的直接跳过), 计数按本轮从 0 起,
        # 否则多轮重试后 files_done 会累积到 files_total 的几倍。
        job.files_done = 0
        job.updated_at = job.started_at
        s.commit()

        conf = settings_store.harvest_conf(s)
        library_root = Path(str(conf["library.dir"]))
        library_root.mkdir(parents=True, exist_ok=True)
        unsorted = str(conf["harvest.unsorted_dir"])

        album_dir = _album_root(s, job, library_root)
        reason = _skip_if_imported(s, job, album_dir, resumed=resumed)
        if reason:
            _finish(s, job, "done", reason)
            s.commit()
            return

        files = s.scalars(select(PikPakFile).where(PikPakFile.job_id == job_id)
                          .order_by(PikPakFile.id)).all()
        if not files:
            _finish(s, job, "failed", "→ 推送的文件直链已丢失")
            s.commit()
            return

        job.bytes_total = sum(f.size or 0 for f in files) or int(job.size or 0)
        s.commit()

        if job.is_archive:
            # 压缩包: 下到 _tmp → 解压 → 归档(沿用 harvest 的解压密码候选)
            archive_file = _download_archive(s, job, files[0], library_root, token)
            job = s.get(PikPakJob, job_id)
            if job is None:
                return
            job.status = "extracting"
            job.updated_at = _now()
            s.commit()
            work_dir = archive_tmp_of(library_root) / f"work-{job_id}"
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
            src_dir = _extract(archive_file, work_dir)
            final_dir = pipeline.archive_collection(
                src_dir, library_root,
                model_name=job.model_name or "",
                title=job.name,
                unsorted_dir=unsorted)
        else:
            # 图片目录: 逐个下载到写真目录, 子目录结构按 rel 原样保留,
            # 不建 archive_tmp 中间层(直链是一次性的, 不做续盘复用)
            _download_files(s, job, files, album_dir, token)
            job = s.get(PikPakJob, job_id)
            if job is None:
                return
            final_dir = album_dir
            if not _album_has_content(final_dir):
                # 一张图都没下到(直链过期/失效)→ 判失败, 重推时会重新解析直链
                failed = s.query(PikPakFile).where(
                    PikPakFile.job_id == job_id,
                    PikPakFile.status == "failed").count()
                _finish(s, job, "failed",
                        f"→ {failed} 个文件全部下载失败")
                s.commit()
                return

        _finish(s, job, "done")
        s.commit()

        # 导入平台(library → media + 建库), tag 由脚本推送
        _import_album(s, job, final_dir, library_root, unsorted, token)
    except FileExistsError:
        if _run_tokens.get(job_id) == token:
            job = s.get(PikPakJob, job_id)
            if job:
                _finish(s, job, "done", "→ 已存在,跳过")
                s.commit()
    except Exception as e:
        if _run_tokens.get(job_id) == token:  # 僵尸线程不得写终态
            log.exception("pikpak job %s failed", job_id)
            job = s.get(PikPakJob, job_id)
            if job:
                _finish(s, job, "failed", str(e)[:500])
                s.commit()
        else:
            # 看门狗已重置本任务(解堵 close 引发的异常属预期): 静默退出
            log.warning("pikpak job #%s: stale thread exception ignored (token revoked): %s",
                        job_id, str(e)[:120])
    finally:
        if _run_tokens.get(job_id) == token:
            try:
                _cleanup_run(library_root, job_id, archive_file)
                _prune_tmp(archive_tmp_of(library_root) if library_root else None)
                _prune_empty_album(library_root, album_dir)
            except Exception:
                pass
            _run_tokens.pop(job_id, None)
        s.close()


def archive_tmp_of(library_root: Path | None) -> Path | None:
    return (library_root / "_tmp") if library_root else None


def _download_archive(s, job: PikPakJob, f: PikPakFile, library_root: Path,
                      token: str) -> Path:
    """下载单个压缩包到 _tmp 并返回路径(断点续传)。"""
    archive_tmp = archive_tmp_of(library_root)
    archive_tmp.mkdir(parents=True, exist_ok=True)
    dest = archive_tmp / (f.rel or job.name or f"pikpak-{job.id}")
    # stream_key = job_id(单文件任务无并发冲突): 看门狗重置时 close 解堵
    prog = _Progress(job.id, token, base_bytes=int(job.bytes_done or 0),
                     total_bytes=int(f.size or job.bytes_total or 0))
    prev = {"n": int(job.bytes_done or 0)}

    def on_prog(done, total):
        prog.report(prev["n"], done, total)
        prev["n"] = done

    pipeline.download_stream(f.url, dest,
                             max_bytes=MAX_FILE_BYTES,
                             on_progress=on_prog,
                             stream_key=job.id,
                             use_proxy=PIKPAK_USE_PROXY)
    prog.finish()
    job = s.get(PikPakJob, job.id)
    if job:
        job.files_done = 1
        s.commit()
    return dest


def _extract(archive: Path, work_dir: Path) -> Path:
    """解压; 解压失败(密码不对/格式不符)时退回普通文件归档, 不判失败。"""
    try:
        pipeline.extract_archive(archive, work_dir, "")
        return work_dir
    except Exception as e:
        log.warning("pikpak extract failed, 按普通文件归档: %s", str(e)[:150])
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir


class _Progress:
    """跨下载线程的字节进度聚合 + 降频落库。

    每个下载线程持有自己的「本流上次已报字节」, 回调把绝对字节数涨量报进来;
    聚合后若距上次落库超过 FLUSH_EVERY(~1MB), 用独立短 session 写一次
    pikpak_jobs.bytes_done/bytes_total —— 调用线程的 session 可能正被
    其它线程使用, 不能在回调里碰。
    """

    FLUSH_EVERY = 1024 * 1024   # 落库间隔: 1MB(串行时代是逐 512KB 一 commit)

    def __init__(self, job_id: int, token: str, base_bytes: int, total_bytes: int):
        self._job_id = job_id
        self._token = token
        self._lock = threading.Lock()
        self._done = base_bytes          # 已落盘字节(含跳过的存量)
        self._total = max(total_bytes, base_bytes)
        self._flushed_at = base_bytes    # 上次落库时的 done 值

    def report(self, prev: int, done: int, total: int) -> None:
        """本流字节数从 prev 涨到 done(流内绝对值)。

        bytes_total 由 _run_job 预计算好(_Progress 构造时已带), 回调的
        total(单流, 且可能为 0=未知)只用来兜底抬升, 不会拉低。
        """
        with self._lock:
            self._done += max(0, done - prev)
            if total and total > self._total:
                self._total = total
        if done - self._flushed_at >= self.FLUSH_EVERY:
            self.flush()

    def flush(self) -> None:
        if _run_tokens.get(self._job_id) != self._token:
            return
        with self._lock:
            if self._done - self._flushed_at < self.FLUSH_EVERY:
                return
            self._flushed_at = self._done
        s = SessionLocal()
        try:
            job = s.get(PikPakJob, self._job_id)
            if job is not None:
                job.bytes_done = self._done
                job.bytes_total = max(job.bytes_total or 0, self._total)
                job.updated_at = _now()
                s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

    def finish(self) -> None:
        """单文件完成时强制落库一次(不受间隔限制)。"""
        with self._lock:
            self._flushed_at = self._done - self.FLUSH_EVERY
        self.flush()


def _download_files(s, job: PikPakJob, files: list[PikPakFile], album_dir: Path,
                    token: str) -> None:
    """并发(DOWNLOAD_CONCURRENCY 路)下载到写真目录, 子目录结构按 rel 保留。

    PikPak CDN 按连接限速(~0.9MB/s), 多路可线性提速 —— 一本 130 张的
    写真从 ~7 分钟降到 ~2 分钟。已完成/已存在的文件直接跳过(断点重跑;
    单张图几 MB, .part 续传价值不大, 按目标文件存在判定)。

    并发安全:
    - SQLAlchemy session 非线程安全 —— 外层 s 在下载期间只读不写;
      job/files 行的更新全部走各线程自己的短 session;
    - files_done/bytes_done 由锁保护的计数器汇总, 降频落库;
    - stream_key 带 file_id 后缀, 看门狗可按前缀关掉本任务全部在途流。
    """
    album_dir.mkdir(parents=True, exist_ok=True)

    # 预检存量: 已存在文件的大小直接计入 bytes_done 底数
    done_bytes = 0
    for f in files:
        dest = _safe_join(album_dir, (f.rel or f.file_id or "").strip())
        if dest is not None and dest.exists() and dest.stat().st_size > 0:
            done_bytes += dest.stat().st_size
    prog = _Progress(job.id, token, base_bytes=done_bytes,
                     total_bytes=int(job.bytes_total or 0))

    lock = threading.Lock()
    queue: list[tuple[int, PikPakFile]] = list(enumerate(files))
    take = {"i": 0}          # 队列游标(锁内推进)

    def mark_file(f_id: int, status: str, error: str | None) -> None:
        s2 = SessionLocal()
        try:
            s2.execute(update(PikPakFile)
                       .where(PikPakFile.id == f_id)
                       .values(status=status, error=error))
            s2.commit()
        except Exception:
            s2.rollback()
        finally:
            s2.close()

    def complete_one() -> None:
        # files_done 用原子 UPDATE 递增 — 各线程短 session 的「读-改-写」
        # 会互相覆盖(后提交的旧值盖掉先提交的新值, 实测 6 个文件随机丢到 2)
        s2 = SessionLocal()
        try:
            if _run_tokens.get(job.id) == token:
                s2.execute(update(PikPakJob)
                           .where(PikPakJob.id == job.id)
                           .values(files_done=PikPakJob.files_done + 1,
                                   updated_at=_now()))
                s2.commit()
        except Exception:
            s2.rollback()
        finally:
            s2.close()
        prog.finish()   # 单文件收尾: 强制进度落库一次

    def worker() -> None:
        while _run_tokens.get(job.id) == token:
            with lock:
                idx = take["i"]
                if idx >= len(queue):
                    return
                take["i"] = idx + 1
            i, f = queue[idx]
            rel = (f.rel or f.file_id or f"file-{i}").strip() or f"file-{i}"
            dest = _safe_join(album_dir, rel)
            if dest is None:
                # 路径穿越(rel 含 .. 或绝对路径)→ 记失败, 不让整包失败
                f.status = "failed"
                f.error = "非法路径"
                mark_file(f.id, "failed", "非法路径")
                complete_one()
                continue
            if dest.exists() and dest.stat().st_size > 0:
                f.status = "done"
                f.error = None
                mark_file(f.id, "done", None)
                complete_one()
                continue
            last_err = ""
            downloaded = False
            for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
                if _run_tokens.get(job.id) != token:
                    break
                # 上次尝试留下的 .part 会走 Range 续传; 进度基准按已有字节起算,
                # 否则重试会把已下部分重复计入 bytes_done。
                part = dest.with_suffix(dest.suffix + ".part")
                start = part.stat().st_size if part.exists() else 0
                prev = {"n": start}
                def on_prog(done, total, _prev=prev):
                    prog.report(_prev["n"], done, total)
                    _prev["n"] = done
                try:
                    pipeline.download_stream(
                        f.url, dest,
                        max_bytes=MAX_FILE_BYTES,
                        on_progress=on_prog,
                        stream_key=f"{job.id}:{f.file_id}",
                        use_proxy=PIKPAK_USE_PROXY)
                    downloaded = True
                    break
                except Exception as e:
                    last_err = str(e)[:200]
                    if attempt < DOWNLOAD_ATTEMPTS:
                        time.sleep(min(RETRY_BACKOFF * attempt, 2.0))
            # 看门狗已重置本任务: 不写状态, 让下一轮完整重跑
            if _run_tokens.get(job.id) != token:
                return
            if downloaded:
                f.status = "done"
                f.error = None
                mark_file(f.id, "done", None)
            else:
                f.status = "failed"
                f.error = last_err
                mark_file(f.id, "failed", last_err)
                # 一张图失败不判整包失败: 剩下的继续下, 最后由 _import_album
                # 按实际到手的图片数决定写真集是否成立
                log.warning("pikpak job #%s file %s failed after %d attempts: %s",
                            job.id, rel, DOWNLOAD_ATTEMPTS, last_err[:120])
            complete_one()

    threads = [threading.Thread(target=worker, daemon=True,
                                name=f"pikpak-dl-{job.id}-{k}")
               for k in range(DOWNLOAD_CONCURRENCY)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    prog.flush()
    # 外层 session 的 identity map 已过期(其它线程改了这些行), 让后续
    # _import_album 重新拉最新状态
    s.expire_all()


def _safe_join(root: Path, rel: str) -> Path | None:
    """把相对路径拼到 root 下; 越界(.. / 绝对路径 / 空)返回 None。"""
    rel = rel.replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts or ".." in rel.split("/"):
        return None
    dest = root.joinpath(*parts)
    try:
        dest.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return dest


def _import_album(s, job: PikPakJob, final_dir: Path, library_root: Path,
                  unsorted: str, token: str) -> None:
    """导入写真集; 失败时把残留目录记到任务上, 删除任务时清理。"""
    try:
        from ...config import settings as app_settings
        r = library_import.import_album(
            s, final_dir, app_settings.media_dir, library_root=library_root,
            unsorted_dir=unsorted,
            tags=_tags_from_job(job), thumbs=False)
        job = s.get(PikPakJob, job.id)
        if job is None or _run_tokens.get(job.id) != token:
            return
        if r["skipped"]:
            job.error = "→ 已导入过,跳过"
        else:
            job.collection_slug = r["slug"]
            extra = f",跳过 {r['videos']} 个视频" if r["videos"] else ""
            job.error = f"→ {r['photos']} 张已入库{extra}"
        # 导入走完之后就没有「待下载」的文件了(失败行也已记录在案)
        s.query(PikPakFile).where(
            PikPakFile.job_id == job.id,
            PikPakFile.status == "queued").update({"status": "done"})
        s.commit()   # 先落库释放写锁
        if not r["skipped"] and r.get("slug"):
            job = s.get(PikPakJob, job.id)
            if job:
                nq = media.queue_import_thumbs(r["slug"])
                job.error = f"{job.error},缩略图生成中#{nq}"
                s.commit()
    except Exception as e:
        log.exception("pikpak job #%s import failed", job.id)
        job = s.get(PikPakJob, job.id)
        if job and _run_tokens.get(job.id) == token:
            _finish(s, job, "failed", f"→ 入库失败: {str(e)[:80]}")
            job.archive_dir = str(final_dir)
            s.commit()


def _prune_empty_album(library_root: Path | None,
                       album_dir: Path | None) -> None:
    """清掉本次跑出来的空写真目录(下载全失败时只剩 mkdir 出的壳)。

    空目录留着会让下次重推时的「已存在」预检误判; 只删空目录, 有文件的
    目录一律不碰(可能是别的写真集)。
    """
    if not library_root or not album_dir:
        return
    for d in (album_dir, album_dir.parent):
        try:
            if not d.is_dir() or d == library_root or d == d.parent:
                continue
            if any(p.is_file() for p in d.rglob("*")):
                continue
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def _cleanup_run(library_root: Path | None, job_id: int,
                 archive_file: Path | None) -> None:
    """清理一次任务运行的产物(仅本任务的)。

    - work 目录一律删(解压产物, 归档后已无价值)
    - 下载完的压缩包删(已入库, 留着只占空间)
    - *.part / 未完成: 保留 — 重试的断点续传基础
    """
    archive_tmp = archive_tmp_of(library_root)
    if archive_tmp is not None:
        shutil.rmtree(archive_tmp / f"work-{job_id}", ignore_errors=True)
        shutil.rmtree(archive_tmp / f"work-{job_id}-import", ignore_errors=True)
    if archive_file is not None:
        Path(archive_file).unlink(missing_ok=True)


def _prune_tmp(archive_tmp) -> None:
    """_tmp 孤儿兑底: 只清无主的工作目录(>7 天)与零字节 .part。"""
    if not archive_tmp:
        return
    s = SessionLocal()
    try:
        active_ids = set(s.scalars(select(PikPakJob.id).where(
            PikPakJob.status.in_(ACTIVE_JOB_STATES))).all())
        # harvest 的任务也可能在同一 _tmp 里工作(共享 library/_tmp)
        active_ids |= set(s.scalars(select(HarvestJob.id).where(
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
            tag = d.name.replace("work-", "")
            # work-<pikpak job id> 与 work-<harvest serial> 都可能, 逐个比对
            if tag.isdigit() and int(tag) in active_ids:
                continue
            if now - mtime > 7 * 86400:
                shutil.rmtree(d, ignore_errors=True)
        for p in archive_tmp.glob("*.part"):
            try:
                if p.stat().st_size == 0:
                    p.unlink(missing_ok=True)
            except OSError:
                continue
    except Exception:
        log.exception("prune _tmp failed")


def _recover_and_watchdog(*, at_startup: bool = False) -> None:
    """启动恢复 + 独立看门狗, 防「downloading 永久卡住」。

    看门狗跑在独立线程(_watchdog_loop): 下载线程卡死会把消费循环一起冻结,
    内嵌看门狗永远轮不到执行。

    at_startup=True 时不看 updated_at: 上次进程的下载线程已随进程消失,
    活动任务必然都是孤儿。若仍按 30 分钟阈值筛, 重启前刚更新过的任务会被
    误判「健康」, 要一直卡到阈值到期才恢复(实测 P20 卡了 30 分钟)。
    """
    s = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - STALE_SECONDS
        rows = s.scalars(select(PikPakJob).where(
            PikPakJob.status.in_(ACTIVE_JOB_STATES))).all()
        reset: list[int] = []
        for job in rows:
            if at_startup:
                reset.append(job.id)
                continue
            ref = job.updated_at or job.started_at or job.created_at
            if ref is not None and ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            if ref is None or ref.timestamp() < cutoff:
                reset.append(job.id)
        for job_id in reset:
            job = s.get(PikPakJob, job_id)
            if job is None:
                continue
            job.status = "queued"
            job.error = "进度停滞/上次运行中断, 自动重新排队(已下载部分续传)"
            s.commit()
            # 解堵: close 本任务全部在途下载流(并发下载是 <job>:<file> 多 key)
            pipeline.close_job_streams(job_id)
            # 撤销所有权: 卡死的旧线程复苏后不得再碰这个任务
            _run_tokens.pop(job_id, None)
            log.warning("watchdog reset pikpak job #%s (%s) -> queued",
                        job_id, job.name)
        if rows and not reset:
            log.info("pikpak watchdog: %d active job(s) healthy", len(rows))
    except Exception:
        log.exception("pikpak watchdog pass failed")
    finally:
        s.close()


def _consume_loop() -> None:
    """串行消费: 取最早排队任务 → 执行。失败不阻塞队列。"""
    while not _stop.is_set():
        s = SessionLocal()
        try:
            job = s.scalar(select(PikPakJob)
                           .where(PikPakJob.status == "queued")
                           .order_by(PikPakJob.id).limit(1))
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
    """独立看门狗线程: 每 60s 扫一次进度停滞的活动任务。"""
    while not _stop.wait(timeout=60.0):
        _recover_and_watchdog()


def start_worker() -> None:
    """启动后台消费线程 + 看门狗线程。无条件启动(手动推送要随时处理)。"""
    global _thread, _watchdog
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    # 上次运行遗留的进行中任务(容器重启/被杀): 恢复回 queued, .part 续传
    _recover_and_watchdog(at_startup=True)
    _thread = threading.Thread(target=_consume_loop, name="pikpak-worker",
                               daemon=True)
    _thread.start()
    _watchdog = threading.Thread(target=_watchdog_loop, name="pikpak-watchdog",
                                 daemon=True)
    _watchdog.start()
    log.info("pikpak worker started")


def stop_worker() -> None:
    _stop.set()


def worker_running() -> bool:
    return bool(_thread and _thread.is_alive())
