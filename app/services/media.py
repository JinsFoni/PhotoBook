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
from PIL import Image, ImageFile
from sqlalchemy import select

from ..config import settings

log = logging.getLogger("photobook.media")

CACHE_DIR = "_cache"
THUMB_RE = re.compile(r"^(\d+)(?:x(\d+))?/(.+)\.(jpg|jpeg|png|webp)$", re.I)

Image.MAX_IMAGE_PIXELS = 400 * 1024 * 1024  # 原图可达 40MP+
# 宽容模式仅在严格解码失败后按图启用, 见 _open_tolerant()


def _open_tolerant(src, *, draft=None):
    """打开图片: 严格解码失败(截断/尾段损坏)时改用宽容模式重试。

    典型案例: 采集包里偶见的截断 JPEG(缺尾部 EOI 十几个字节), PIL 严格
    模式报 'image file is truncated', 但图像数据其实完整可解码 —— 这类图
    不用宽容模式的话 /t 缩略图永远 500, 预热每次巡检都刷警告。
    真「烂到解不开」的图宽容模式也救不了, 异常照旧抛出。

    draft: JPEG 降采样档, 与调用方的 draft() 参数同义(仅宽容重试时需要
    重新传: 重试是新开图, 原 draft 不会保留)。
    """
    try:
        im = Image.open(src)
        if draft:
            im.draft(*draft)
        im.load()
        return im
    except Exception:
        pass
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        im = Image.open(src)
        if draft:
            im.draft(*draft)
        im.load()
        return im
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = False

# 档位策略(两档, 都预热):
#   900  网格 + 照片墙
#   2400 灯箱显示档(前端恒用, 见 app.js 的 LB_W) — 全屏 fit 无差, 体积约 286KB/张。
# 灯箱从不请求真原图(24MP 原图解码是切图卡顿根源), 原图只服务下载与 1:1 放大。
# 曾有 1800 档: 本库 70% 原图宽 ≤1800, "只缩不放"下 1800 与 2400 输出字节完全相同,
# 两档并存就是纯重复副本; 且屏宽驱动的 1800/2400 双档让灯箱大屏永远打不到热缓存
# (2400 无人预热 → 每张现场解码 230~900ms)。故收敛为单档预热。
WALL_W = 900
HD_W = 2400
PREHEAT_WIDTHS = (WALL_W, HD_W)

# 缩略图生成全局并发上限。单张 19MP 图解码峰值 ~170MB,
# 不限流时浏览器并发 8 张就能把容器打到 1.4GB(NAS 实测);
# 库里还有 74MP 巨图, 2400 档单张峰值 243MB(实测)。
# NAS 级 CPU 单张 1~3s,排队等 1 轮远好于内存打爆。
_gen_sem = threading.Semaphore(2)

# 入库缩略图队列: 采集/手动导入完成后, 后台线程逐张生成 WALL/HD 两档。
# 生成完 → 写真从 processing 翻转 published(前台可见)。
# 单张两档合计约 0.33s(窄图 0.20s / 宽图 0.63s 加权, 实测): 299 张的写真
# 约 1~2 分钟就绪。2400 档在宽图上比 1800 贵约 2 倍 —— draft() 只为 1800
# 能选到 1/2 降采样档, 2400 要求全尺寸解码。
_thumb_queue: list[str] = []   # collection slug 列表(去重由入队方保证)
_thumb_lock = threading.Lock()
_thumb_wake = threading.Event()
_thumb_thread: threading.Thread | None = None

# 预热每张图要连出多个档位, 74MP 巨图在 2400 档单张峰值 243MB(实测)。
# 预热是逐张串行的, 但 glibc 默认不把解完后的空闲堆页还给内核,
# VmHWM 会一路顶到 800MB+。每张图之间 malloc_trim 归还内存 + 短歇。
_preheat_gap = 0.3


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
    """从源图生成缩放 WebP;只缩不放,支持等比(仅 w)与中心裁剪(w+h)。

    JPEG 先 draft() 降采样解码:按目标宽选 1/2、1/4 档,
    解码内存/时间降 4~16 倍,缩放结果肉眼无差(目标宽 ≥ 源宽/2 时取最近档)。
    """
    with _gen_sem:
        # 严格解码失败自动转宽容模式重试(截断 JPEG 可正常出图);
        # draft 对非 JPEG 是无操作, 不需要判格式
        im = _open_tolerant(src, draft=("RGB", (w, h or w)))
        try:
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
        finally:
            im.close()


def purge_collection_files(slug: str, filenames: list[str]) -> None:
    """删除写真集后清理磁盘残留: 照片本体 + 缩略图缓存 + 收藏记录。

    - 照片本体: 逐个删除 DB 登记过的文件; 原目录仅当空时才删
      (手工放进的非本写真集文件绝不误删), 不空则保留。
    - 缩略图: /media/_cache/<规格>/<照片相对路径>.webp, 按每个规格目录
      整目录移除; 空了则连规格下的写真目录一并移除。
    - 收藏记录(favorite): collection 与 photo(键 = slug:idx)一并清除, 避免前台
      收藏夹出现幽灵条目。

    清理失败不阻断删除主流程(DB 行已删, 不影响前台; 磁盘残留可手工清)。
    """
    import shutil

    if not filenames:
        return
    base = settings.media_dir
    album_dir = (base / filenames[0]).parent  # <owner>/<album-dir>

    # 照片本体: 逐个删除(只删 DB 里登记过的文件, 目录里其它文件不动)
    for rel in filenames:
        try:
            (base / rel).unlink()
        except OSError:
            pass

    # 缩略图缓存: 每个规格目录下按相对路径删除
    cache_root = base / CACHE_DIR
    if cache_root.is_dir():
        for spec_dir in cache_root.iterdir():
            if not spec_dir.is_dir():
                continue
            album_cache = spec_dir / album_dir.relative_to(base)
            if album_cache.is_dir():
                shutil.rmtree(album_cache, ignore_errors=True)
                try:
                    next(album_cache.parent.iterdir())  # 目录非空则保留
                except StopIteration:
                    album_cache.parent.rmdir()

    # 原图目录: 空才删, 防误删手工文件
    if album_dir.is_dir():
        try:
            next(album_dir.iterdir())
        except StopIteration:
            album_dir.rmdir()
            try:
                next(album_dir.parent.iterdir())
            except StopIteration:
                album_dir.parent.rmdir()

    # 收藏记录: collection 本体 + 照片(键 = "slug:idx")
    from ..database import SessionLocal
    from ..db import Favorite

    s = SessionLocal()
    try:
        n = s.query(Favorite).filter(
            (Favorite.target_type == "collection") & (Favorite.target_key == slug)
            | (Favorite.target_type == "photo") & (Favorite.target_key.like(f"{slug}:%"))
        ).delete(synchronize_session=False)
        if n:
            s.commit()
            log.info("purged %d favourites of deleted collection %s", n, slug)
    except Exception:
        s.rollback()
        log.exception("purge favourites failed: %s", slug)
    finally:
        s.close()
    log.info("purged collection files: %s (%d photos)", slug, len(filenames))


def ensure_cached(rel: str, w: int, h: int | None = None, q: int | None = None) -> bool:
    """确保某个缩放档已有磁盘缓存(预热用,不直接服务请求)。

    返回是否真的生成了新缓存(命中已有缓存/源图缺失返回 False)。
    """
    src = _safe_path(rel)
    if not src.is_file():
        return False
    if q is None:
        q = 88 if w >= 1600 else 78
    cache = _cache_path(w, h, q, rel)
    if cache.is_file():
        return False
    try:
        data = _make_webp(src, w, h, q)
    except Exception:
        log.warning("preheat failed: %s w=%s", rel, w, exc_info=True)
        return False
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return True


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


# ---- 入库健康检查 ---------------------------------------------------------------

def check_integrity(paths) -> list[str]:
    """逐张试解码,返回完整可解码的相对路径列表(调用方自己比对差集)。

    用途: 入库时把采集包里损坏的图(截断/非图)当场报出来, 而不是入库后
    缩略图阶段才冒警告。宽容重试后仍解不开的才算坏 —— 与 /t 生成同一
    判定口径, 这里放行的图缩略图必能生成。
    """
    ok: list[str] = []
    for p in paths:
        try:
            im = _open_tolerant(p)
            im.close()
            ok.append(str(p))
        except Exception:
            pass
    return ok


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


def _preheat_files(files: list[str], batch: int) -> tuple[int, int]:
    """逐张巡检预热。返回 (已巡检张数, 实际生成缩略图数)。

    缓存全部命中时零停顿(热重启几秒内巡完);只有真生成了缩略图
    才让出 CPU + 归还堆页,采集下载等任务优先。
    """
    import time

    done = 0
    generated = 0
    libc = _load_libc()  # malloc_trim: 把空闲堆页还给内核(不可用则跳过)
    for rel in files:
        if _preheat_done.is_set():
            break
        made = 0
        for w in PREHEAT_WIDTHS:
            if ensure_cached(rel, w):
                made += 1
        done += 1
        generated += made
        if done % 50 == 0:
            log.info("preheat: %d/%d (%.0fs)", done, len(files), time.time() - _t0[0])
        with _preheat_lock:
            _preheat_state["done"] = done
        if not made:
            # 全部命中缓存:零开销巡检,不睡眠不等内存回收
            continue
        # 真生成了缩略图才节流
        if done % batch == 0:
            time.sleep(0.05)
        time.sleep(_preheat_gap)
        if libc:
            libc.malloc_trim(0)
    return done, generated


_t0 = [0.0]


def preheat_all(batch: int = 4) -> None:
    """巡检全库, 补齐 PREHEAT_WIDTHS 各档缺失的缩略图(900 网格/照片墙 + 2400 灯箱)。

    幂等:已有缓存的文件直接跳过, 全命中时零停顿。daemon 线程, 不阻塞启动。
    顺序按新入库优先 —— 换档后补齐全库是小时级(每张生成 + _preheat_gap 0.3s),
    让最近采集的部分先热, 用户真会翻到的那批不等长尾。"""

    # 新一轮预热周期:清掉上次 shutdown 置位的停机信号,
    # 否则同进程内二次启动(测试/热重启)时预热线程会立即退出
    _preheat_done.clear()

    def _run() -> None:
        import time

        from sqlalchemy import select

        from ..database import SessionLocal
        from ..db import Photo

        t0 = time.time()
        _t0[0] = t0
        try:
            s = SessionLocal()
            try:
                files = list(s.scalars(
                    select(Photo.filename).order_by(Photo.created_at.desc())).all())
            finally:
                s.close()
            with _preheat_lock:
                _preheat_state.update(total=len(files), done=0, running=True)
            log.info("preheat: %d photos", len(files))
            done, generated = _preheat_files(files, batch)
            with _preheat_lock:
                _preheat_state.update(done=done, running=False)
            log.info("preheat done: %d photos, %d thumbs generated in %.0fs",
                     done, generated, time.time() - t0)
        except Exception:
            with _preheat_lock:
                _preheat_state["running"] = False
            log.exception("preheat crashed")

    threading.Thread(target=_run, name="thumb-preheat", daemon=True).start()


# ---- 入库缩略图队列 -------------------------------------------------------------
# 采集/手动导入完成后异步生成 900/2400 两档;生成完把写真从 processing
# 翻转 published,前台才可见。队列元素为 collection slug。

def _publish_ready(slug: str) -> None:
    """写真两档齐备 → published。幂等:已是 published 则无操作。"""
    from ..database import SessionLocal
    from ..db import Collection

    s = SessionLocal()
    try:
        c = s.scalar(select(Collection).where(Collection.slug == slug))
        if not c:
            return
        if c.status == "processing":
            c.status = "published"
            s.commit()
            log.info("published (thumbs ready): %s", slug)
    finally:
        s.close()


def _load_libc():
    """malloc_trim 用;Linux 走 libc.so.6。macOS 无此符号 → 返回 None(不致命)。"""
    import ctypes
    try:
        libc = ctypes.CDLL("libc.so.6")
        if not hasattr(libc, "malloc_trim"):
            return None
        return libc
    except OSError:
        return None


def _import_worker() -> None:
    import time

    libc = _load_libc()
    while True:
        with _thumb_lock:
            slug = _thumb_queue[0] if _thumb_queue else None
        if slug is None:
            _thumb_wake.wait(timeout=30)
            _thumb_wake.clear()
            continue
        try:
            from ..database import SessionLocal
            from ..db import Collection

            s = SessionLocal()
            try:
                c = s.scalar(select(Collection).where(Collection.slug == slug))
                files = [p.filename for p in c.photos] if c else []
            finally:
                s.close()
            for rel in files:
                for w in PREHEAT_WIDTHS:
                    ensure_cached(rel, w)
            _publish_ready(slug)
        except Exception:
            # 生成失败也放行(保持 processing 会永久隐藏写真;放行交给
            # 请求路径限流兜底,预热下次重启再补)
            log.exception("import thumbs failed: %s", slug)
            try:
                _publish_ready(slug)
            except Exception:
                log.exception("publish failed: %s", slug)
        finally:
            with _thumb_lock:
                if _thumb_queue and _thumb_queue[0] == slug:
                    _thumb_queue.pop(0)
            if libc:
                libc.malloc_trim(0)
            time.sleep(0.1)


def ensure_import_worker() -> None:
    """启动入库缩略图 worker(daemon)。幂等。"""
    global _thumb_thread
    if _thumb_thread and _thumb_thread.is_alive():
        return
    _thumb_thread = threading.Thread(target=_import_worker, name="thumb-import", daemon=True)
    _thumb_thread.start()


def queue_import_thumbs(slug: str) -> int:
    """写真入队生成缩略图,返回当前队列长度。入队后写真状态置 processing。"""
    from ..database import SessionLocal
    from ..db import Collection

    s = SessionLocal()
    try:
        c = s.scalar(select(Collection).where(Collection.slug == slug))
        if c and c.status == "published":
            c.status = "processing"
            s.commit()
    finally:
        s.close()
    with _thumb_lock:
        if slug not in _thumb_queue:
            _thumb_queue.append(slug)
        n = len(_thumb_queue)
    ensure_import_worker()
    _thumb_wake.set()
    return n


def recover_stuck_processing() -> int:
    """启动自愈:重启会丢内存缩略图队列,卡在 processing 的写真将永远不可见。
    扫描全部 processing 集合重新入队(幂等:缩略图已存在的 ensure_cached
    直接命中,随后 _publish_ready 正常翻转)。返回入队数量。"""
    from ..database import SessionLocal
    from ..db import Collection

    s = SessionLocal()
    try:
        slugs = [row for row in s.scalars(
            select(Collection.slug).where(Collection.status == "processing")).all()]
    finally:
        s.close()
    for slug in slugs:
        with _thumb_lock:
            if slug not in _thumb_queue:
                _thumb_queue.append(slug)
    if slugs:
        ensure_import_worker()
        _thumb_wake.set()
        log.warning("recovered %d stuck processing collection(s): %s",
                    len(slugs), ", ".join(x[:40] for x in slugs))
    return len(slugs)
