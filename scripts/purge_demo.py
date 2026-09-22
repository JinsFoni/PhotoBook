"""一次性清理:删除内置 demo 写真(数据行 + 磁盘文件),只保留采集内容。

- 范围:filename like 'demo/%' 的照片行、相关集合/模特/标签、demo 收藏、demo 磁盘目录
- 不动:用户、采集写真(media/ 下非 demo 目录)、采集集合/模特、settings/harvest 表
- 幂等:可重复执行;SEED_DEMO 未开时重启不会再生成

用法: .venv/bin/python scripts/purge_demo.py [--dry-run]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.db import Collection, CollectionTag, Favorite, Model, ModelTag, Photo, Tag


def main(dry_run: bool = False) -> None:
    s = SessionLocal()
    stats = {"photos": 0, "collections": 0, "models": 0, "tags": 0,
             "fav_collections": 0, "fav_models": 0, "fav_photos": 0}

    # ---- 照片行 + 对应集合 ------------------------------------------------
    demo_files = list(s.scalars(select(Photo.filename)
                                .where(Photo.filename.like("demo/%"))).all())
    demo_col_ids = [cid for (cid,) in s.execute(
        select(Photo.collection_id).where(Photo.filename.like("demo/%")).distinct()).all()]
    stats["photos"] = len(demo_files)
    stats["collections"] = len(demo_col_ids)

    # ---- 种子模特(头像在 demo/avatars/ 下即种子;采集模特 avatar 为 NULL) --
    demo_model_ids = [m.id for m in s.scalars(select(Model)).all()
                      if m.avatar_path and m.avatar_path.startswith("demo/")]
    stats["models"] = len(demo_model_ids)

    # ---- 种子标签(仅被种子集合/模特引用的才删) ---------------------------
    used_tag_ids = set()
    for cid in demo_col_ids:
        used_tag_ids.update(s.scalars(select(CollectionTag.tag_id)
                                      .where(CollectionTag.collection_id == cid)).all())
    for mid in demo_model_ids:
        used_tag_ids.update(s.scalars(select(ModelTag.tag_id)
                                      .where(ModelTag.model_id == mid)).all())
    stats["tags"] = len(used_tag_ids)

    # ---- demo 收藏 --------------------------------------------------------
    for f in s.scalars(select(Favorite)).all():
        if f.target_type == "photo" and f.target_key.startswith("demo/"):
            stats["fav_photos"] += 1
        elif f.target_type == "collection":
            if f.target_key in [x for x in s.scalars(
                    select(Collection.slug).where(Collection.id.in_(demo_col_ids))).all()]:
                stats["fav_collections"] += 1
        elif f.target_type == "model" and f.target_key in [x for x in s.scalars(
                select(Model.slug).where(Model.id.in_(demo_model_ids))).all()]:
            stats["fav_models"] += 1

    if dry_run:
        print("[dry-run] 将删除:", stats)
        s.close()
        return

    # ---- 执行删除(顺序:引用方 → 被引用方) --------------------------------
    if demo_files:
        s.query(Photo).filter(Photo.filename.like("demo/%")) \
            .delete(synchronize_session=False)
    for f in s.scalars(select(Favorite)).all():
        drop = (f.target_type == "photo" and f.target_key.startswith("demo/")) \
            or (f.target_type == "collection"
                and s.scalar(select(Collection.id)
                             .where(Collection.slug == f.target_key)) in demo_col_ids) \
            or (f.target_type == "model"
                and s.scalar(select(Model.id)
                             .where(Model.slug == f.target_key)) in demo_model_ids)
        if drop:
            s.delete(f)
    if demo_col_ids:
        s.query(CollectionTag).filter(CollectionTag.collection_id.in_(demo_col_ids)) \
            .delete(synchronize_session=False)
        s.query(Collection).filter(Collection.id.in_(demo_col_ids)) \
            .delete(synchronize_session=False)
    if demo_model_ids:
        s.query(ModelTag).filter(ModelTag.model_id.in_(demo_model_ids)) \
            .delete(synchronize_session=False)
        s.query(Model).filter(Model.id.in_(demo_model_ids)) \
            .delete(synchronize_session=False)
    if used_tag_ids:
        s.query(Tag).filter(Tag.id.in_(used_tag_ids)) \
            .delete(synchronize_session=False)
    s.commit()
    s.close()

    # ---- 磁盘文件 ----------------------------------------------------------
    demo_dir = settings.media_dir / "demo"
    if demo_dir.is_dir():
        n_files = sum(1 for _ in demo_dir.rglob("*") if _.is_file())
        shutil.rmtree(demo_dir)
        print(f"已删除磁盘目录 {demo_dir}({n_files} 个文件)")
    else:
        print("磁盘无 demo/ 目录(已清)")

    # ---- 缩略图缓存里的 demo 条目(可选,不清也只是占点空间) ---------------
    n_cache = 0
    cache_root = settings.media_dir / "_cache"
    if cache_root.is_dir():
        for sub in cache_root.iterdir():
            if sub.is_dir():
                for d in list(sub.glob("demo")):
                    shutil.rmtree(d, ignore_errors=True)
                    n_cache += 1
    print(f"缓存中 demo 目录清理: {n_cache} 处")
    print("删除统计:", stats)
    print("完成。重启服务后生效(SEED_DEMO 保持关闭则不会再生成)。")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
