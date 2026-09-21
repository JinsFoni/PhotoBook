"""library_import(M4)— 归档库 → 平台:移动文件、建库、幂等、未分类、跳过视频。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.db import Collection, Model, Photo
from app.services import library_import


def _img(path: Path, size=(1200, 800)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 100, 50)).save(path)


def _album(root: Path, model: str, title: str, n: int = 3, videos: int = 0) -> Path:
    d = root / model / title
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
        assert c.status == "published"          # 导入即发布
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


def test_import_leaves_videos(tmp_path):
    """视频暂不导入:计入统计但文件留在归档库。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    d = _album(lib, "Yeha", "Video Album", n=2, videos=2)

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["photos"] == 2 and stats["videos"] == 2
        assert _collection(s, "yeha-video-album") is not None

    assert (d / "clip0.mp4").exists() and (d / "clip1.mp4").exists()
    assert not (d / "001.jpg").exists()


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
    """导入即 published → 写真集页面立刻能看到,封面图可服务。"""
    lib = tmp_path / "library"
    _album(lib, "Yeha", "Visible Album", n=2)

    with SessionLocal() as s:
        library_import.import_library(s, lib, settings.media_dir)
        c = _collection(s, "yeha-visible-album")
        assert c is not None and c.status == "published"

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
