"""用户端页面 — Discovery / Models / Collection / Favorites / Profile。"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from ..auth import require_login
from ..db import Collection, Favorite, Model, Photo, Tag, User
from ..database import SessionLocal, get_db
from ..i18n import t
from ..templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def _photo_counts(s: Session, cols: list[Collection]) -> dict[int, int]:
    """一批合集的照片数,一条 GROUP BY(替代 len(c.photos) 的全库 ORM 加载)。"""
    if not cols:
        return {}
    rows = s.execute(
        select(Photo.collection_id, func.count(Photo.id))
        .where(Photo.collection_id.in_([c.id for c in cols]))
        .group_by(Photo.collection_id)).all()
    return dict(rows)


def load_photos(s: Session, cols: list[Collection]) -> None:
    """显式批量加载 photos 列表(详情/收藏/轮播等真要照片数组的页面)。"""
    if not cols:
        return
    ids = [c.id for c in cols]
    photos = s.scalars(
        select(Photo).where(Photo.collection_id.in_(ids))
        .order_by(Photo.collection_id, Photo.sort_order)).all()
    by_col: dict[int, list[Photo]] = {}
    for p in photos:
        by_col.setdefault(p.collection_id, []).append(p)
    for c in cols:
        # 直接赋值会先懒加载旧集合(每本合集一条全量 SELECT, 发现页实测
        # 16 条额外查询), set_committed_value 跳过旧值直接落新值。
        set_committed_value(c, "photos", by_col.get(c.id, []))


def _collections_by_model(cols: list[Collection]) -> dict[int | None, list[Collection]]:
    """一次分组,替代每个模特遍历全量合集的 O(models×collections) 写法。"""
    by_model: dict[int | None, list[Collection]] = {}
    for c in cols:
        by_model.setdefault(c.model_id, []).append(c)
    return by_model


def load_covers(s: Session, cols: list[Collection]) -> dict[int, str]:
    """批量取封面文件名 {collection_id: filename},一条查询。

    卡片与模特头像兜底都读封面;逐条 s.get(Photo) 在 NAS 的 482 本合集上
    要 90ms+。无 cover_photo_id 的老数据不进字典,由 _collection_cover
    回退第一张(正常库应为 0 条)。
    """
    ids = {c.cover_photo_id for c in cols if c.cover_photo_id}
    if not ids:
        return {}
    rows = s.execute(select(Photo.id, Photo.filename).where(Photo.id.in_(ids))).all()
    by_photo = dict(rows)
    return {c.id: by_photo[c.cover_photo_id] for c in cols
            if c.cover_photo_id in by_photo}


def _fav_keys(s: Session, user_id: int) -> dict[str, set[str]]:
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user_id)).all()
    out: dict[str, set[str]] = {"model": set(), "collection": set(), "photo": set()}
    for r in rows:
        if r.target_type in out:
            out[r.target_type].add(r.target_key)
    return out


def _collection_cover(s: Session, c: Collection,
                      covers: dict[int, str] | None = None) -> str | None:
    """列表用封面文件名: 优先 cover_photo_id(避免为拿第一张图拖全 photos),
    兼容老数据/手动建集合回退第一张。covers 为 load_covers() 的批量结果。"""
    if covers is not None and c.id in covers:
        return covers[c.id]
    if c.cover_photo_id:
        ph = s.get(Photo, c.cover_photo_id)
        if ph:
            return ph.filename
    ph = s.scalar(select(Photo).where(Photo.collection_id == c.id)
                  .order_by(Photo.sort_order).limit(1))
    return ph.filename if ph else None


def _collection_card(s: Session, c: Collection, counts: dict[int, int] | None = None,
                     covers: dict[int, str] | None = None) -> dict:
    """列表/网格卡片的瘦身条目: 不带 photos 数组, 体积约为完整 payload 的 1/30。
    用在哪: /collections 虚拟化数据池(万级条目也轻)。
    counts: 预聚合的照片数(调用方 _photo_counts 一次算好); 缺了按封面兜底。
    covers: 调用方 load_covers() 一次算好的封面文件名, 避免逐条查照片表。"""
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "",
        # 入库日期(YYYY-MM-DD,客户端「最新/最早入库」排序用)
        "created": c.created_at.date().isoformat() if c.created_at else "",
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else t("未分类"),
        "cover": _collection_cover(s, c, covers),
        "count": (counts or {}).get(c.id, 0),
        "tags": [t.name for t in c.tags],
    }


def _collection_payload(s: Session, c: Collection,
                        counts: dict[int, int] | None = None,
                        covers: dict[int, str] | None = None) -> dict:
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "", "featured": c.featured,
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else t("未分类"),
        "cover": _collection_cover(s, c, covers),
        "photos": [{"id": p.id, "file": p.filename, "w": p.width, "h": p.height}
                   for p in c.photos],
        "tags": [t.name for t in c.tags],
        "count": (counts or {}).get(c.id, len(c.photos)),
    }


def _model_payload(s: Session, m: Model, collections: list[Collection] | None = None,
                   counts: dict[int, int] | None = None,
                   covers: dict[int, str] | None = None) -> dict:
    works = collections if collections is not None else m.collections
    photo_count = sum((counts or {}).get(c.id, 0) for c in works)
    # 模特页「排序:最新」= 最新作品的入库日期(与写真列表「最新入库」同语义),
    # 不是源站发布日期 —— 刚入库的老作品模特也应排前
    _latest = max((c.created_at for c in works if c.created_at), default=None)
    latest = _latest.date().isoformat() if _latest else ""
    # 头像兜底:没设头像时用第一张合集封面(covers 命中时零查询)
    avatar = m.avatar_path
    if not avatar:
        for c in works:
            if covers is not None and c.id in covers:
                avatar = covers[c.id]
                break
            if c.cover_photo_id:
                ph = s.get(Photo, c.cover_photo_id)
                if ph:
                    avatar = ph.filename
                    break
    return {
        "id": m.id, "slug": m.slug, "name": m.name, "stage": m.stage_name or "",
        "avatar": avatar, "hero": m.hero_path or avatar,
        "gender": m.gender or "", "age": m.age, "height": m.height,
        "measurements": m.measurements, "agency": m.agency or "", "bio": m.bio or "",
        "since": m.since or "", "featured": m.featured, "latest": latest,
        "tags": [t.name for t in m.tags],
        "count": len(works), "photoCount": photo_count,
    }


def _published_collections(s: Session) -> list[Collection]:
    return list(s.scalars(
        select(Collection).where(Collection.status == "published")
        .options(selectinload(Collection.model))
        .order_by(desc(Collection.published_at), desc(Collection.id))).all())


def _works_newest_first(works: list[Collection]) -> list[Collection]:
    """模特页作品序 = 最新入库(created_at 新→旧, 同刻按 id 兜底)。

    与写真列表「最新入库」、首页轮播、移动端写真 tab 同一语义, **不是**源站
    发布日期: 老站转载的旧作今天刚入库, 按 published_at 会被排到很后面。
    虚化垫底图(templating._blur_src)按同一把尺子挑合集, 所以模特页背景恒等于
    本网格第一张 —— 两处排序基准必须一致, 改一处就得改另一处。
    """
    # created_at 理论上不会为空(default=utcnow), 老数据兜底排到最后
    return sorted(works, key=lambda c: (c.created_at or datetime.min, c.id),
                  reverse=True)


# ---- Discovery --------------------------------------------------------------

@router.get("/")
async def discovery(request: Request, s: Session = Depends(get_db)):
    user = request.state.user
    cols = _published_collections(s)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    counts = _photo_counts(s, cols)
    # 轮播图顺序 = 最新入库(created_at 新→旧, 同刻按 id 兜底);cols 自身是
    # 发布日期序, 不能直接截断。勾了 featured 的优先, 没有则全库兜底。
    by_added = sorted(cols, key=lambda c: (c.created_at, c.id), reverse=True)
    featured_set = {c.id for c in cols if c.featured}
    featured = [c for c in by_added if c.id in featured_set][:16] or by_added[:16]
    latest = by_added[:6]  # 「Latest Collections」同为最新入库序
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

    # 轮播需要照片数组: 只有 featured(≤16) + latest(≤6) 两个小集合真要照片
    load_photos(s, [c for c in dict.fromkeys(featured + latest)])
    payload = {
        "featured": [_collection_payload(s, c, counts, covers) for c in featured],
        "latest": [_collection_payload(s, c, counts, covers) for c in latest],
        "models": [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                   for m in models],
        "tags": sorted(
            [{"name": t.name, "collections": tag_counts.get(t.name, {}).get("collections", 0),
              "models": len(tag_counts.get(t.name, {}).get("models", set()))} for t in tags],
            key=lambda d: (-d["collections"], d["name"])),
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

    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    items = [_collection_card(s, c, counts, covers) for c in cols]

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
    c = s.scalar(select(Collection).where(Collection.slug == slug)
                 .options(selectinload(Collection.model)))
    if not c or c.status != "published":
        text = t("We couldn't find that {w}. The link may be out of date.", w=t("写真"))
        return templates.TemplateResponse(request, "notfound.html",
                                          {"user": user, "page": "collections", "text": text},
                                          status_code=404)
    load_photos(s, [c])
    counts = _photo_counts(s, [c])
    same_model = [x for x in (s.scalars(
        select(Collection).where(Collection.model_id == c.model_id,
                                 Collection.status == "published")
        .options(selectinload(Collection.model))).all()
        if c.model_id else []) if x.slug != c.slug]
    others = [x for x in _published_collections(s) if x.slug != c.slug and x.model_id != c.model_id][:5]
    next_cols = (same_model + others)[:5]
    next_counts = _photo_counts(s, next_cols)
    covers = load_covers(s, [c, *next_cols])
    payload = _collection_payload(s, c, counts, covers)
    payload["next"] = [_collection_card(s, x, next_counts, covers) for x in next_cols]
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
    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    agencies = sorted({m.agency for m in models if m.agency})
    tag_set = sorted({t.name for m in models for t in m.tags})

    payload = {
        "models": [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                   for m in models],
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
    # 写真集按最新入库在前(与列表页「最新入库」、虚化背景同序)
    works = _works_newest_first([c for c in m.collections if c.status == "published"])
    work_counts = _photo_counts(s, works)
    covers = load_covers(s, works)
    # 显式传 works + counts: 缺省时 photoCount 只能逐个兜底 0
    payload = _model_payload(s, m, works, work_counts, covers)
    payload["works"] = [_collection_card(s, c, work_counts, covers) for c in works]
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
    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    model_items = [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                   for m in models if m.slug in favs["model"]]
    collection_items = [_collection_card(s, c, counts, covers)
                        for c in cols if c.slug in favs["collection"]]

    # 收藏的照片:target_key = "<collection_slug>:<idx>"
    # w/h 必带: justified 照片墙(layoutPhotoWall)按宽高比分行,图片未加载时
    # 只能读模板内联 aspect-ratio,缺了会全部按 2/3 兜底 → 横图卡留洞。
    # gi 是本页照片列表的全局下标, 灯箱按它直接定位当前张。
    # 只有含收藏照片的合集才需要照片数组, 显式加载这一小撮
    fav_col_slugs = {k.split(":")[0] for k in favs["photo"]}
    photo_cols = [c for c in cols if c.slug in fav_col_slugs]
    load_photos(s, photo_cols)
    photo_items = []
    for c in photo_cols:
        for i, p in enumerate(c.photos):
            key = f"{c.slug}:{i}"
            if key in favs["photo"]:
                photo_items.append({"key": key, "file": p.filename, "id": p.id,
                                    "w": p.width, "h": p.height, "gi": len(photo_items),
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
    counts = _photo_counts(s, cols)
    recent_cols = [c for c in cols if c.slug in favs["collection"]][:3]
    covers = load_covers(s, recent_cols)
    recent = [_collection_card(s, c, counts, covers) for c in recent_cols]
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
