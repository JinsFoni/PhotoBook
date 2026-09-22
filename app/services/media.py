"""媒体服务 — /media 原图 + 按需缩略图(WebP, 版位尺寸, 磁盘缓存)。

URL 形如 /media/<path>              原图
        /t/<w>x<h>/<path>.webp     裁剪缩略图(h 可省略 → 等比)
"""

from __future__ import annotations

import io
import logging
import re
import threading

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from PIL import Image

from ..config import settings

log = logging.getLogger("photobook.media")

CACHE_DIR = "_cache"
THUMB_RE = re.compile(r"^(\d+)(?:x(\d+))?/(.+)\.(jpg|jpeg|png|webp)$", re.I)

Image.MAX_IMAGE_PIXELS = 400 * 1024 * 1024  # 原图可达 40MP+


def _safe_path(rel: str) -> any:
    """防目录穿越:解析后必须仍在 media_dir 内。"""
    base = settings.media_dir.resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(404)
    return p


def _cache_path(w: int, h: int | None, q: int, rel: str) -> any:
    """缓存路径带质量标记,避免不同质量档互相误命中。"""
    return settings.media_dir / CACHE_DIR / f"{w}x{h or 0}q{q}" / f"{rel}.webp"


def _make_webp(src, w: int, h: int | None, q: int) -> bytes:
    """从源图生成缩放 WebP;只缩不放,支持等比(仅 w)与中心裁剪(w+h)。"""
    with Image.open(src) as im:
        im = im.convert("RGB")
        sw, sh = im.size
        tw = min(w, sw)
        if h:
            # 先按比例裁剪,再缩放
            target_ratio = w / h
            src_ratio = sw / sh
            if src_ratio > target_ratio:   # 太宽 → 裁两侧
                nw = int(sh * target_ratio)
                x0 = (sw - nw) // 2
                im = im.crop((x0, 0, x0 + nw, sh))
            else:                           # 太高 → 裁上下(偏上,保头部)
                nh = int(sw / target_ratio)
                y0 = max(0, (sh - nh) // 3)
                im = im.crop((0, y0, sw, y0 + nh))
        th = h if h else int(tw * sh / sw)
        im = im.resize((tw, th), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=q, method=4)
        return buf.getvalue()


def ensure_cached(rel: str, w: int, h: int | None = None, q: int | None = None) -> None:
    """确保某个缩放档已有磁盘缓存(预热用,不直接服务请求)。"""
    src = _safe_path(rel)
    if not src.is_file():
        return
    if q is None:
        q = 88 if w >= 1600 else 78
    cache = _cache_path(w, h, q, rel)
    if cache.is_file():
        return
    try:
        data = _make_webp(src, w, h, q)
    except Exception:
        log.warning("preheat failed: %s w=%s", rel, w, exc_info=True)
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)


def serve_media(rel: str, request: Request) -> Response:
    p = _safe_path(rel)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=31536000, immutable"})


def serve_thumb(spec: str, request: Request) -> Response:
    m = THUMB_RE.match(spec)
    if not m:
        raise HTTPException(404)
    w = min(int(m.group(1)), 2400)
    if w < 16:
        raise HTTPException(404)
    # 大尺寸(灯箱预览)用高质量,网格小图保持 q78 省体积
    q = 88 if w >= 1600 else 78
    h = int(m.group(2)) if m.group(2) else None
    if h is not None and h < 16:
        raise HTTPException(404)
    rel = m.group(3)
    # URL 里 .webp 是缩略图格式后缀,真实源文件不带它
    if rel.lower().endswith(".webp"):
        rel = rel[:-5]

    src = _safe_path(rel)
    if not src.is_file():
        raise HTTPException(404)

    cache = _cache_path(w, h, q, rel)
    if cache.is_file():
        return FileResponse(cache, media_type="image/webp",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # 生成:缩到目标宽(裁高比),WebP 按尺寸分档
    try:
        data = _make_webp(src, w, h, q)
    except Exception as e:
        raise HTTPException(500, f"thumbnail failed: {e}")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return Response(data, media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


def thumb_url(rel: str | None, w: int, h: int | None = None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    if h:
        return f"/t/{w}x{h}/{rel}.webp"
    return f"/t/{w}/{rel}.webp"


# ---- 缩略图预热 -----------------------------------------------------------------
# 启动后后台线程逐张预生成常用尺寸,用户请求永远命中热缓存(24MP 图冷生成
# 0.4s/张,未预热时首次浏览明显卡顿)。daemon 线程,服务退出即终止。

_preheat_done = threading.Event()
_preheat_lock = threading.Lock()
_preheat_state = {"total": 0, "done": 0, "running": False}


def preheat_running() -> bool:
    """预热线程是否仍在工作中。"""
    with _preheat_lock:
        return _preheat_state["running"]


def preheat_progress() -> dict:
    """预热进度(供管理后台展示)。"""
    with _preheat_lock:
        return dict(_preheat_state)


def preheat_all(batch: int = 4) -> None:
    """预热全部照片的常用尺寸(700 网格 / 900 封面 / 1800 预览 / 2400 高清)。
    幂等:已有缓存的文件直接跳过。在 daemon 线程里跑,不阻塞启动。"""

    def _run() -> None:
        import time

        from sqlalchemy import select

        from ..database import SessionLocal
        from ..db import Photo

        t0 = time.time()
        try:
            s = SessionLocal()
            try:
                files = list(s.scalars(select(Photo.filename)).all())
            finally:
                s.close()
            with _preheat_lock:
                _preheat_state.update(total=len(files), done=0, running=True)
            log.info("preheat: %d photos", len(files))
            done = 0
            for rel in files:
                if _preheat_done.is_set():
                    break
                for w in (700, 900, 1800, 2400):
                    ensure_cached(rel, w)
                done += 1
                if done % 50 == 0:
                    log.info("preheat: %d/%d (%.0fs)", done, len(files), time.time() - t0)
                with _preheat_lock:
                    _preheat_state["done"] = done
                # 小批次让出 CPU,采集下载等任务优先
                if done % batch == 0:
                    time.sleep(0.05)
            with _preheat_lock:
                _preheat_state.update(done=done, running=False)
            log.info("preheat done: %d photos in %.0fs", done, time.time() - t0)
        except Exception:
            with _preheat_lock:
                _preheat_state["running"] = False
            log.exception("preheat crashed")

    threading.Thread(target=_run, name="thumb-preheat", daemon=True).start()
