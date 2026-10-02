"""入库健康检查 — 损坏图跳过/全坏整包跳过。"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image


def _jpeg(path: Path, color=(90, 140, 200)):
    Image.new("RGB", (48, 64), color).save(path, "JPEG", quality=90)


@pytest.fixture
def lib_and_media(tmp_path):
    lib = tmp_path / "library"
    media_root = tmp_path / "media"
    lib.mkdir()
    media_root.mkdir()
    return lib, media_root


def _import(lib_and_media, album="Test模特/测试画集"):
    from app.database import SessionLocal
    from app.services import library_import

    lib, media_root = lib_and_media
    s = SessionLocal()
    try:
        return library_import.import_album(s, lib / album, media_root,
                                           library_root=lib)
    finally:
        s.close()


def test_import_skips_broken_images(lib_and_media):
    """部分图损坏: 好图正常入库, 坏图不进库、文件留在 library。"""
    lib, media_root = lib_and_media
    album = lib / "Test模特" / "测试画集"
    album.mkdir(parents=True)
    _jpeg(album / "01.jpg")
    _jpeg(album / "02.jpg", (200, 90, 90))
    (album / "03.jpg").write_bytes(b"\xff\xd8 broken tail")  # 假 JPEG

    stats = _import(lib_and_media)
    assert stats["photos"] == 2
    assert stats["broken"] == ["03.jpg"]
    # 坏图留在原地, 没被搬进 media
    assert (album / "03.jpg").is_file()
    assert not (media_root / "test-mo-te" / "测试画集" / "03.jpg").exists()


def test_import_all_broken_skips_whole_album(lib_and_media):
    """整包全是坏图: 不建写真集, 文件原样留在 library。"""
    lib, media_root = lib_and_media
    album = lib / "Test模特" / "全坏画集"
    album.mkdir(parents=True)
    (album / "01.jpg").write_bytes(b"garbage")
    (album / "02.jpg").write_bytes(b"also garbage")

    stats = _import(lib_and_media, album="Test模特/全坏画集")
    assert stats["skipped"] is True
    assert stats["photos"] == 0
    assert stats["broken"] == ["01.jpg", "02.jpg"]
    assert (album / "01.jpg").is_file() and (album / "02.jpg").is_file()


def test_truncated_but_decodable_image_passes_check(lib_and_media):
    """宽容模式可解的截断图不算坏: 正常入库(与 /t 口径一致)。"""
    lib, media_root = lib_and_media
    album = lib / "Test模特" / "截断画集"
    album.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (40, 50), (10, 10, 10)).save(buf, "JPEG", quality=90)
    (album / "01.jpg").write_bytes(buf.getvalue()[:-18])  # 掐尾部

    stats = _import(lib_and_media, album="Test模特/截断画集")
    assert stats["photos"] == 1 and stats["broken"] == []
