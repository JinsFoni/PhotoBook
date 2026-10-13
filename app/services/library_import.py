"""归档库 → 平台导入(M4)。

采集归档落在 `<library>/<模特名>/<写真目录>/`(写真目录名取自压缩包自带顶层
目录名,见 pipeline.archive_collection)。本模块把图片 **移动** 到
`/media/<模特slug>/<写真slug>/` 并建立 models / collections / photos 记录;
同一目录里的视频走平行的视频模块:移动到 `video/<模特slug>/<专辑slug>/`
并建立 video_albums / videos 记录(两个模块分开存、分开展示)。

约定(2026-09 与用户对齐,2026-10 补视频):
- 一级目录名 = 模特名;等于「未分类目录名」时 model_id 留空 → 前台显示「未分类」
- 二级目录名 = 写真/专辑标题
- 图片按自然序排序(001…061);跳过 .DS_Store / ._* / __MACOSX
- 同一归档目录里图片与视频都存在 → 图片建写真集、视频建视频专辑,两条条目
- 导入即 `status=published`,立即在页面可见;封面 = 首图 / 首视频抽帧
- library 是「下载暂存区」:文件移走后清理空目录(保留 _tmp)
- 幂等键 = collections.slug / video_albums.slug,重复导入自动跳过
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Collection, Model, Photo, Video, VideoAlbum

log = logging.getLogger("library_import")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jfif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".flv", ".ts", ".webm", ".mpg", ".mpeg"}
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}
JUNK_DIRS = {"__MACOSX", "_tmp", "_cache", ".git"}
# 这些目录名视为「没有模特」(与 harvest.unsorted_dir 一起判定)
NO_MODEL_DIRS = {"未分类", "未分類", "00_Unsorted", "unsorted", "uncategorized", "uncategorised"}


# ---- 工具 -------------------------------------------------------------------

def slugify(text: str | None, *, fallback: str = "untitled", maxlen: int = 120) -> str:
    """标题 → URL slug。保留汉字/字母数字,其余(空白、下划线、标点)归一为 '-'。

    URL 结构字符(# ? % &)必须剔除:slug 未编码直拼进 href(模板与前端
    都是 "/collections/" + slug),浏览器把 # 当 fragment、? 当 query 截断
    路径 → 404(任务 285 的「#バケショ」实测)。% 还会让服务端解码二次
    歪斜。这里按"只放行白名单"处理,比追补黑名单稳。
    """
    s = re.sub(r'[\\/:*?"<>|#%&?+\x00-\x1f]+', "-", (text or "").strip())
    s = re.sub(r"[\s_.]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("- .")
    s = s.lower()  # 与既有 slug 风格一致(ASCII 小写;汉字不受影响)
    return (s[:maxlen].strip("- .") or fallback)


def _nat_key(text: str):
    """自然序键:'10' > '9'(避免 '10.jpg' 排在 '9.jpg' 前)。"""
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"(\d+)", text.lower()))


def _path_key(root: Path, p: Path):
    return tuple(_nat_key(part) for part in p.relative_to(root).parts)


def _is_junk(p: Path, root: Path | None = None) -> bool:
    """系统垃圾/隐藏文件。root 给定时只在 root 之内匹配目录名(避免误伤绝对路径)。"""
    if p.name in JUNK_NAMES or p.name.startswith("."):
        return True
    try:
        parts = p.relative_to(root).parts if root else p.parts
    except ValueError:
        parts = p.parts
    return any(part in JUNK_DIRS for part in parts)


def list_images(album_dir: Path, recursive: bool = True) -> tuple[list[Path], int]:
    """(图片文件[自然序], 视频数)。recursive=False 只数本层(判定是否写真目录用)。

    视频只计数不收集 —— 收集是 list_videos 的事(视频走独立模块)。
    """
    images: list[Path] = []
    videos = 0
    walker = album_dir.rglob("*") if recursive else album_dir.glob("*")
    for p in walker:
        if not p.is_file() or _is_junk(p, album_dir):
            continue
        ext = p.suffix.lower()
        if ext in IMAGE_EXTS:
            images.append(p)
        elif ext in VIDEO_EXTS:
            videos += 1
    images.sort(key=lambda p: _path_key(album_dir, p))
    return images, videos


def list_videos(album_dir: Path, recursive: bool = True) -> list[Path]:
    """视频文件[自然序]。与 list_images 同一套 junk/排序规则。"""
    out: list[Path] = []
    walker = album_dir.rglob("*") if recursive else album_dir.glob("*")
    for p in walker:
        if not p.is_file() or _is_junk(p, album_dir):
            continue
        if p.suffix.lower() in VIDEO_EXTS:
            out.append(p)
    out.sort(key=lambda p: _path_key(album_dir, p))
    return out


def _dims(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None, None


def _prune_empty(album_dir: Path, library_root: Path | None) -> None:
    """删除空目录(含上级模特目录),保留 library 根与 _tmp。"""
    for d in sorted((p for p in album_dir.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    for d in (album_dir, album_dir.parent):
        if d == library_root or d.name in JUNK_DIRS or d == d.parent:
            continue
        try:
            d.rmdir()
        except OSError:
            pass


# ---- DB 侧 ------------------------------------------------------------------

def _unique_slug(s: Session, model_cls, base: str, maxlen: int) -> str:
    slug, i = base[:maxlen], 2
    while s.scalar(select(model_cls.id).where(model_cls.slug == slug)):
        suffix = f"-{i}"
        slug = base[:maxlen - len(suffix)] + suffix
        i += 1
    return slug


def _get_or_create_model(s: Session, name: str) -> Model | None:
    """按名字复用模特;没有则新建(published)。空名字 → None(未分类)。"""
    if not name:
        return None
    m = s.scalar(select(Model).where(Model.name == name))
    if m:
        return m
    m = Model(slug=_unique_slug(s, Model, slugify(name, maxlen=120), 120),
              name=name[:120], status="published")
    s.add(m)
    s.flush()
    log.info("new model: %s (%s)", m.name, m.slug)
    return m


def _owner_slug(s: Session, model_name: str, unsorted_dir: str) -> str:
    """媒体目录名 / slug 前缀:有模特用其 slug,否则用未分类目录名。"""
    if model_name:
        m = s.scalar(select(Model).where(Model.name == model_name))
        if m:
            return m.slug
        return slugify(model_name, maxlen=120)
    return slugify(unsorted_dir, maxlen=120)


def collection_slug(s: Session, model_name: str, title: str,
                    unsorted_dir: str = "未分类") -> str:
    owner = _owner_slug(s, model_name, unsorted_dir)
    return f"{owner}-{slugify(title, maxlen=160)}"[:200]


def collection_exists(s: Session, model_name: str, title: str,
                      unsorted_dir: str = "未分类") -> bool:
    """该写真是否已导入过(幂等判定;采集重试前的廉价预检也用它)。"""
    if not (title or "").strip():
        return False
    slug = collection_slug(s, model_name, title, unsorted_dir)
    return s.scalar(select(Collection.id).where(Collection.slug == slug)) is not None


# ---- 导入 -------------------------------------------------------------------

def import_album(s: Session, album_dir: Path, media_root: Path,
                 library_root: Path | None = None, unsorted_dir: str = "未分类",
                 today: str | None = None,
                 tags: list[str] | None = None,
                 thumbs: bool = True) -> dict:
    """导入单个写真目录。返回统计 {album, model, photos, videos, skipped, slug}。

    图片移动 → 建 models/collections/photos 记录;已导入过(slug 命中)则原样跳过。
    中途失败会把已移动的文件移回原位,不留半成品。
    ``tags``:采集详情页解析到的显示名 tag(None = 无),建合集后一并挂上。
    ``thumbs``:True = 入库后同步入队缩略图生成(完成前 status=processing,
    前台不可见);False = 调用方自管(采集 worker 拿到 slug 后自己入队)。
    ``today``:写进 published_at 的日期(YYYY.MM.DD);采集链路传源站详情页
    的发布日期,None 回退导入当天(手动目录导入无源站日期)。
    """
    album_dir = Path(album_dir)
    parent = album_dir.parent
    model_name = "" if (library_root is not None and parent == Path(library_root)) else parent.name
    if model_name in NO_MODEL_DIRS or model_name == unsorted_dir:
        model_name = ""
    title = album_dir.name
    stats = {"album": title, "model": model_name, "photos": 0, "videos": 0,
             "skipped": False, "slug": ""}

    images, videos = list_images(album_dir)
    stats["videos"] = videos
    if not images:
        stats["skipped"] = True
        return stats

    # 幂等:已导入过 → 原样跳过(文件留在 library,不动);
    # 必须在健康检查之前 —— 定时扫描会反复遇到已入库目录,不能白全量解码
    if collection_exists(s, model_name, title, unsorted_dir):
        stats["skipped"] = True
        log.info("skip (already imported): %s / %s", model_name or unsorted_dir, title)
        return stats

    # 健康检查: 宽容重试后仍解不开的图当场拉出来, 不让烂图混进库
    # (与 /t 缩略图同一判定口径; 全坏则整包跳过, 不建空写真集)
    from . import media as _media
    broken: list[str] = []
    ok_set = set(_media.check_integrity(images))
    for src in images:
        if str(src) not in ok_set:
            broken.append(src.name)
            log.warning("import %s: 跳过损坏图片 %s", title, src.name)
    if broken and not ok_set:
        log.error("import %s: 全部 %d 张图均损坏, 整包跳过", title, len(broken))
        stats["skipped"] = True
        stats["broken"] = broken
        return stats
    stats["broken"] = broken

    model = _get_or_create_model(s, model_name)
    owner_slug = model.slug if model else slugify(unsorted_dir, maxlen=120)
    slug = f"{owner_slug}-{slugify(title, maxlen=160)}"[:200]
    stats["slug"] = slug

    # 移动文件到 /media/<模特slug>/<写真slug>/ (同名冲突加序号)
    dest_dir = Path(media_root) / owner_slug / slugify(title, maxlen=160)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    try:
        for src in images:
            if str(src) not in ok_set:
                continue  # 损坏图不移动不入库(已在上面记录/警告)
            target = dest_dir / src.name
            n = 2
            while target.exists():
                target = dest_dir / f"{src.stem}-{n}{src.suffix}"
                n += 1
            shutil.move(str(src), str(target))
            moved.append((src, target))

        published = today or datetime.now().strftime("%Y.%m.%d")  # 采集传源站发布日期
        # 缩略图就绪前不前台可见: thumbs=True 直接 processing, 生成完自动发布;
        # thumbs=False(采集 worker)调用方随后自己入队(同样会置 processing)
        initial = "processing" if thumbs else "published"
        c = Collection(slug=slug, title=title[:255],
                       model_id=model.id if model else None,
                       published_at=published, status=initial)
        s.add(c)
        s.flush()
        for i, (_src, target) in enumerate(moved):
            w, h = _dims(target)
            ph = Photo(collection_id=c.id,
                       filename=f"{owner_slug}/{dest_dir.name}/{target.name}",
                       width=w, height=h, sort_order=i)
            s.add(ph)
            s.flush()
            if i == 0:
                c.cover_photo_id = ph.id
        if tags:
            from . import tagging
            n = tagging.apply_tags(s, c, model, tags)
            log.info("tagged %s: +%d", c.slug, n)
        s.commit()
        stats["photos"] = len(moved)
    except Exception:
        s.rollback()
        for src, target in reversed(moved):
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(src))
            except Exception:
                log.exception("rollback move failed: %s", target)
        raise

    _prune_empty(album_dir, Path(library_root) if library_root else None)
    log.info("imported %s: %d photos (%s)%s", title, len(moved), slug,
             f",损坏跳过 {len(broken)} 张" if broken else "")
    stats["broken"] = broken
    if thumbs and not stats["skipped"] and stats["slug"]:
        from . import media
        media.queue_import_thumbs(stats["slug"])
    return stats


def import_video_album(s: Session, album_dir: Path,
                       library_root: Path | None = None,
                       unsorted_dir: str = "未分类",
                       today: str | None = None) -> dict:
    """导入单个视频目录(与 import_album 平行的独立模块)。

    视频移动 → video_dir/<模特slug>/<专辑slug尾>/ + 建 video_albums/videos 记录;
    首视频抽帧作封面(ffmpeg 缺失则 poster=None,前台回退占位)。
    中途失败把已移动的文件移回原位,不留半成品。
    返回 {album, model, videos, skipped, slug}。
    """
    from ..config import settings
    from . import video as video_service

    album_dir = Path(album_dir)
    parent = album_dir.parent
    model_name = "" if (library_root is not None and parent == Path(library_root)) else parent.name
    if model_name in NO_MODEL_DIRS or model_name == unsorted_dir:
        model_name = ""
    title = album_dir.name
    stats = {"album": title, "model": model_name, "videos": 0,
             "skipped": False, "slug": ""}

    clips = list_videos(album_dir)
    if not clips:
        stats["skipped"] = True
        return stats

    # 幂等:已导入过 → 原样跳过(文件留在 library,不动)
    if video_album_exists(s, model_name, title, unsorted_dir):
        stats["skipped"] = True
        log.info("skip (already imported): %s / %s", model_name or unsorted_dir, title)
        return stats

    model = _get_or_create_model(s, model_name)
    owner_slug = model.slug if model else slugify(unsorted_dir, maxlen=120)
    slug = f"{owner_slug}-{slugify(title, maxlen=160)}"[:200]
    stats["slug"] = slug

    dest_dir = Path(settings.video_dir) / owner_slug / slugify(title, maxlen=160)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    try:
        for src in clips:
            target = dest_dir / src.name
            n = 2
            while target.exists():
                target = dest_dir / f"{src.stem}-{n}{src.suffix}"
                n += 1
            shutil.move(str(src), str(target))
            moved.append((src, target))

        published = today or datetime.now().strftime("%Y.%m.%d")
        a = VideoAlbum(slug=slug, title=title[:255],
                       model_id=model.id if model else None,
                       published_at=published, status="processing")
        s.add(a)
        s.flush()
        for i, (_src, target) in enumerate(moved):
            w, h, dur = video_service.probe(target)
            rel = f"{owner_slug}/{dest_dir.name}/{target.name}"
            v = Video(album_id=a.id,
                      filename=rel,
                      width=w, height=h, duration=dur, sort_order=i)
            s.add(v)
            s.flush()
            if i == 0:
                a.cover_video_id = v.id
            # 导入时顺手抽首帧落缓存(ffmpeg 缺失/失败则 poster 留空,
            # 后台 worker 与 /poster 路由都会兜底重试)
            try:
                if video_service.ensure_poster_cached(rel):
                    v.poster = rel
            except Exception:
                log.warning("poster generate skipped at import: %s", rel,
                            exc_info=True)
        s.commit()
        stats["videos"] = len(moved)
    except Exception:
        s.rollback()
        for src, target in reversed(moved):
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(src))
            except Exception:
                log.exception("rollback move failed: %s", target)
        raise

    _prune_empty(album_dir, Path(library_root) if library_root else None)
    log.info("imported video album %s: %d clips (%s)", title, len(moved), slug)
    if not stats["skipped"] and stats["slug"]:
        video_service.queue_video_posters(stats["slug"])
    return stats


def video_album_exists(s: Session, model_name: str, title: str,
                       unsorted_dir: str) -> bool:
    """(模特名, 专辑标题)是否已导入(幂等判定,与 collection_exists 平行)。"""
    owner = _owner_slug(s, model_name, unsorted_dir)
    slug = f"{owner}-{slugify(title, maxlen=160)}"[:200]
    return s.scalar(select(VideoAlbum.id).where(VideoAlbum.slug == slug)) is not None


def import_library(s: Session, library_root: Path, media_root: Path,
                   unsorted_dir: str = "未分类") -> dict:
    """扫描归档库,导入所有写真与视频专辑。

    返回 {albums, imported, skipped, photos, videos, errors, video_albums, video_files}:
    photos/videos 是写真侧的图片数与该目录里数到的视频数(历史字段,语义不变);
    video_albums/video_files 是视频模块实际建成的专辑数与移入的视频文件数。
    """
    library_root = Path(library_root)
    stats: dict = {"albums": 0, "imported": 0, "skipped": 0,
                   "photos": 0, "videos": 0, "errors": [],
                   "video_albums": 0, "video_files": 0}
    if not library_root.is_dir():
        return stats

    albums: list[Path] = []
    for entry in sorted(library_root.iterdir(), key=lambda p: _nat_key(p.name)):
        if not entry.is_dir() or _is_junk(entry, library_root):
            continue
        images, _v = list_images(entry, recursive=False)
        if images:
            albums.append(entry)  # 一级目录下直接是图片 → 无模特写真
            continue
        # 一级目录下没有图但有视频 → 该目录本身是视频专辑(无模特)
        if list_videos(entry, recursive=False):
            albums.append(entry)
            continue
        # 其余一级目录一律下沉二级:二级可能是写真、视频专辑、混合或空目录,
        # 由循环内的 list_images/list_videos 判定(空目录报 skipped,同旧行为)
        for sub in sorted(entry.iterdir(), key=lambda p: _nat_key(p.name)):
            if sub.is_dir() and not _is_junk(sub, library_root):
                albums.append(sub)

    for album in albums:
        stats["albums"] += 1
        try:
            images, n_videos = list_images(album)
            if images or not n_videos:
                # 有图 → 写真集;无图也无视频 → import_album 内部报 skipped
                # (空目录/全坏图的统计口径不变,见 test_import_skips_empty_album)
                r = import_album(s, album, media_root, library_root=library_root,
                                 unsorted_dir=unsorted_dir)
                if r["skipped"]:
                    stats["skipped"] += 1
                else:
                    stats["imported"] += 1
                    stats["photos"] += r["photos"]
                    stats["videos"] += r["videos"]
            if n_videos:
                # 同一归档目录里的视频走独立模块(分开存、分开展示);
                # 纯视频目录 images 为空,上面不会建写真集,这里建专辑
                vr = import_video_album(s, album, library_root=library_root,
                                        unsorted_dir=unsorted_dir)
                if vr["skipped"]:
                    if not images:
                        stats["skipped"] += 1
                else:
                    stats["video_albums"] += 1
                    stats["video_files"] += vr["videos"]
        except Exception as e:
            s.rollback()
            stats["errors"].append(f"{album.name}: {e}")
            log.exception("import failed: %s", album)
    return stats
