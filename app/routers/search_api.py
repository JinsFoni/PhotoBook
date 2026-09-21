"""站内搜索 API — 全站搜索框的数据源。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import Collection, Model, Tag
from ..database import get_db
from ..i18n import t
from ..services.media import thumb_url

router = APIRouter(prefix="/api/search", dependencies=[Depends(require_login)])


def _thumb(rel: str | None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    return thumb_url(rel.lstrip("/"), 160)


def _model_thumb(m: Model) -> str:
    """搜索行缩略图:头像缺省时用第一张合集封面。"""
    rel = m.avatar_path
    if not rel:
        for c in m.collections:
            if c.photos:
                rel = c.photos[0].filename
                break
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

    return {
        "q": q,
        "models": [{"slug": m.slug, "name": m.name, "tags": [t.name for t in m.tags],
                    "count": len(m.collections), "thumb": _model_thumb(m)}
                   for m in hit_models],
        "collections": [{"slug": c.slug, "title": c.title,
                         "model_name": c.model.name if c.model else t("未分类"),
                         "count": len(c.photos), "date": c.published_at or "",
                         "thumb": _thumb(c.photos[0].filename if c.photos else None)}
                        for c in hit_cols],
        "tags": hit_tags,
    }
