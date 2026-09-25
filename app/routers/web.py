"""用户端页面 — Discovery / Models / Collection / Favorites / Profile。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import Collection, Favorite, Model, Photo, Tag, User
from ..database import SessionLocal, get_db
from ..i18n import t
from ..templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def _fav_keys(s: Session, user_id: int) -> dict[str, set[str]]:
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user_id)).all()
    out: dict[str, set[str]] = {"model": set(), "collection": set(), "photo": set()}
    for r in rows:
        if r.target_type in out:
            out[r.target_type].add(r.target_key)
    return out


def _collection_payload(s: Session, c: Collection) -> dict:
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "", "featured": c.featured,
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else t("未分类"),
        "cover": c.photos[0].filename if c.photos else None,
        "photos": [{"id": p.id, "file": p.filename, "w": p.width, "h": p.height}
                   for p in c.photos],
        "tags": [t.name for t in c.tags],
        "count": len(c.photos),
    }


def _model_payload(s: Session, m: Model, collections: list[Collection] | None = None) -> dict:
    works = collections if collections is not None else m.collections
    photo_count = sum(len(c.photos) for c in works)
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
        "since": m.since or "", "featured": m.featured,
        "tags": [t.name for t in m.tags],
        "count": len(works), "photoCount": photo_count,
    }


def _published_collections(s: Session) -> list[Collection]:
    return list(s.scalars(
        select(Collection).where(Collection.status == "published")
        .options()  # photos lazy selectin via relationship
        .order_by(desc(Collection.published_at), desc(Collection.id))).all())


# ---- Discovery --------------------------------------------------------------

@router.get("/")
async def discovery(request: Request, s: Session = Depends(get_db)):
    user = request.state.user
    cols = _published_collections(s)
    featured = [c for c in cols if c.featured][:4] or cols[:4]
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

    items = []
    for c in cols:
        p = _collection_payload(s, c)
        items.append(p)

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
    photo_items = []
    for c in cols:
        for i, p in enumerate(c.photos):
            key = f"{c.slug}:{i}"
            if key in favs["photo"]:
                photo_items.append({"key": key, "file": p.filename,
                                    "collection": c.slug, "title": c.title, "index": i})

    payload = {
        "models": model_items, "collections": collection_items, "photos": photo_items,
        "counts": {"model": len(model_items), "collection": len(collection_items),
                   "photo": len(photo_items)},
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
