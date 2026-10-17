"""站内搜索 API — 全站搜索框的数据源。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import Collection, Model, Photo, Tag
from ..database import get_db
from ..i18n import t
from ..services.media import thumb_url

router = APIRouter(prefix="/api/search", dependencies=[Depends(require_login)])


def _thumb(rel: str | None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    # 全站只预热 s900/s2400 两档,其余规格冷生成会回源云盘
    return thumb_url(rel.lstrip("/"), 900, short=True)


def _model_thumb(s: Session, m: Model) -> str:
    """搜索行缩略图:头像缺省时用第一张合集封面(标量查询,不拖全 photos)。"""
    rel = m.avatar_path
    if not rel:
        rel = s.scalar(
            select(Photo.filename)
            .join(Collection, Collection.id == Photo.collection_id)
            .where(Collection.model_id == m.id, Collection.status == "published")
            .order_by(Collection.published_at.desc(), Photo.sort_order)
            .limit(1))
    return _thumb(rel)


@router.get("")
async def search(q: str = Query(""), s: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return {"q": "", "models": [], "collections": [], "tags": []}
    like = f"%{q}%"

    models = s.scalars(
        select(Model).where(Model.status == "published").order_by(Model.name)).all()
    hit_models = [m for m in models
                  if q.lower() in (m.name + " " + (m.stage_name or "") + " " +
                                   " ".join(t.name for t in m.tags) + " " +
                                   (m.agency or "")).lower()][:8]

    cols = s.scalars(
        select(Collection).where(Collection.status == "published")
        .order_by(Collection.published_at.desc())).all()
    hit_cols = [c for c in cols
                if q.lower() in (c.title + " " +
                                 (c.model.name if c.model else "") + " " +
                                 " ".join(t.name for t in c.tags)).lower()][:10]

    tags = s.scalars(select(Tag).order_by(Tag.name)).all()
    hit_tags = [t.name for t in tags if q.lower() in t.name.lower()][:8]

    # 照片数 + 封面文件名:两条聚合/标量查询(替代逐合集加载全部照片)
    counts = dict(s.execute(
        select(Photo.collection_id, func.count(Photo.id))
        .where(Photo.collection_id.in_([c.id for c in hit_cols]))
        .group_by(Photo.collection_id)).all()) if hit_cols else {}
    covers = dict(s.execute(
        select(Photo.collection_id, func.min(Photo.filename))
        .where(Photo.collection_id.in_([c.id for c in hit_cols]))
        .group_by(Photo.collection_id)).all()) if hit_cols else {}

    return {
        "q": q,
        "models": [{"slug": m.slug, "name": m.name, "tags": [t.name for t in m.tags],
                    "count": len(m.collections), "thumb": _model_thumb(s, m)}
                   for m in hit_models],
        "collections": [{"slug": c.slug, "title": c.title,
                         "model_name": c.model.name if c.model else t("未分类"),
                         "count": counts.get(c.id, 0), "date": c.published_at or "",
                         "thumb": _thumb(covers.get(c.id))}
                        for c in hit_cols],
        "tags": hit_tags,
    }
