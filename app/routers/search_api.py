"""站内搜索 API — 全站搜索框的数据源。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import Collection, Model, Tag, VideoAlbum
from ..database import get_db
from ..i18n import t
from ..services.media import thumb_url

router = APIRouter(prefix="/api/search", dependencies=[Depends(require_login)])


def _thumb(rel: str | None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    return thumb_url(rel.lstrip("/"), 160)


def _video_thumb(rel: str | None) -> str:
    """视频封面缩略图:poster rel 已是 /t 缓存同构路径,直接拼 160 档。

    poster 为空(ffmpeg 缺失)时给透明占位 —— 前端搜索行图片加载失败会
    显示底色,不影响点击。
    """
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
        return {"q": "", "models": [], "collections": [], "videos": [], "tags": []}
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

    # 视频专辑(与写真集平行的独立模块)
    albums = s.scalars(
        select(VideoAlbum).where(VideoAlbum.status == "published")
        .order_by(VideoAlbum.published_at.desc())).all()
    hit_albums = [a for a in albums
                  if q.lower() in (a.title + " " +
                                   (a.model.name if a.model else "") + " " +
                                   " ".join(t.name for t in a.tags)).lower()][:10]

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
        "videos": [{"slug": a.slug, "title": a.title,
                    "model_name": a.model.name if a.model else t("未分类"),
                    "count": len(a.videos), "date": a.published_at or "",
                    "thumb": _video_thumb(_album_cover_poster(a))}
                   for a in hit_albums],
        "tags": hit_tags,
    }


def _album_cover_poster(a: VideoAlbum) -> str | None:
    """视频专辑封面 poster(优先 cover_video,回退首个有 poster 的)。"""
    for v in a.videos:
        if a.cover_video_id and v.id == a.cover_video_id and v.poster:
            return v.poster
    for v in a.videos:
        if v.poster:
            return v.poster
    return None
