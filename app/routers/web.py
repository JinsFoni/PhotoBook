"""用户端页面 — Discovery / Models / Collection / Videos / Favorites / Profile。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import (Collection, Favorite, Model, Photo, Tag, User, Video,
                  VideoAlbum)
from ..database import SessionLocal, get_db
from ..i18n import t
from ..templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def _fav_keys(s: Session, user_id: int) -> dict[str, set[str]]:
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user_id)).all()
    out: dict[str, set[str]] = {"model": set(), "collection": set(), "photo": set(),
                                "video_album": set(), "video": set()}
    for r in rows:
        if r.target_type in out:
            out[r.target_type].add(r.target_key)
    return out


def _collection_cover(s: Session, c: Collection) -> str | None:
    """列表用封面文件名: 优先 cover_photo_id(避免为拿第一张图拖全 photos),
    兼容老数据/手动建集合回退第一张。"""
    if c.cover_photo_id:
        ph = s.get(Photo, c.cover_photo_id)
        if ph:
            return ph.filename
    ph = s.scalar(select(Photo).where(Photo.collection_id == c.id)
                  .order_by(Photo.sort_order).limit(1))
    return ph.filename if ph else None


def _collection_card(s: Session, c: Collection) -> dict:
    """列表/网格卡片的瘦身条目: 不带 photos 数组, 体积约为完整 payload 的 1/30。
    用在哪: /collections 虚拟化数据池(万级条目也轻)。"""
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "",
        # 入库日期(YYYY-MM-DD,客户端「最新/最早入库」排序用)
        "created": c.created_at.date().isoformat() if c.created_at else "",
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else t("未分类"),
        "cover": _collection_cover(s, c),
        "count": len(c.photos),
        "tags": [t.name for t in c.tags],
    }


def _collection_payload(s: Session, c: Collection) -> dict:
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "", "featured": c.featured,
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else t("未分类"),
        "cover": _collection_cover(s, c),
        "photos": [{"id": p.id, "file": p.filename, "w": p.width, "h": p.height}
                   for p in c.photos],
        "tags": [t.name for t in c.tags],
        "count": len(c.photos),
    }


def _model_payload(s: Session, m: Model, collections: list[Collection] | None = None) -> dict:
    works = collections if collections is not None else m.collections
    photo_count = sum(len(c.photos) for c in works)
    albums = [a for a in m.video_albums if a.status == "published"]
    video_count = sum(len(a.videos) for a in albums)
    # 最新活动日期:作品集里最新的发布日期(模特页「排序:最新」用)
    latest = max((c.published_at or "" for c in works), default="")
    # 头像兜底:没设头像时用第一张合集封面
    avatar = m.avatar_path
    if not avatar:
        for c in works:
            if c.photos:
                avatar = c.photos[0].filename
                break
    return {
        "id": m.id, "slug": m.slug, "name": m.name, "stage": m.stage_name or "",
        "avatar": avatar, "hero": m.hero_path or avatar,
        "gender": m.gender or "", "age": m.age, "height": m.height,
        "measurements": m.measurements, "agency": m.agency or "", "bio": m.bio or "",
        "since": m.since or "", "featured": m.featured, "latest": latest,
        "tags": [t.name for t in m.tags],
        "count": len(works), "photoCount": photo_count,
        # 视频模块(独立于写真集的平行模块)
        "videoAlbumCount": len(albums), "videoCount": video_count,
    }


def _published_collections(s: Session) -> list[Collection]:
    return list(s.scalars(
        select(Collection).where(Collection.status == "published")
        .options()  # photos lazy selectin via relationship
        .order_by(desc(Collection.published_at), desc(Collection.id))).all())


# ---- 视频模块(与写真集平行的独立模块) ----------------------------------------

def _video_album_cover(s: Session, a: VideoAlbum) -> str | None:
    """列表用封面 rel:优先 cover_video 的 poster,回退首个有 poster 的视频。

    封面走 /t/s900/ 缓存(与照片同构),poster 为空(ffmpeg 缺失)时回退 None,
    前端再兜底占位图。
    """
    if a.cover_video_id:
        v = s.get(Video, a.cover_video_id)
        if v and v.poster:
            return v.poster
    for v in a.videos:
        if v.poster:
            return v.poster
    return None


def _video_album_card(s: Session, a: VideoAlbum) -> dict:
    """视频专辑瘦身条目(与 _collection_card 平行)。"""
    return {
        "id": a.id, "slug": a.slug, "title": a.title,
        "date": a.published_at or "",
        "created": a.created_at.date().isoformat() if a.created_at else "",
        "model_slug": a.model.slug if a.model else "",
        "model_name": a.model.name if a.model else t("未分类"),
        "cover": _video_album_cover(s, a),
        "count": len(a.videos),
        "tags": [t.name for t in a.tags],
    }


def _video_album_payload(s: Session, a: VideoAlbum) -> dict:
    return {
        "id": a.id, "slug": a.slug, "title": a.title,
        "date": a.published_at or "", "featured": a.featured,
        "model_slug": a.model.slug if a.model else "",
        "model_name": a.model.name if a.model else t("未分类"),
        "cover": _video_album_cover(s, a),
        "videos": [{"id": v.id, "file": v.filename, "w": v.width, "h": v.height,
                    "duration": v.duration, "poster": v.poster}
                   for v in a.videos],
        "tags": [t.name for t in a.tags],
        "count": len(a.videos),
    }


def _published_video_albums(s: Session) -> list[VideoAlbum]:
    return list(s.scalars(
        select(VideoAlbum).where(VideoAlbum.status == "published")
        .order_by(desc(VideoAlbum.published_at), desc(VideoAlbum.id))).all())


# ---- Discovery --------------------------------------------------------------

@router.get("/")
async def discovery(request: Request, s: Session = Depends(get_db)):
    user = request.state.user
    cols = _published_collections(s)
    featured = [c for c in cols if c.featured][:16] or cols[:16]
    latest = cols[:6]
    models = s.scalars(select(Model).where(Model.status == "published")
                       .order_by(desc(Model.featured), Model.name)).all()
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()

    tag_counts = {}
    for c in cols:
        for t in c.tags:
            d = tag_counts.setdefault(t.name, {"collections": 0, "models": set()})
            d["collections"] += 1
            if c.model:
                d["models"].add(c.model.slug)

    payload = {
        "featured": [_collection_payload(s, c) for c in featured],
        "latest": [_collection_payload(s, c) for c in latest],
        "models": [_model_payload(s, m, [c for c in cols if c.model_id == m.id]) for m in models],
        "tags": [{"name": t.name, "collections": tag_counts.get(t.name, {}).get("collections", 0),
                  "models": len(tag_counts.get(t.name, {}).get("models", set()))} for t in tags],
        "stats": {"collections": len(cols), "models": len(models)},
    }
    return templates.TemplateResponse(request, "discovery.html", {
        "user": user, "page": "discovery", "data": payload,
        "data_json": json.dumps(payload, ensure_ascii=False),
        "shell_immersive": True,  # 顶栏压在 Hero 轮播上(沉浸式)
    })


# ---- Collections ------------------------------------------------------------

@router.get("/collections")
async def collections_page(request: Request, s: Session = Depends(get_db),
                           q: str = "", tag: str = "", model: str = ""):
    user = request.state.user
    cols = _published_collections(s)
    models = s.scalars(select(Model).where(Model.status == "published").order_by(Model.name)).all()
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()

    items = [_collection_card(s, c) for c in cols]

    tag_counts = {}
    for c in cols:
        for t in c.tags:
            tag_counts[t.name] = tag_counts.get(t.name, 0) + 1

    payload = {
        "collections": items,
        "models": [{"slug": m.slug, "name": m.name} for m in models],
        "tags": [{"name": t.name, "collections": tag_counts.get(t.name, 0)} for t in tags],
        "filters": {"q": q, "tag": tag, "model": model},
    }
    return templates.TemplateResponse(request, "collections.html", {
        "user": user, "page": "collections",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


@router.get("/collections/{slug}")
async def collection_detail(request: Request, slug: str, s: Session = Depends(get_db)):
    user = request.state.user
    c = s.scalar(select(Collection).where(Collection.slug == slug))
    if not c or c.status != "published":
        text = t("We couldn't find that {w}. The link may be out of date.", w=t("写真"))
        return templates.TemplateResponse(request, "notfound.html",
                                          {"user": user, "page": "collections", "text": text},
                                          status_code=404)
    payload = _collection_payload(s, c)
    same_model = [x for x in (s.scalars(
        select(Collection).where(Collection.model_id == c.model_id,
                                 Collection.status == "published")).all()
        if c.model_id else []) if x.slug != c.slug]
    others = [x for x in _published_collections(s) if x.slug != c.slug and x.model_id != c.model_id][:5]
    next_cols = (same_model + others)[:5]
    payload["next"] = [_collection_payload(s, x) for x in next_cols]
    payload["next_aside"] = c.model.name if (same_model and c.model) else ""
    return templates.TemplateResponse(request, "collection.html", {
        "user": user, "page": "collections",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


# ---- Videos(视频模块,与写真集平行) --------------------------------------------

@router.get("/videos")
async def videos_page(request: Request, s: Session = Depends(get_db),
                      q: str = "", tag: str = "", model: str = ""):
    user = request.state.user
    albums = _published_video_albums(s)
    models = s.scalars(select(Model).where(Model.status == "published")
                       .order_by(Model.name)).all()
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()

    items = [_video_album_card(s, a) for a in albums]

    tag_counts = {}
    for a in albums:
        for t in a.tags:
            tag_counts[t.name] = tag_counts.get(t.name, 0) + 1

    payload = {
        "albums": items,
        "models": [{"slug": m.slug, "name": m.name} for m in models],
        "tags": [{"name": t.name, "albums": tag_counts.get(t.name, 0)} for t in tags],
        "filters": {"q": q, "tag": tag, "model": model},
    }
    return templates.TemplateResponse(request, "videos.html", {
        "user": user, "page": "videos",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


@router.get("/videos/{slug}")
async def video_detail(request: Request, slug: str, s: Session = Depends(get_db)):
    user = request.state.user
    a = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug))
    if not a or a.status != "published":
        text = t("We couldn't find that {w}. The link may be out of date.", w=t("视频"))
        return templates.TemplateResponse(request, "notfound.html",
                                          {"user": user, "page": "videos", "text": text},
                                          status_code=404)
    payload = _video_album_payload(s, a)
    same_model = [x for x in (s.scalars(
        select(VideoAlbum).where(VideoAlbum.model_id == a.model_id,
                                 VideoAlbum.status == "published")).all()
        if a.model_id else []) if x.slug != a.slug]
    others = [x for x in _published_video_albums(s)
              if x.slug != a.slug and x.model_id != a.model_id][:5]
    next_albums = (same_model + others)[:5]
    payload["next"] = [_video_album_payload(s, x) for x in next_albums]
    payload["next_aside"] = a.model.name if (same_model and a.model) else ""
    return templates.TemplateResponse(request, "video.html", {
        "user": user, "page": "videos",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


# ---- Models -------------------------------------------------------------------

@router.get("/models")
async def models_page(request: Request, s: Session = Depends(get_db),
                      q: str = "", gender: str = "", tag: str = "", agency: str = ""):
    user = request.state.user
    models = s.scalars(select(Model).where(Model.status == "published").order_by(Model.name)).all()
    cols = _published_collections(s)
    agencies = sorted({m.agency for m in models if m.agency})
    tag_set = sorted({t.name for m in models for t in m.tags})

    payload = {
        "models": [_model_payload(s, m, [c for c in cols if c.model_id == m.id]) for m in models],
        "agencies": agencies, "tags": tag_set,
        "filters": {"q": q, "gender": gender, "tag": tag, "agency": agency},
    }
    return templates.TemplateResponse(request, "models.html", {
        "user": user, "page": "models",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


@router.get("/models/{slug}")
async def model_detail(request: Request, slug: str, s: Session = Depends(get_db)):
    user = request.state.user
    m = s.scalar(select(Model).where(Model.slug == slug))
    if not m or m.status != "published":
        text = t("We couldn't find that {w}. The link may be out of date.", w=t("模特"))
        return templates.TemplateResponse(request, "notfound.html",
                                          {"user": user, "page": "models", "text": text},
                                          status_code=404)
    payload = _model_payload(s, m)
    # 写真集按最新在前(与全站列表一致); 无发布日期的排最后
    works = [c for c in m.collections if c.status == "published"]
    works.sort(key=lambda c: (c.published_at or "", c.id), reverse=True)
    payload["works"] = [_collection_payload(s, c) for c in works]
    return templates.TemplateResponse(request, "model.html", {
        "user": user, "page": "models",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


# ---- Favorites ---------------------------------------------------------------

@router.get("/favorites")
async def favorites_page(request: Request, s: Session = Depends(get_db), tab: str = "model"):
    user = request.state.user
    favs = _fav_keys(s, user.id)

    models = s.scalars(select(Model).where(Model.status == "published")).all()
    cols = _published_collections(s)
    model_items = [_model_payload(s, m, [c for c in cols if c.model_id == m.id])
                   for m in models if m.slug in favs["model"]]
    collection_items = [_collection_payload(s, c) for c in cols if c.slug in favs["collection"]]

    # 收藏的照片:target_key = "<collection_slug>:<idx>"
    # w/h 必带: justified 照片墙(layoutPhotoWall)按宽高比分行,图片未加载时
    # 只能读模板内联 aspect-ratio,缺了会全部按 2/3 兜底 → 横图卡留洞。
    # gi 是本页照片列表的全局下标, 灯箱按它直接定位当前张。
    photo_items = []
    for c in cols:
        for i, p in enumerate(c.photos):
            key = f"{c.slug}:{i}"
            if key in favs["photo"]:
                photo_items.append({"key": key, "file": p.filename, "id": p.id,
                                    "w": p.width, "h": p.height, "gi": len(photo_items),
                                    "collection": c.slug, "title": c.title, "index": i})

    # 收藏的视频专辑(键 = album slug)与单个视频(键 = "<album_slug>:v<idx>",
    # v 前缀与照片的 "<slug>:<idx>" 区分,两个模块的键不会撞)
    albums = _published_video_albums(s)
    video_album_items = [_video_album_payload(s, a) for a in albums
                         if a.slug in favs["video_album"]]
    video_items = []
    for a in albums:
        for i, v in enumerate(a.videos):
            key = f"{a.slug}:v{i}"
            if key in favs["video"]:
                video_items.append({"key": key, "file": v.filename, "id": v.id,
                                    "w": v.width, "h": v.height, "duration": v.duration,
                                    "poster": v.poster, "gi": len(video_items),
                                    "album": a.slug, "title": a.title, "index": i})

    payload = {
        "models": model_items, "collections": collection_items, "photos": photo_items,
        "videoAlbums": video_album_items, "videos": video_items,
        "counts": {"model": len(model_items), "collection": len(collection_items),
                   "photo": len(photo_items), "video_album": len(video_album_items),
                   "video": len(video_items)},
        "tab": tab,
    }
    return templates.TemplateResponse(request, "favorites.html", {
        "user": user, "page": "favorites",
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


# ---- Profile ----------------------------------------------------------------

# 头像选择器可选项: 用户名本身 + 6 个预设种子(与色板一一对应观感)
AVATAR_SEEDS = ["lens-brass", "lens-celadon", "lens-violet", "lens-amber", "lens-steel", "lens-crimson"]


@router.get("/profile")
async def profile_page(request: Request, s: Session = Depends(get_db)):
    user = request.state.user
    favs = _fav_keys(s, user.id)
    cols = _published_collections(s)
    recent = [_collection_payload(s, c) for c in cols if c.slug in favs["collection"]][:3]
    payload = {
        "user": {"name": user.username, "role": user.role},
        "counts": {k: len(v) for k, v in favs.items()},
        "recent": recent,
        "recent_empty": not recent,
    }
    return templates.TemplateResponse(request, "profile.html", {
        "user": user, "page": "profile",
        "counts": {k: len(v) for k, v in favs.items()},
        "recent": recent, "recent_empty": not recent,
        "avatar_seeds": AVATAR_SEEDS,
        "data_json": json.dumps(payload, ensure_ascii=False),
    })


@router.post("/avatar")
async def set_avatar(request: Request, seed: str = Form(""), next: str = Form("")):
    """设置头像种子(生成式头像, 无上传)。"""
    user = request.state.user
    seed = seed.strip()[:64]
    s = SessionLocal()
    try:
        u = s.get(User, user.id)
        if u:
            u.avatar_seed = seed
            s.commit()
    finally:
        s.close()
    nxt = next or "/profile#settings"
    if not nxt.startswith("/"):
        nxt = "/profile#settings"
    return RedirectResponse(nxt, 303)
