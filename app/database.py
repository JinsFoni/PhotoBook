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
        "ALTER TABLE collections ADD COLUMN source_serial INTEGER",
    )
    with engine.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # 列已存在
    _backfill_collection_slug()
    _backfill_source_serial()


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
