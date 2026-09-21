"""演示图片引导 — 空库首启时填充 /media/demo/。

优先从 Unsplash 下载(data.js 里的 POOL 图片 ID);失败则生成占位图,
保证离线环境(NAS 内网)也能完整体验 UI。
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from .seed_data import COLLECTIONS

log = logging.getLogger("seed-images")

BASE = "https://images.unsplash.com/photo-"
SIZES = {"cover": 1200, "thumb": 700}


def _placeholder(w: int, h: int, label: str) -> bytes:
    im = Image.new("RGB", (w, h), (24, 26, 30))
    d = ImageDraw.Draw(im)
    d.text((w // 2 - 40, h // 2), label[:24], fill=(160, 163, 168))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _fetch(pool_id: str, w: int) -> bytes | None:
    import httpx

    try:
        r = httpx.get(BASE + pool_id, params={"w": w, "q": 72, "auto": "format", "fit": "crop"},
                      timeout=20, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass
    return None


def ensure_demo_images(media_dir: Path) -> int:
    """确保 demo 用到的图片存在。返回新下载/生成的数量。"""
    demo_root = media_dir / "demo"
    demo_root.mkdir(parents=True, exist_ok=True)
    missing: dict[str, tuple[str, str]] = {}  # key -> (pool_id, 目标绝对路径)

    for c in COLLECTIONS:
        col_dir = demo_root / c["slug"]
        col_dir.mkdir(exist_ok=True)
        for ph in c["photos"]:
            fname = Path(ph["file"]).name  # <pool_id>.jpg
            dest = col_dir / fname
            if not dest.is_file():
                # 共享池:同一张图被多个集合引用,每个集合目录都要有实体文件;
                # 键用目标路径,避免不同集合同名文件相互覆盖。
                missing[str(dest)] = (fname[:-4], str(dest))

    if not missing:
        return 0

    log.info("downloading %d demo images…", len(missing))
    done = 0

    def work(item):
        (_key, (pool_id, path)) = item
        data = _fetch(pool_id, 1200)
        if data is None:
            data = _placeholder(1200, 1600, pool_id)
        Path(path).write_bytes(data)
        return 1

    with ThreadPoolExecutor(max_workers=6) as ex:
        for n in ex.map(work, missing.items()):
            done += n
    done += ensure_demo_avatars(media_dir)
    log.info("demo images ready: %d", done)
    return done


def ensure_demo_avatars(media_dir: Path) -> int:
    """模特头像(avatar/hero)。同一池图多模特复用时按目标路径落盘。"""
    from .seed_data import MODELS

    av_root = media_dir / "demo" / "avatars"
    av_root.mkdir(parents=True, exist_ok=True)
    missing: dict[str, tuple[str, str]] = {}
    for md in MODELS:
        for key in ("avatar", "hero"):
            pid = md.get(key)
            if not pid:
                continue
            dest = av_root / f"{pid}.jpg"
            if not dest.is_file():
                missing[str(dest)] = (pid, str(dest))
    if not missing:
        return 0

    log.info("downloading %d model avatars…", len(missing))

    def work(item):
        (_key, (pool_id, path)) = item
        data = _fetch(pool_id, 800)
        if data is None:
            data = _placeholder(800, 1000, pool_id)
        Path(path).write_bytes(data)
        return 1

    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for n in ex.map(work, missing.items()):
            done += n
    return done
