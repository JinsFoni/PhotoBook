"""删除写真集后的磁盘清理: 原图目录 + 缩略图缓存 + 收藏记录。"""

from __future__ import annotations

import os


def _mk_collection_with_photos():
    """造一个写真集: 2 张图(直接写文件 + DB 行), 返回 (slug, 文件相对路径)。"""
    from app.database import SessionLocal
    from app.db import Collection, Model, Photo
    from app.config import settings

    slug = "purge-target"
    rels = ["purge-owner/purge-target/a.jpg", "purge-owner/purge-target/b.jpg"]
    s = SessionLocal()
    try:
        m = s.query(Model).filter(Model.name == "purge-owner").first()
        if not m:
            m = Model(name="purge-owner", slug="purge-owner")
            s.add(m); s.flush()
        c = Collection(slug=slug, title="purge target", model_id=m.id,
                       published_at="2026.09.30", status="published")
        s.add(c); s.flush()
        for i, rel in enumerate(rels):
            p = settings.media_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            import io as _io
            from PIL import Image as _Image
            _buf = _io.BytesIO()
            _Image.new("RGB", (8, 12), (200, 120, 90)).save(_buf, "JPEG")
            p.write_bytes(_buf.getvalue())
            s.add(Photo(collection_id=c.id, filename=rel, sort_order=i))
        s.commit()
    finally:
        s.close()
    return slug, rels


def _gen_thumbs(rel: str):
    from app.services.media import ensure_cached
    assert ensure_cached(rel, 900)
    assert ensure_cached(rel, 1800)


def _cache_paths(rel: str) -> list[str]:
    from app.config import settings
    from app.services.media import PREHEAT_WIDTHS
    out = []
    for w in PREHEAT_WIDTHS:
        q = 88 if w >= 1600 else 78
        out.append(str(settings.media_dir / "_cache" / f"{w}x0q{q}" / f"{rel}.webp"))
    return out


def test_delete_collection_purges_cache_files_and_favourites(admin_client):
    from app.config import settings
    from app.database import SessionLocal
    from app.db import Collection, Favorite, User

    slug, rels = _mk_collection_with_photos()
    for rel in rels:
        _gen_thumbs(rel)
    for p in _cache_paths(rels[0]):
        assert os.path.isfile(p), p

    # 用户收藏该写真集与其中一张照片
    s = SessionLocal()
    try:
        uid = s.query(User).filter(User.username == "admin").one().id
        s.add(Favorite(user_id=uid, target_type="collection", target_key=slug))
        s.add(Favorite(user_id=uid, target_type="photo", target_key=f"{slug}:0"))
        s.commit()
        cid = s.query(Collection).filter(Collection.slug == slug).one().id
    finally:
        s.close()

    r = admin_client.post(f"/admin/collections/{cid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    # 缩略图缓存全清
    for rel in rels:
        for p in _cache_paths(rel):
            assert not os.path.exists(p), f"cache residue: {p}"
    # 空的原图目录一并移除
    assert not (settings.media_dir / "purge-owner" / "purge-target").exists()
    assert not (settings.media_dir / "purge-owner").exists()
    # 收藏记录清除
    s = SessionLocal()
    try:
        n = s.query(Favorite).filter(
            (Favorite.target_type == "collection") & (Favorite.target_key == slug)
            | (Favorite.target_type == "photo") & (Favorite.target_key.like(f"{slug}:%"))).count()
        assert n == 0
    finally:
        s.close()


def test_delete_keeps_album_dir_with_stray_files(admin_client):
    """目录里有非本写真集的文件时只清缩略图与 DB, 原图目录保留(防误删)。"""
    from app.config import settings
    from app.database import SessionLocal
    from app.db import Collection

    slug, rels = _mk_collection_with_photos()
    # 目录里塞一个外来文件
    album = settings.media_dir / "purge-owner" / "purge-target"
    stray = album / "stray.txt"
    stray.write_text("keep me")

    s = SessionLocal()
    try:
        cid = s.query(Collection).filter(Collection.slug == slug).one().id
    finally:
        s.close()
    assert admin_client.post(f"/admin/collections/{cid}/delete",
                             follow_redirects=False).status_code in (302, 303)
    # 外来文件仍在, 目录保留
    assert stray.is_file()
    # 但缩略图缓存已清
    for rel in rels:
        for p in _cache_paths(rel):
            assert not os.path.exists(p)


def test_delete_model_purges_its_collections(admin_client):
    """删模特连带其全部写真集的磁盘清理(照片/缩略图/收藏)。"""
    from app.config import settings
    from app.database import SessionLocal
    from app.db import Collection, Model

    slug, rels = _mk_collection_with_photos()
    for rel in rels:
        _gen_thumbs(rel)
    s = SessionLocal()
    try:
        mid = s.query(Model).filter(Model.slug == "purge-owner").one().id
    finally:
        s.close()
    assert admin_client.post(f"/admin/models/{mid}/delete", follow_redirects=False).status_code in (302, 303)
    for rel in rels:
        assert not (settings.media_dir / rel).exists()
        for p in _cache_paths(rel):
            assert not os.path.exists(p)
    s = SessionLocal()
    try:
        assert s.query(Collection).filter(Collection.slug == slug).count() == 0
    finally:
        s.close()


def test_delete_last_collection_removes_model(admin_client):
    """模特名下最后一套写真被删时, 模特一并删除。"""
    from app.database import SessionLocal
    from app.db import Collection, Model

    slug, rels = _mk_collection_with_photos()  # 模特 purge-owner, 1 套写真
    s = SessionLocal()
    try:
        mid = s.query(Model).filter(Model.slug == "purge-owner").one().id
        cid = s.query(Collection).filter(Collection.slug == slug).one().id
    finally:
        s.close()
    assert admin_client.post(f"/admin/collections/{cid}/delete", follow_redirects=False).status_code in (302, 303)
    s = SessionLocal()
    try:
        assert s.query(Model).filter(Model.id == mid).count() == 0
    finally:
        s.close()


def test_delete_one_collection_keeps_model_with_others(admin_client):
    """模特还有其它写真集时, 删一套不影响模特。"""
    from app.database import SessionLocal
    from app.db import Collection, Model

    slug1, _ = _mk_collection_with_photos()
    # 给同一模特再挂一套(空照片列表也行, 只为占位)
    s = SessionLocal()
    try:
        m = s.query(Model).filter(Model.slug == "purge-owner").one()
        s.add(Collection(slug="purge-target-2", title="pt2", model_id=m.id,
                         published_at="2026.09.30", status="published"))
        s.commit()
        mid, cid1 = m.id, s.query(Collection).filter(Collection.slug == slug1).one().id
    finally:
        s.close()
    assert admin_client.post(f"/admin/collections/{cid1}/delete", follow_redirects=False).status_code in (302, 303)
    s = SessionLocal()
    try:
        assert s.query(Model).filter(Model.id == mid).count() == 1  # 模特还在
        assert s.query(Collection).filter(Collection.slug == "purge-target-2").count() == 1
    finally:
        s.close()
    # 收尾: 删掉第二套和模特, 不污染其它测试
    s = SessionLocal()
    try:
        cid2 = s.query(Collection).filter(Collection.slug == "purge-target-2").one().id
    finally:
        s.close()
    admin_client.post(f"/admin/collections/{cid2}/delete", follow_redirects=False)
    s = SessionLocal()
    try:
        assert s.query(Model).filter(Model.slug == "purge-owner").count() == 0
    finally:
        s.close()
