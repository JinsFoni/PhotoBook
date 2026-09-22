"""媒体服务 — /media 原图 + 按需缩略图(WebP, 版位尺寸, 磁盘缓存)。

URL 形如 /media/<path>              原图
        /t/<w>x<h>/<path>.webp     裁剪缩略图(h 可省略 → 等比)
"""

from __future__ import annotations

import io
import re

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from PIL import Image

from ..config import settings

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


def _cache_path(w: int, h: int | None, rel: str) -> any:
    return settings.media_dir / CACHE_DIR / f"{w}x{h or 0}" / f"{rel}.webp"


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

    cache = settings.media_dir / CACHE_DIR / f"{w}x{h or 0}q{q}" / f"{rel}.webp"
    if cache.is_file():
        return FileResponse(cache, media_type="image/webp",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # 生成:缩到目标宽(裁高比),WebP q78
    try:
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
    except Exception as e:
        raise HTTPException(500, f"thumbnail failed: {e}")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(buf.getvalue())
    return Response(buf.getvalue(), media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


def thumb_url(rel: str | None, w: int, h: int | None = None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    if h:
        return f"/t/{w}x{h}/{rel}.webp"
    return f"/t/{w}/{rel}.webp"
