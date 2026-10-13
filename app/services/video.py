"""视频服务 — /video 原片(Range/206)+ /poster 封面帧(ffmpeg 抽帧)。

与 media.py 的分工:media 管图片(缩略图按需生成),这里只管视频。
封面帧是「一张从视频里抽出来的 JPEG」,之后喂给 media._make_webp 走
与照片完全相同的两档缓存(/t/s900、/t/s2400),URL 同构,前端卡片代码
可与写真集镜像复用。

ffmpeg 缺失时的降级:probe/extract_frame 全部返回空值,视频照常入库
与播放,只是无封面(前端回退写真首图/占位)。删本地视频的门槛因此多
一条「封面两档已缓存」—— 照片删了还能回源重生成缩略图,视频删了连
帧都抽不出来。
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import threading

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from PIL import Image
from sqlalchemy import select

from ..config import settings

log = logging.getLogger("photobook.video")

# 视频 rel 的 MIME(Starlette guess_type 对 .ts/.m4v 等不可靠,显式映射)
_MIME_BY_EXT = {
    ".mp4": "video/mp4", ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".ts": "video/mp2t",
    ".mpg": "video/mpeg", ".mpeg": "video/mpeg",
}

# 封面帧档位:与照片共用 media._cache_path 的同一棵缓存树
POSTER_WALL_SHORT = 900
POSTER_HD_SHORT = 2400
# 封面帧质量与照片网格档一致(w<1600 → q78);_cache_path 由调用方按档位传
POSTER_Q = 78

_ffmpeg_lock = threading.Lock()
_ffmpeg_state: bool | None = None   # None = 未探测;True/False = 有无 ffmpeg


def mime_of(rel: str) -> str:
    """rel → 响应 MIME;未知扩展名回退 video/mp4(浏览器嗅探能力强)。"""
    from pathlib import PurePosixPath
    return _MIME_BY_EXT.get(PurePosixPath(rel).suffix.lower(), "video/mp4")


def ffmpeg_available() -> bool:
    """ffmpeg 是否可用(进程内缓存一次 which 结果)。"""
    global _ffmpeg_state
    with _ffmpeg_lock:
        if _ffmpeg_state is None:
            _ffmpeg_state = shutil.which("ffmpeg") is not None
            if not _ffmpeg_state:
                log.warning("ffmpeg not found — 视频无封面帧(功能降级,播放不受影响)")
        return _ffmpeg_state


def _safe_path(rel: str):
    """防目录穿越:解析后必须仍在 video_dir 内。"""
    base = settings.video_dir.resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(404)
    return p


def abs_path(rel: str):
    """video 下相对路径 → 绝对路径(后台任务用)。"""
    return settings.video_dir / rel


# ---- ffprobe / ffmpeg ---------------------------------------------------------

def probe(path) -> tuple[int | None, int | None, float | None]:
    """ffprobe 读尺寸与时长。任何失败(无 ffmpeg/文件坏/超时)返回全 None。

    导入链路对返回值零要求:探不到只是元数据缺失,视频本身照样可用。
    """
    if not ffmpeg_available():
        return None, None, None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            capture_output=True, timeout=30, check=False)
        if out.returncode != 0:
            return None, None, None
        info = json.loads(out.stdout or b"{}")
    except Exception:
        log.warning("probe failed: %s", path, exc_info=True)
        return None, None, None
    w = h = None
    for st in info.get("streams", []):
        if st.get("codec_type") == "video":
            w, h = st.get("width"), st.get("height")
            break
    try:
        duration = float(info.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    return w, h, duration


def extract_frame(path, at: float | None = None) -> bytes | None:
    """ffmpeg 抽一帧 JPEG(管道直出,不落临时文件)。

    ``-ss`` 放在 ``-i`` 前 = 快速seek(关键帧定位,不解码全片),
    1GB 视频抽第 1s 也是毫秒级。失败返回 None。
    """
    if not ffmpeg_available():
        return None
    at = settings.video_frame_at if at is None else at
    try:
        out = subprocess.run(
            ["ffmpeg", "-ss", str(max(0.0, at)), "-i", str(path),
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
            capture_output=True, timeout=60, check=False)
        if out.returncode != 0 or not out.stdout:
            return None
        return out.stdout
    except Exception:
        log.warning("extract frame failed: %s", path, exc_info=True)
        return None


# ---- 封面帧缓存 ---------------------------------------------------------------

def poster_cache_paths(rel: str) -> list:
    """该视频封面帧的两档缓存路径(与照片缩略图同一棵树,同档位同质量)。"""
    from . import media
    return [media._cache_path(w, None, POSTER_Q if w < 1600 else 88, rel, short=True)
            for w in (POSTER_HD_SHORT, POSTER_WALL_SHORT)]


def poster_ready(rel: str) -> bool:
    """两档封面帧是否都已在盘(删本地视频前的门槛,同 thumb_cache_ready 语义)。"""
    return all(p.is_file() for p in poster_cache_paths(rel))


def ensure_poster_cached(rel: str) -> bool:
    """确保两档封面帧已缓存(预热/入队 worker 用)。

    命中返回 False;真生成了返回 True。视频不在本地(已上传并删除)时
    返回 False —— 上传 worker 保证删除前两档已就绪,这里不会漏。

    poster rel 与视频 rel 同值(缓存树按 rel 派生路径,不需要额外字段
    记录"帧来自第几秒"—— 封面永远是默认抽帧点)。DB 里的
    Video.poster 由调用方(worker/import)在本函数成功后回写。
    """
    from . import media

    src = _safe_path(rel)
    if not src.is_file():
        return False
    paths = poster_cache_paths(rel)
    if all(p.is_file() for p in paths):
        return False
    frame = extract_frame(src)
    if frame is None:
        return False
    try:
        im = Image.open(io.BytesIO(frame))
        im.load()
    except Exception:
        log.warning("extracted frame is not decodable: %s", rel)
        return False
    made = False
    try:
        for w, path in zip((POSTER_HD_SHORT, POSTER_WALL_SHORT), paths):
            if path.is_file():
                continue
            data = media._make_webp(io.BytesIO(frame), w, None,
                                    POSTER_Q if w < 1600 else 88, short=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            made = True
    except Exception:
        log.warning("poster cache write failed: %s", rel, exc_info=True)
    finally:
        im.close()
    return made


def mark_poster(rel: str) -> int:
    """把成功生成封面的视频在 DB 里回写 poster rel(与 filename 同值)。

    poster 为空 = 前台回退占位;非空 = 卡片/灯箱直接拼 /t/s900/{poster}.webp。
    幂等:已回写过的跳过(UPDATE 只动 poster IS NULL 的行)。
    """
    from ..database import SessionLocal
    from ..db import Video

    s = SessionLocal()
    try:
        n = s.query(Video).filter(Video.filename == rel,
                                  Video.poster.is_(None)).update({"poster": rel})
        s.commit()
        return n
    except Exception:
        s.rollback()
        log.exception("poster mark failed: %s", rel)
        return 0
    finally:
        s.close()


def serve_poster(rel: str, w: int = POSTER_WALL_SHORT) -> Response:
    """封面帧路由:缓存优先,未命中且本地视频在则抽帧现生成。

    900 档是卡片/灯箱垫底通用档(与照片 WALL_SHORT 同语义);调用方只
    要这一个档 —— 2400 档由入队 worker 预热,灯箱放大时才需要。
    """
    from . import media

    if w not in (POSTER_WALL_SHORT, POSTER_HD_SHORT):
        raise HTTPException(404)
    q = POSTER_Q if w < 1600 else 88
    cache = media._cache_path(w, None, q, rel, short=True)
    if cache.is_file():
        return FileResponse(cache, media_type="image/webp",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})
    src = _safe_path(rel)
    if not src.is_file():
        # 原片已上传外部存储并删除本地:缓存也没有 → 抽不出帧,404 让前端回退
        raise HTTPException(404)
    frame = extract_frame(src)
    if frame is None:
        raise HTTPException(404)
    try:
        data = media._make_webp(io.BytesIO(frame), w, None, q, short=True)
    except Exception:
        log.warning("poster generate failed: %s", rel, exc_info=True)
        raise HTTPException(404)
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache.write_bytes(data)
    except OSError:
        pass  # 缓存写失败不影响本次响应
    return Response(data, media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ---- 原片服务 -----------------------------------------------------------------

def serve_video(rel: str, request: Request) -> Response:
    """/video/{rel}:本地 FileResponse(Range 原生支持)→ 远端 302 → 流式代理。

    Range/206 由 Starlette FileResponse 自己处理(_parse_range_header),
    视频拖动进度条/断点续传零额外代码;远端路径与 media 同一套存储
    优先级逻辑(remote_stream 已透传 Range 给上游)。
    """
    p = _safe_path(rel)
    if not p.is_file():
        from .storage import remote_redirect, remote_stream
        from .storage import remote_urls
        redirect = remote_redirect(rel)
        if redirect:
            return RedirectResponse(redirect, 302)
        for url in remote_urls(rel):
            resp = remote_stream(url, dict(request.headers))
            if resp is not None:
                return resp
        raise HTTPException(404)
    return FileResponse(p, media_type=mime_of(rel),
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ---- 清理 ---------------------------------------------------------------------

def cleanup_empty_dirs(any_rel: str) -> None:
    """视频所在专辑目录/模特目录若已空则逐级删除(空才删,防误删)。"""
    if not any_rel:
        return
    album_dir = (settings.video_dir / any_rel).parent
    try:
        next(album_dir.iterdir())
    except StopIteration:
        album_dir.rmdir()
        try:
            next(album_dir.parent.iterdir())
        except StopIteration:
            album_dir.parent.rmdir()
    except OSError:
        pass


def purge_video_album_files(slug: str, filenames: list[str],
                            posters: list[str] | None = None) -> None:
    """删视频专辑时清理磁盘与收藏(与 media.purge_collection_files 平行)。

    1. 原片本体(DB 登记的 Video.filename);
    2. 封面帧缓存(按规格目录整目录 rmtree,同照片缩略图清理);
    3. video/ 空目录(空才删);
    4. 收藏记录:album 本体(键 = slug)+ 单视频(键 = "slug:v{idx}" 前缀)。
    """
    import shutil as _shutil

    base = settings.video_dir
    for rel in filenames:
        p = base / rel
        try:
            p.unlink()
        except OSError:
            pass

    # 封面帧缓存: 与缩略图同一棵树(media/_cache), 按规格目录删
    cache_root = settings.media_dir / "_cache"
    for rel in (posters or []) + list(filenames):
        for spec_dir in cache_root.iterdir() if cache_root.is_dir() else []:
            if not spec_dir.is_dir():
                continue
            album_cache = spec_dir / rel
            if album_cache.is_dir():
                _shutil.rmtree(album_cache, ignore_errors=True)
                try:
                    next(album_cache.parent.iterdir())  # 目录非空则保留
                except StopIteration:
                    album_cache.parent.rmdir()

    # 原片目录: 空才删, 防误删手工文件
    for rel in filenames:
        album_dir = (base / rel).parent
        try:
            next(album_dir.iterdir())
        except StopIteration:
            album_dir.rmdir()
            try:
                next(album_dir.parent.iterdir())
            except StopIteration:
                album_dir.parent.rmdir()
        except OSError:
            pass

    # 收藏记录
    from ..database import SessionLocal
    from ..db import Favorite

    s = SessionLocal()
    try:
        n = s.query(Favorite).filter(
            (Favorite.target_type == "video_album") & (Favorite.target_key == slug)
            | (Favorite.target_type == "video") & (Favorite.target_key.like(f"{slug}:%"))
        ).delete(synchronize_session=False)
        if n:
            s.commit()
            log.info("purged %d favourites of deleted video album %s", n, slug)
    except Exception:
        s.rollback()
        log.exception("purge favourites failed: %s", slug)
    finally:
        s.close()
    log.info("purged video album files: %s (%d files)", slug, len(filenames))


# ---- 入库封面帧队列 -----------------------------------------------------------
# 与 media._thumb_queue 同模式:内存队列 + daemon worker,入队即把专辑置
# processing,两档封面齐备后翻 published 并触发自动上传。

_poster_queue: list[str] = []   # album slug 列表(去重由入队方保证)
_poster_lock = threading.Lock()
_poster_wake = threading.Event()
_poster_thread: threading.Thread | None = None


def ensure_video_worker() -> None:
    """启动封面帧 worker(daemon)。幂等。"""
    global _poster_thread
    if _poster_thread and _poster_thread.is_alive():
        return
    _poster_thread = threading.Thread(target=_poster_worker, name="video-poster-worker",
                                      daemon=True)
    _poster_thread.start()


def queue_video_posters(slug: str) -> int:
    """视频专辑入队生成封面帧,返回当前队列长度。入队后专辑状态置 processing。"""
    from ..database import SessionLocal
    from ..db import VideoAlbum

    s = SessionLocal()
    try:
        a = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug))
        if a and a.status == "published":
            a.status = "processing"
            s.commit()
    finally:
        s.close()
    with _poster_lock:
        if slug not in _poster_queue:
            _poster_queue.append(slug)
        n = len(_poster_queue)
    ensure_video_worker()
    _poster_wake.set()
    return n


def _publish_ready_album(slug: str) -> None:
    """封面帧两档齐备 → published。幂等:已是 published 则无操作。"""
    from ..database import SessionLocal
    from ..db import VideoAlbum

    s = SessionLocal()
    try:
        a = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug))
        if not a:
            return
        if a.status == "processing":
            a.status = "published"
            s.commit()
            log.info("published (posters ready): %s", slug)
            _auto_upload_new_video_album(s, a)
    finally:
        s.close()


def _auto_upload_new_video_album(s, a) -> None:
    """新入库视频专辑发布后自动上传(仅此路径;存量库不回填)。"""
    try:
        from . import settings_store
        from .storage import worker as storage_worker
        targets = settings_store.auto_upload_targets(s)
        if targets:
            n = storage_worker.enqueue_video_album(a.id, targets)
            if n:
                log.info("auto upload queued: %s -> %d storage(s)", a.slug, n)
    except Exception:
        log.exception("auto upload enqueue failed: %s", a.slug)


def _poster_worker() -> None:
    import time

    while True:
        with _poster_lock:
            slug = _poster_queue[0] if _poster_queue else None
        if slug is None:
            _poster_wake.wait(timeout=30)
            _poster_wake.clear()
            continue
        try:
            from ..database import SessionLocal
            from ..db import VideoAlbum

            s = SessionLocal()
            try:
                a = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug))
                files = [v.filename for v in a.videos] if a else []
            finally:
                s.close()
            for rel in files:
                # 缓存落盘成功后回写 DB poster rel(前台封面才有值)
                if ensure_poster_cached(rel) or poster_ready(rel):
                    mark_poster(rel)
            _publish_ready_album(slug)
        except Exception:
            # 生成失败也放行(保持 processing 会永久隐藏专辑;ffmpeg 缺失时
            # 走这条:视频无封面但前台必须可见,播放不受影响)
            log.exception("poster generation failed: %s", slug)
            try:
                _publish_ready_album(slug)
            except Exception:
                log.exception("publish failed: %s", slug)
        finally:
            with _poster_lock:
                if _poster_queue and _poster_queue[0] == slug:
                    _poster_queue.pop(0)
            time.sleep(0.1)


def recover_stuck_processing_albums() -> int:
    """启动自愈:重启会丢内存队列,卡在 processing 的视频专辑将永远不可见。

    扫描全部 processing 专辑重新入队(幂等:封面已存在的直接命中,
    随后 _publish_ready_album 正常翻转)。返回入队数量。
    """
    from ..database import SessionLocal
    from ..db import VideoAlbum

    s = SessionLocal()
    try:
        slugs = [row for row in s.scalars(
            select(VideoAlbum.slug).where(VideoAlbum.status == "processing")).all()]
    finally:
        s.close()
    for slug in slugs:
        with _poster_lock:
            if slug not in _poster_queue:
                _poster_queue.append(slug)
    if slugs:
        ensure_video_worker()
        _poster_wake.set()
        log.warning("recovered %d stuck processing video album(s): %s",
                    len(slugs), ", ".join(x[:40] for x in slugs))
    return len(slugs)
