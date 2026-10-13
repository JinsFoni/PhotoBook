"""library_import(M4)— 归档库 → 平台:移动文件、建库、幂等、未分类、视频独立模块。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.db import Collection, Model, Photo, VideoAlbum
from app.services import library_import


def _img(path: Path, size=(1200, 800)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 100, 50)).save(path)


def _album(root: Path, model: str, title: str, n: int = 3, videos: int = 0) -> Path:
    d = root / model / title
    d.mkdir(parents=True, exist_ok=True)  # n=0(纯视频)也要建目录
    for i in range(1, n + 1):
        _img(d / f"{i:03d}.jpg")
    for i in range(videos):
        (d / f"clip{i}.mp4").write_bytes(b"v")
    return d


def _pb_data(html: str) -> dict:
    m = re.search(r"window\.PB_DATA = (.*?);\nwindow\.PB_BOOT", html, re.S)
    assert m, "PB_DATA missing"
    return json.loads(m.group(1))


def _collection(s, slug: str) -> Collection | None:
    return s.scalar(select(Collection).where(Collection.slug == slug))


def _video_album(s, slug: str) -> VideoAlbum | None:
    return s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug))


# ---- 基本导入 ---------------------------------------------------------------

def test_import_moves_files_and_publishes(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "School Nurse Vol.1", n=3)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 1 and stats["skipped"] == 0
        assert stats["photos"] == 3 and stats["errors"] == []

        c = _collection(s, "yeha-school-nurse-vol-1")
        assert c is not None
        # 缩略图就绪前 processing(前台不可见), 生成完自动 published
        assert c.status == "processing"
        assert c.cover_photo_id                 # 封面 = 首图
        assert c.model is not None and c.model.name == "Yeha"
        assert c.published_at.count(".") == 2   # YYYY.MM.DD

        photos = s.scalars(select(Photo).where(Photo.collection_id == c.id)
                           .order_by(Photo.sort_order)).all()
        assert [p.sort_order for p in photos] == [0, 1, 2]
        assert photos[0].filename == "yeha/school-nurse-vol-1/001.jpg"
        assert (photos[0].width, photos[0].height) == (1200, 800)

    # 图片「移动」而非拷贝:library 腾空(空目录一并清理)
    assert (media / "yeha" / "school-nurse-vol-1" / "001.jpg").exists()
    assert not (lib / "Yeha" / "School Nurse Vol.1").exists()
    assert not (lib / "Yeha").exists()


def test_import_natural_order(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    d = lib / "Yeha" / "Order Album"
    for name in ("10.jpg", "2.jpg", "1.jpg"):
        _img(d / name, size=(100, 100))

    with SessionLocal() as s:
        library_import.import_library(s, lib, media)
        c = _collection(s, "yeha-order-album")
        photos = s.scalars(select(Photo).where(Photo.collection_id == c.id)
                           .order_by(Photo.sort_order)).all()
        assert [p.filename.rsplit("/", 1)[1] for p in photos] == ["1.jpg", "2.jpg", "10.jpg"]
        assert c.cover_photo_id == photos[0].id


def test_import_skips_junk(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    d = _album(lib, "Yeha", "Junk Album", n=2)
    (d / ".DS_Store").write_bytes(b"junk")
    (d / "._001.jpg").write_bytes(b"junk")
    (d / "__MACOSX").mkdir()
    (d / "__MACOSX" / "._001.jpg").write_bytes(b"junk")

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["photos"] == 2
        c = _collection(s, "yeha-junk-album")
        names = [p.filename.rsplit("/", 1)[1] for p in c.photos]
        assert names == ["001.jpg", "002.jpg"]


def test_import_moves_videos_to_video_dir(tmp_path):
    """视频走独立模块:移入 video/ 并建 Video 行(archive 侧腾空)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    d = _album(lib, "Yeha", "Video Album", n=2, videos=2)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["photos"] == 2 and stats["videos"] == 2
        assert stats["video_albums"] == 1 and stats["video_files"] == 2
        assert _collection(s, "yeha-video-album") is not None
        album = _video_album(s, "yeha-video-album")
        assert album is not None
        assert len(album.videos) == 2
        assert album.cover_video_id == album.videos[0].id

    # 视频落在 video_dir(与 media 平行的独立根),library 侧已腾空
    assert (d / "clip0.mp4").exists() is False
    assert (d / "clip1.mp4").exists() is False
    assert (settings.video_dir / "yeha" / "video-album" / "clip0.mp4").is_file()
    assert (settings.video_dir / "yeha" / "video-album" / "clip1.mp4").is_file()
    assert not (d / "001.jpg").exists()


def test_import_video_only_album(tmp_path):
    """纯视频目录:不再 skipped,建视频专辑(images 为空也放行)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    d = _album(lib, "Yeha", "Clips Only", n=0, videos=2)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["skipped"] == 0 and stats["video_albums"] == 1
        assert _collection(s, "yeha-clips-only") is None  # 没有写真集
        assert _video_album(s, "yeha-clips-only") is not None

    assert (settings.video_dir / "yeha" / "clips-only" / "clip0.mp4").is_file()


def test_import_album_with_both_photo_and_video(tmp_path):
    """同一归档目录混有图与视频 → 写真集与视频专辑各建一条(分开存)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "Mixed Set", n=2, videos=1)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 1 and stats["video_albums"] == 1
        assert stats["photos"] == 2 and stats["video_files"] == 1
        assert _collection(s, "yeha-mixed-set") is not None
        assert _video_album(s, "yeha-mixed-set") is not None

    assert (media / "yeha" / "mixed-set" / "001.jpg").is_file()
    assert (settings.video_dir / "yeha" / "mixed-set" / "clip0.mp4").is_file()


def test_video_import_without_ffmpeg_degrades(tmp_path, monkeypatch):
    """ffmpeg 缺失 → 降级:导入成功、Video.poster 为空、文件仍在。"""
    from app.services import video as video_service

    monkeypatch.setattr(video_service, "ffmpeg_available", lambda: False)
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "No FFmpeg", n=0, videos=1)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["video_albums"] == 1 and stats["video_files"] == 1
        album = _video_album(s, "yeha-no-ffmpeg")
        assert album is not None
        assert album.videos[0].poster is None       # 无封面
        assert album.videos[0].width is None        # 探测也降级

    assert (settings.video_dir / "yeha" / "no-ffmpeg" / "clip0.mp4").is_file()
    # worker 生成不了帧也放行(无封面必须可见),等它翻 published
    _wait_album_published("yeha-no-ffmpeg")


def _wait_album_published(slug: str, timeout: float = 8.0) -> None:
    """等封面帧 worker 把专辑翻到 published(失败也放行)。"""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as s:
            a = _video_album(s, slug)
            if a and a.status == "published":
                return
        time.sleep(0.1)
    raise AssertionError(f"video album {slug} never published")


def test_import_unsorted_has_no_model(tmp_path):
    """未分类目录 → collection.model_id 留空(前台显示「未分类」)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "未分类", "AI Generated Album", n=1)

    with SessionLocal() as s:
        library_import.import_library(s, lib, media, unsorted_dir="未分类")
        c = _collection(s, "未分类-ai-generated-album")
        assert c is not None and c.model_id is None
    assert (media / "未分类" / "ai-generated-album" / "001.jpg").exists()


def test_import_reuses_model(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "Reuse Album A", n=1)
    _album(lib, "Yeha", "Reuse Album B", n=1)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 2
        a = _collection(s, "yeha-reuse-album-a")
        b = _collection(s, "yeha-reuse-album-b")
        assert a.model_id == b.model_id
        assert s.scalar(select(func.count()).select_from(Model)
                        .where(Model.name == "Yeha")) == 1


def test_import_cjk_names(tmp_path):
    """中文模特名/标题保留原字(不做音译)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "麻花麻花酱", "碧蓝航线 埃吉尔", n=1)

    with SessionLocal() as s:
        library_import.import_library(s, lib, media)
        c = _collection(s, "麻花麻花酱-碧蓝航线-埃吉尔")
        assert c is not None and c.model.slug == "麻花麻花酱"
        assert c.photos[0].filename == "麻花麻花酱/碧蓝航线-埃吉尔/001.jpg"


# ---- 幂等 / 预检 -------------------------------------------------------------

def test_import_is_idempotent(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "Idem Album", n=2)

    with SessionLocal() as s:
        assert library_import.import_library(s, lib, media)["imported"] == 1
        # 同内容再次出现(重试/重下)→ 以 slug 为准跳过,不重复建库、不动文件
        _album(lib, "Yeha", "Idem Album", n=2)
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 0 and stats["skipped"] == 1
        assert s.scalar(select(func.count()).select_from(Collection)
                        .where(Collection.slug == "yeha-idem-album")) == 1

    assert (lib / "Yeha" / "Idem Album" / "001.jpg").exists()


def test_collection_exists_helper(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "Probe Album", n=1)
    with SessionLocal() as s:
        assert not library_import.collection_exists(s, "Yeha", "Probe Album")
        library_import.import_library(s, lib, media)
        assert library_import.collection_exists(s, "Yeha", "Probe Album")
        # 采集侧的目录名已 sanitize,这里保持一致
        assert library_import.collection_slug(s, "Yeha", "Probe Album") == "yeha-probe-album"
        assert not library_import.collection_exists(s, "Yeha", "不存在的写真")


def test_import_skips_empty_album(tmp_path):
    lib, media = tmp_path / "library", tmp_path / "media"
    (lib / "Yeha" / "Empty Album").mkdir(parents=True)
    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 0 and stats["skipped"] == 1


def test_import_missing_library_dir(tmp_path):
    with SessionLocal() as s:
        stats = library_import.import_library(s, tmp_path / "nope", tmp_path / "media")
        assert stats["albums"] == 0 and stats["errors"] == []


# ---- 前台可见性 --------------------------------------------------------------

def test_imported_album_visible_on_pages(tmp_path, admin_client):
    """缩略图生成完后自动 published → 写真集页面可见,封面图可服务。
    测试里直接调 _publish_ready 跳过后台线程等待。"""
    lib = tmp_path / "library"
    _album(lib, "Yeha", "Visible Album", n=2)

    with SessionLocal() as s:
        library_import.import_library(s, lib, settings.media_dir)
        c = _collection(s, "yeha-visible-album")
        assert c is not None and c.status == "processing"
        from app.services import media as media_svc
        media_svc._publish_ready("yeha-visible-album")
        s.expire_all()
        c = _collection(s, "yeha-visible-album")
        assert c.status == "published"

    r = admin_client.get("/collections")
    assert r.status_code == 200
    assert any(c["slug"] == "yeha-visible-album" for c in _pb_data(r.text)["collections"])

    r = admin_client.get("/collections/yeha-visible-album")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert d["slug"] == "yeha-visible-album"
    assert d["title"] == "Visible Album" and len(d["photos"]) == 2
    assert admin_client.get("/media/yeha/visible-album/001.jpg").status_code == 200
    assert admin_client.get("/t/400/yeha/visible-album/001.jpg.webp").status_code == 200


def test_video_import_records_poster_rel(tmp_path, monkeypatch):
    """ffmpeg 可用时:抽帧成功 → Video.poster 记下 rel(前台封面才有值)。

    poster rel 与 filename 同值(缓存树按 rel 派生路径);这条链路曾断过:
    worker 只落缓存不回写 DB,导致 _video_album_cover 永远返回 None。
    """
    import io as _io

    from PIL import Image

    from app.services import media as media_service
    from app.services import video as video_service

    def _jpeg_bytes():
        b = _io.BytesIO()
        Image.new("RGB", (640, 360), (30, 60, 90)).save(b, "JPEG")
        return b.getvalue()

    monkeypatch.setattr(video_service, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video_service, "extract_frame",
                        lambda path, at=None: _jpeg_bytes())
    monkeypatch.setattr(video_service, "probe",
                        lambda path: (1920, 1080, 42.0))

    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "Yeha", "Poster Set", n=0, videos=2)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["video_albums"] == 1
        album = _video_album(s, "yeha-poster-set")
        assert album is not None
        v0 = album.videos[0]
        # poster rel == filename(封面帧缓存按视频 rel 派生)
        assert v0.poster == v0.filename
        # 900 档缓存真的落盘了
        cache = media_service._cache_path(900, None, 78, v0.filename, short=True)
        assert cache.is_file()

    _wait_album_published("yeha-poster-set")
