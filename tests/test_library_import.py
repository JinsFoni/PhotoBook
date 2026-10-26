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


def test_import_writes_native_name_to_stage_name(tmp_path):
    """采集链路给的原生名 → models.stage_name(主名仍是拉丁名)。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Mu Yu Qian", "MFStar Vol.076 Mu Yu Qian (慕羽茜)", n=1)

    with SessionLocal() as s:
        library_import.import_album(s, album, media, library_root=lib,
                                    model_native="慕羽茜", thumbs=False)
        m = s.scalar(select(Model).where(Model.name == "Mu Yu Qian"))
        assert m is not None and m.stage_name == "慕羽茜"
        c = _collection(s, "mu-yu-qian-mfstar-vol-076-mu-yu-qian-(慕羽茜)")
        assert c is not None and c.model_id == m.id


def test_import_native_name_does_not_clobber_manual_stage_name(tmp_path):
    """人工填过的 stage_name(艺名)不被自动抽取覆盖;空的才补。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    name = "StageName Probe"           # 独立名字, 不与其他用例抢同一行
    a1 = _album(lib, name, "Album A", n=1)
    a2 = _album(lib, name, "Album B", n=1)

    with SessionLocal() as s:
        s.add(Model(slug="stage-name-probe", name=name, stage_name="小茜",
                    status="published"))
        s.commit()
        library_import.import_album(s, a1, media, library_root=lib,
                                    model_native="慕羽茜", thumbs=False)
        m = s.scalar(select(Model).where(Model.name == name))
        assert m.stage_name == "小茜"

        m.stage_name = None            # 空着 → 下次导入补上
        s.commit()
        library_import.import_album(s, a2, media, library_root=lib,
                                    model_native="慕羽茜", thumbs=False)
        assert m.stage_name == "慕羽茜"


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


def test_import_same_slug_different_photo_count(tmp_path):
    """slug 撞名但张数不同 → 同名不同批,改名追加序号照常入库。

    「诛仙-陆雪琪」实录:同系列泛化标题的压缩包内目录名一样,
    旧逻辑按 slug 幂等跳过 → 1.5GB 下载成果躺在 library 不入库。
    """
    lib, media = tmp_path / "library", tmp_path / "media"
    _album(lib, "未分类", "Series Album", n=3)          # 第一批 3 张

    with SessionLocal() as s:
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 1
        # 同名目录再来一批,张数不同(2 张)→ 不再跳过
        _album(lib, "未分类", "Series Album", n=2)
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 1 and stats["skipped"] == 0
        b = _collection(s, "未分类-series-album-(2)")
        assert b is not None and len(b.photos) == 2
        assert b.title == "Series Album (2)"
        # 张数相同(3 张)→ 视为同批重复,仍跳过
        _album(lib, "未分类", "Series Album", n=3)
        stats = library_import.import_library(s, lib, media)
        assert stats["imported"] == 0 and stats["skipped"] == 1
        assert s.scalar(select(func.count()).select_from(Collection)
                        .where(Collection.slug == "未分类-series-album")) == 1


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
    assert admin_client.get("/t/400/yeha/visible-album/001.jpg").status_code == 200


# ---- 模特名查重:写法漂移不该建第二条(2026-10-27) ---------------------------

def _mk_model(s, slug: str, name: str) -> Model:
    m = Model(slug=slug, name=name, status="published")
    s.add(m)
    s.flush()
    return m


def test_model_lookup_matches_name_with_native_parens(tmp_path):
    """老条目名里带原生名括号(`Coco (瑚々)`),新规则抽出 `Coco` → 复用同一条。"""
    with SessionLocal() as s:
        old = _mk_model(s, "dedup-paren-probe-(瑚々)", "Dedup Paren Probe (瑚々)")
        got = library_import._get_or_create_model(s, "Dedup Paren Probe", "瑚々")
        assert got is not None and got.id == old.id
        assert s.scalar(select(func.count()).select_from(Model)
                        .where(Model.name.like("Dedup Paren Probe%"))) == 1


def test_model_lookup_matches_punctuation_variant(tmp_path):
    """`U Hwa` / `U.Hwa` 只是标点不同 → 同一条模特。"""
    with SessionLocal() as s:
        old = _mk_model(s, "dedup-dot-probe", "Dedup.Dot Probe")
        got = library_import._get_or_create_model(s, "Dedup Dot Probe", "")
        assert got is not None and got.id == old.id


def test_model_lookup_keeps_distinct_people_apart():
    with SessionLocal() as s:
        a = library_import._get_or_create_model(s, "Dedup Distinct One", "")
        b = library_import._get_or_create_model(s, "Dedup Distinct Two", "")
        assert a.id != b.id


def test_collection_slug_uses_existing_model_slug(tmp_path):
    """预检 slug 必须落在既有模特的 slug 前缀上,否则会重复下载/重复入库。"""
    with SessionLocal() as s:
        _mk_model(s, "dedup-slug-probe-(瑚々)", "Dedup Slug Probe (瑚々)")
        assert (library_import.collection_slug(s, "Dedup Slug Probe", "Album X")
                == "dedup-slug-probe-(瑚々)-album-x")
        assert not library_import.collection_exists(s, "Dedup Slug Probe", "Album X")


def test_import_reuses_model_matched_by_key(tmp_path):
    """端到端:库目录是 `Coco`,库里只有 `Coco (瑚々)` → 挂到那条,不新建。"""
    lib, media = tmp_path / "library", tmp_path / "media"
    album = _album(lib, "Dedup Import Probe", "Album Y", n=2)
    with SessionLocal() as s:
        old = _mk_model(s, "dedup-import-probe-(ぬ)", "Dedup Import Probe (ぬ)")
        library_import.import_album(s, album, media, library_root=lib, thumbs=False)
        c = _collection(s, "dedup-import-probe-(ぬ)-album-y")
        assert c is not None and c.model_id == old.id
        assert c.photos[0].filename.startswith("dedup-import-probe-(ぬ)/")
        assert s.scalar(select(func.count()).select_from(Model)
                        .where(Model.name.like("Dedup Import Probe%"))) == 1
