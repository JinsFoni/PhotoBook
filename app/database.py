"""数据库引擎与会话 — SQLite WAL。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

settings.ensure_dirs()

engine = create_engine(
    f"sqlite:///{settings.data_dir / 'photobook.db'}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from . import db  # noqa: F401  确保模型注册

    db.Base.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """轻量迁移:仅对已存在的旧库补列(create_all 不会改已有表)。幂等。"""
    stmts = (
        "ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT ''",
        "ALTER TABLE harvest_jobs ADD COLUMN archive_dir VARCHAR(500)",
        "ALTER TABLE harvest_jobs ADD COLUMN collection_slug VARCHAR(220)",
        "ALTER TABLE harvest_jobs ADD COLUMN updated_at TIMESTAMP",
        "ALTER TABLE collections ADD COLUMN source_serial INTEGER",
        "ALTER TABLE collections ADD COLUMN source_serials TEXT",
        "ALTER TABLE storages ADD COLUMN username VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE storages ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE storages ADD COLUMN manual_upload BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE storages ADD COLUMN direct_link BOOLEAN NOT NULL DEFAULT 1",
        "ALTER TABLE model_tags ADD COLUMN pos INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE collection_tags ADD COLUMN pos INTEGER NOT NULL DEFAULT 0",
    )
    with engine.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # 列已存在
    _backfill_tag_pos()
    _backfill_collection_slug()
    _backfill_source_serial()
    _backfill_cross_site_serials()
    _fix_url_unsafe_slugs()


def _backfill_tag_pos() -> None:
    """一次性回填:关联表 pos 列上线前的存量挂载,用 rowid(即当时的
    输入顺序)补齐。幂等:只更新 pos=0 的行。"""
    stmts = (
        "UPDATE model_tags SET pos = rowid - (SELECT MIN(rowid) FROM model_tags mt2 "
        "WHERE mt2.model_id = model_tags.model_id) WHERE pos = 0",
        "UPDATE collection_tags SET pos = rowid - (SELECT MIN(rowid) FROM collection_tags ct2 "
        "WHERE ct2.collection_id = collection_tags.collection_id) WHERE pos = 0",
    )
    with engine.connect() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
        conn.commit()


def _fix_url_unsafe_slugs() -> None:
    """一次性修复:存量 slug 含 URL 结构字符(# ? % &)导致链接被浏览器截断 404。

    slugify 旧版只拦 \\/:*?"<>| ,标题里的「#バケショ」等原样进 slug,而模板
    与前端都是 "/collections/" + slug 直拼(不编码)—— # 后全部被当 fragment,
    ?后当 query,页面 404(harvest 任务 285 实测)。

    修复三件事,均只对「含 URL 结构字符」的行动手,幂等:
    1. 重算 Model/Collection slug(用修复后的 slugify,冲突加 -2 序号);
    2. 同步媒体目录名与 Photo.filename 前缀(filename = 模特slug/写真slug尾/文件,
       见 import_album);
    3. 同步 harvest_jobs.collection_slug 引用(任务列表实时判态用)。
    """
    from sqlalchemy import select

    from .db import Collection, HarvestJob, Model, Photo
    from .services.library_import import _unique_slug, slugify

    bad_chars = set("#%&?")
    s = SessionLocal()
    try:
        media_root = settings.media_dir
        log = logging.getLogger("photobook")

        # ---- Model slug(也是 /media 的 owner 目录名) ----
        for m in s.scalars(select(Model)).all():
            if not any(ch in bad_chars for ch in m.slug):
                continue
            old = m.slug
            new = _unique_slug(s, Model, slugify(m.name, maxlen=120), 120)
            src = media_root / old
            dst = media_root / new
            if src.is_dir() and src != dst and not dst.exists():
                src.rename(dst)
                log.info("renamed media dir %s -> %s", old, new)
            for p in s.scalars(select(Photo).where(
                    Photo.filename.like(f"{old}/%"))).all():
                p.filename = new + p.filename[len(old):]
            m.slug = new
            log.info("model slug %s -> %s", old, new)
        s.flush()

        # ---- Collection slug(尾段 = dest_dir 目录名) ----
        for c in s.scalars(select(Collection)).all():
            if not any(ch in bad_chars for ch in c.slug):
                continue
            old = c.slug
            # owner 段从 Photo.filename 首段取权威值(= 模特slug或未分类目录名)
            first = s.scalars(select(Photo.filename).where(
                Photo.collection_id == c.id).limit(1)).first()
            owner = first.split("/", 1)[0] if first else old.split("-", 1)[0]
            old_title_slug = old[len(owner) + 1:] if old.startswith(owner + "-") else old
            title_slug = slugify(c.title, maxlen=160)
            new = _unique_slug(s, Collection, f"{owner}-{title_slug}"[:200], 200)
            new_title_slug = new[len(owner) + 1:] if new.startswith(owner + "-") else title_slug
            src = media_root / owner / old_title_slug
            dst = media_root / owner / new_title_slug
            if src.is_dir() and src != dst and not dst.exists():
                src.rename(dst)
                log.info("renamed media dir %s -> %s", src, dst)
            for p in s.scalars(select(Photo).where(
                    Photo.collection_id == c.id)).all():
                parts = p.filename.split("/", 2)  # owner / title_slug / file
                if len(parts) == 3 and parts[1] == old_title_slug:
                    p.filename = f"{parts[0]}/{new_title_slug}/{parts[2]}"
            s.execute(text(
                "UPDATE harvest_jobs SET collection_slug = :new WHERE collection_slug = :old"),
                {"new": new, "old": old})
            c.slug = new
            log.info("collection slug %s -> %s", old, new)

        s.commit()
    except Exception:
        s.rollback()
        logging.getLogger("photobook").exception("url-unsafe slug fix failed")
    finally:
        s.close()


def _backfill_source_serial() -> None:
    """一次性回填:存量采集导入的写真集无 source_serial, 浏览器联动无法判「已入库」。

    路径: job.collection_slug → collection, serial 从任务行直接拷贝。
    幂等: 只更新 source_serial 为空的行。与 _backfill_collection_slug 有先后依赖:
    它先补齐 job.collection_slug, 这里才能覆盖存量任务。
    """
    from sqlalchemy import select

    from .db import Collection, HarvestJob

    s = SessionLocal()
    try:
        jobs = s.scalars(select(HarvestJob).where(
            HarvestJob.collection_slug.is_not(None),
            HarvestJob.status.in_(["done", "exists"]))).all()
        if not jobs:
            return
        fixed = 0
        for job in jobs:
            col = s.scalar(select(Collection).where(Collection.slug == job.collection_slug))
            if col is None or col.source_serial is not None:
                continue
            col.source_serial = job.serial
            fixed += 1
        if fixed:
            s.commit()
            logging.getLogger("photobook").info(
                "backfilled source_serial on %d collections", fixed)
    except Exception:
        logging.getLogger("photobook").exception("source_serial backfill failed")
    finally:
        s.close()


def _backfill_cross_site_serials() -> None:
    """一次性回填:同一本写真在其他源站的序号(见 Collection.source_serials)。

    三站转载同一作品时序号体系各自独立(buondua 56556 ↔ misskon 117727),
    入库时只写下当前站的序号,另外两站的油猴链接因此永远显示「可下载」。
    这里按 harvest_history 的 title 与 collections.title 做跨站标题比对,
    把命中的其他站序号补进 source_serials。

    幂等: 只补 source_serials 为空的行;标题比对只在本次启动做一次,
    新增写真走 worker 的实时匹配(见 harvest.worker._link_cross_site_serials)。
    """
    import json

    from sqlalchemy import select

    from .db import Collection, HarvestHistory
    from .services.harvest.titlematch import titles_match

    s = SessionLocal()
    try:
        cols = s.scalars(select(Collection).where(
            Collection.source_serial.is_not(None),
            Collection.source_serials.is_(None))).all()
        if not cols:
            return
        hist = s.scalars(select(HarvestHistory)).all()
        if not hist:
            return
        fixed = 0
        for col in cols:
            own = {col.source_serial}
            extra = [h.serial for h in hist
                     if h.serial not in own and titles_match(h.title, col.title)]
            if not extra:
                # 无跨站序号也要落个空数组, 避免每次启动重跑全量比对
                col.source_serials = json.dumps([])
                continue
            col.source_serials = json.dumps(sorted(extra))
            fixed += 1
        s.commit()
        if fixed:
            logging.getLogger("photobook").info(
                "backfilled cross-site serials on %d collections", fixed)
    except Exception:
        logging.getLogger("photobook").exception("cross-site serial backfill failed")
    finally:
        s.close()


def _backfill_collection_slug() -> None:
    """一次性回填:存量「缩略图生成中」任务无 collection_slug,展示层无法实时判态。

    从任务的 error 文案(「N 张已入库」)与写真标题反查匹配的 collection:
    slug 由模特 slug + 标题 slugify 构成,标题在 DB 里精确存过 → 用 LIKE 前缀匹配。
    修复后展示文案即可正确变为「已完成」。幂等:只更新 slug 为空的行。
    """
    from sqlalchemy import select
    import re as _re

    from .db import Collection, HarvestJob
    from .services import library_import

    s = SessionLocal()
    try:
        jobs = s.scalars(select(HarvestJob).where(
            HarvestJob.collection_slug.is_(None),
            HarvestJob.status == "done",
            HarvestJob.error.like("%缩略图生成中%"))).all()
        if not jobs:
            return
        fixed = 0
        for job in jobs:
            # 标题形如 "Coser@蠢沫沫 (chunmomo): 阳 (31 photos)  -" → 取冒号后的纯标题
            m = _re.search(r"[:\uFF1A]\s*(.+?)(?:\s*\(\d+\s*photos?\))?\s*-?\s*$",
                           job.title or "")
            if not m:
                continue
            title_part = m.group(1).strip()
            col = s.scalars(select(Collection).where(
                Collection.title.like(f"%{title_part}%"))).first()
            if col is None:
                continue
            job.collection_slug = col.slug
            fixed += 1
        if fixed:
            s.commit()
            logging.getLogger("photobook").info(
                "backfilled collection_slug on %d harvest jobs", fixed)
    except Exception:
        logging.getLogger("photobook").exception("collection_slug backfill failed")
    finally:
        s.close()


@contextmanager
def get_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖。"""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def db_ready() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
