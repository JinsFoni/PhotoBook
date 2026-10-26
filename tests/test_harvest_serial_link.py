"""跨站同内容「已入库」判定:跳过时也要把本站序号登记到既有写真集上。

2026-10-27 用户报 buondua `/tag/le` 里 888-891 四本没显示「已入库」。
这四本是 buondua 的链接,下完解包后才发现 misskon 那批同内容已入库 →
任务判 exists/done,但序号没写进任何 `collections.source_serial(s)`;
浏览器联动脚本(`ext_api.collection_exists`)只看那两个字段,于是永远显示
「可下载」,点了就是白下一遍。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.db import Collection, HarvestJob, Model
from app.routers import ext_api
from app.services import library_import
from app.services.harvest import worker as h_worker


def _img(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 140), (30, 60, 90)).save(path)


def _album(root: Path, model: str, title: str, n: int = 3) -> Path:
    d = root / model / title
    for i in range(1, n + 1):
        _img(d / f"{i:03d}.jpg")
    return d


def _mk_job(s, serial: int, title: str, model_name: str) -> HarvestJob:
    j = HarvestJob(serial=serial, url=f"https://x/{serial}", title=title,
                   model_name=model_name, status="exists")
    s.add(j)
    s.flush()
    return j


def _cleanup(serial: int) -> None:
    s = SessionLocal()
    try:
        s.execute(delete(HarvestJob).where(HarvestJob.serial == serial))
        s.commit()
    finally:
        s.close()


def test_register_existing_serial_marks_collection(tmp_path):
    """跳过的任务 → 序号进 source_serials + job 指向那条写真集。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Serial Link Probe", "Album A", n=2)
    serial = 960011
    _cleanup(serial)
    try:
        with SessionLocal() as s:
            r = library_import.import_album(s, album, media, library_root=lib,
                                            thumbs=False)
            col = s.scalar(select(Collection).where(Collection.slug == r["slug"]))
            col.source_serial = 123456
            job = _mk_job(s, serial, "[LE] Probe Album (2 photos)", "Serial Link Probe")
            assert not ext_api.collection_exists(s, serial)   # 登记前:脚本看到「可下载」

            h_worker._register_existing_serial(s, job, col)
            s.commit()

            assert ext_api.collection_exists(s, serial)
            assert job.collection_slug == col.slug
            assert str(col.source_serials).count("123456") == 1
            # 幂等:再登记一次不重复、不丢原序号
            h_worker._register_existing_serial(s, job, col)
            s.commit()
            assert col.source_serial == 123456
            assert str(col.source_serials).count(str(serial)) == 1
    finally:
        _cleanup(serial)


def test_register_existing_serial_for_target_matches_by_slug(tmp_path):
    """FileExistsError 兜底:靠标题算出的 slug 也能定位既有写真集。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Serial Target Probe", "Album B", n=2)
    serial = 960012
    _cleanup(serial)
    try:
        with SessionLocal() as s:
            library_import.import_album(s, album, media, library_root=lib, thumbs=False)
            job = _mk_job(s, serial, "Album B", "Serial Target Probe")

            class T:
                title = "Album B"
                model_name = "Serial Target Probe"

            h_worker._register_existing_serial_for_target(
                s, job, T(), {"harvest.unsorted_dir": "未分类"})
            s.commit()

            assert ext_api.collection_exists(s, serial)
            assert job.collection_slug == "serial-target-probe-album-b"
    finally:
        _cleanup(serial)


def test_preslug_strips_site_suffix_with_count_guard(tmp_path):
    """预检要剥掉源站张数尾缀, 但剥完必须过真实张数守卫。

    页码标题 `[LE] GMS-006A: GMS (60 photos)` 与归档目录名
    `[LE] GMS-006A GMS` 只差这个尾缀; 不剥就白下整包。
    而泛化系列标题的不同批次(25/121/310 张)剥完同名 → 张数不等就不能算命中。
    """
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Preslug Probe", "[LE] PRES-001 Probe", n=3)
    with SessionLocal() as s:
        library_import.import_album(s, album, media, library_root=lib, thumbs=False)
        col = s.scalar(select(Collection).where(
            Collection.slug == "preslug-probe-[le]-pres-001-probe"))
        assert col is not None
        n = len(col.photos)

        def hit(title: str) -> bool:
            from app.services.harvest.titlematch import photo_count, strip_counts
            from app.services.harvest.filters import sanitize_path_part
            reported = photo_count(title)
            if reported != n:          # 张数守卫(worker 的候选②)
                return False
            stripped = sanitize_path_part(strip_counts(title))
            return library_import.collection_slug(
                s, "Preslug Probe", stripped, "未分类") == col.slug

        assert hit(f"[LE] PRES-001 Probe ({n} photos)  -")     # 剥尾缀命中
        assert not hit(f"[LE] PRES-001 Probe ({n + 97} photos)")  # 张数不符 → 不命中


def test_import_album_skip_reports_existing_slug(tmp_path):
    """幂等跳过要把既有 slug 回传 —— 采集侧靠它把序号登记上去。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Serial Skip Probe", "Album C", n=2)
    with SessionLocal() as s:
        first = library_import.import_album(s, album, media, library_root=lib,
                                            thumbs=False)
        s.commit()
        album.mkdir(parents=True, exist_ok=True)
        _img(album / "001.jpg")       # 目录被搬空后再出现同一本
        _img(album / "002.jpg")
        second = library_import.import_album(s, album, media, library_root=lib,
                                             thumbs=False)
        assert second["skipped"] is True
        assert second["slug"] == first["slug"] == "serial-skip-probe-album-c"


def test_register_skips_when_target_missing():
    """兜底函数拿到 None 目标(异常路径)时不得炸。"""
    class Job:
        serial = 1

    h_worker._register_existing_serial_for_target(None, Job(), None, {})
