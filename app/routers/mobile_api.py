"""移动端 JSON API — Bearer token 认证(复用 sessions 表)+ 统一错误体。

认证模型:token = sessions 表主键(create_session 产出),客户端存 DataStore,
后续请求走 `Authorization: Bearer <token>`;auth_wall 中间件对 /api/mobile 早退,
鉴权完全由本模块的依赖完成。所有错误统一为 {"error": {"code", "message"}}。

媒体 URL 约定(客户端拿 rel 自拼):原图 /media/{rel},缩略图 /t/{w}x{h}/{rel}(rel 带真实后缀,输出一律 WebP)。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from ..auth import create_session, verify_password
from ..config import settings
from ..db import Collection, Favorite, Model, Photo, Session as DbSession, Tag, User
from ..database import get_db

router = APIRouter(prefix="/api/mobile")

RENEW_HEADER = "X-Renewed-Token"    # 滑动续期:响应头携带新 token,客户端持久化替换

THUMB_SHORT_CARD = 900    # 列表卡片 /t/s900/(与 web 端全站统一低清档,共用 HTTP 缓存)
THUMB_SHORT_HERO = 900    # 详情头图 /t/s900/


# ---- ETag 条件请求 ------------------------------------------------------------

def _etag_response(payload, if_none_match: str | None) -> Response:
    """内容寻址 ETag:payload 的 sha1 即弱验证器,数据不变 → 304 空响应。

    客户端(OkHttp Cache)自动带 If-None-Match;304 省去客户端重新
    反序列化,更省蜂窝流量(响应体占这类接口流量的大头)。
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    etag = '"' + hashlib.sha1(body.encode()).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if if_none_match and etag in if_none_match:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


# ---- 统一错误体 --------------------------------------------------------------

class ApiError(Exception):
    """业务错误 — handler 统一转 {"error": {code, message}}。

    code 集合:invalid_credentials / unauthorized / not_found / validation / server。
    """

    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, exc.status)


async def mobile_validation_error_handler(request: Request, exc: RequestValidationError):
    """仅对 /api/mobile 收敛 422 形状;其余路径保持 FastAPI 默认。"""
    if not request.url.path.startswith("/api/mobile"):
        return await request_validation_exception_handler(request, exc)
    first = next(iter(exc.errors()), {})
    msg = first.get("msg") or "Validation error"
    field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    detail = f"{field}: {msg}" if field else msg
    return JSONResponse({"error": {"code": "validation", "message": detail}}, 422)


# ---- Bearer 鉴权 -------------------------------------------------------------

def _bearer_user(s: Session, authorization: str | None, request: Request | None = None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    sess = s.get(DbSession, token)
    if not sess:
        return None
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        s.delete(sess)
        s.commit()
        return None
    # 滑动续期:剩余寿命不足一半时签发新会话,旧会话作废,
    # 新 token 经响应头 X-Renewed-Token 下发(中间件落响应头)。
    half_life = timedelta(hours=settings.session_ttl_hours / 2)
    if request is not None and expires - datetime.now(timezone.utc) < half_life:
        new_token = create_session(s, sess.user_id)
        s.delete(sess)
        s.commit()
        request.state.renewed_token = new_token
    return s.get(User, sess.user_id)


def mobile_user(s: Session = Depends(get_db),
                authorization: str | None = Header(default=None),
                request: Request = None) -> User | None:
    """可选鉴权:读接口匿名可用,收藏写接口用 require_mobile_user。

    FastAPI 注入 request(用于滑动续期留 state);直接调用时可为 None。
    """
    return _bearer_user(s, authorization, request)


def require_mobile_user(user: User | None = Depends(mobile_user)) -> User:
    if not user:
        raise ApiError("unauthorized", "Not authenticated", 401)
    return user


# ---- 登录 --------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def mobile_login(body: LoginIn, s: Session = Depends(get_db)):
    user = s.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise ApiError("invalid_credentials", "用户名或密码错误", 401)
    token = create_session(s, user.id)
    s.commit()
    sess = s.get(DbSession, token)
    return {"token": token, "expires_at": sess.expires_at.isoformat()}


@router.get("/auth/me")
async def mobile_me(user: User = Depends(require_mobile_user)):
    return {"username": user.username, "role": user.role}


# ---- 内容 payload(与 web.py 同形状,加 coverThumb)------------------------

def _collection_cover(s: Session, c: Collection,
                      covers: dict[int, str] | None = None) -> str | None:
    """列表用封面文件名:优先 cover_photo_id,回退第一张(同 web.py)。
    covers 为 load_covers() 的批量结果, 命中时零查询。"""
    if covers is not None and c.id in covers:
        return covers[c.id]
    if c.cover_photo_id:
        ph = s.get(Photo, c.cover_photo_id)
        if ph:
            return ph.filename
    ph = s.scalar(select(Photo).where(Photo.collection_id == c.id)
                  .order_by(Photo.sort_order).limit(1))
    return ph.filename if ph else None


def _collections_by_model(cols: list[Collection]) -> dict[int | None, list[Collection]]:
    """一次分组,替代每个模特遍历全量合集的 O(models×collections) 写法。"""
    by_model: dict[int | None, list[Collection]] = {}
    for c in cols:
        by_model.setdefault(c.model_id, []).append(c)
    return by_model


def load_covers(s: Session, cols: list[Collection]) -> dict[int, str]:
    """批量取封面文件名 {collection_id: filename},一条查询(同 web.py)。
    无 cover_photo_id 的老数据不进字典,由 _collection_cover 回退第一张。"""
    ids = {c.cover_photo_id for c in cols if c.cover_photo_id}
    if not ids:
        return {}
    rows = s.execute(select(Photo.id, Photo.filename).where(Photo.id.in_(ids))).all()
    by_photo = dict(rows)
    return {c.id: by_photo[c.cover_photo_id] for c in cols
            if c.cover_photo_id in by_photo}


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
    """显式批量加载 photos 列表(photos 关系是 lazy=select,按需加载)。"""
    if not cols:
        return
    photos = s.scalars(
        select(Photo).where(Photo.collection_id.in_([c.id for c in cols]))
        .order_by(Photo.collection_id, Photo.sort_order)).all()
    by_col: dict[int, list[Photo]] = {}
    for p in photos:
        by_col.setdefault(p.collection_id, []).append(p)
    for c in cols:
        # 直接赋值会先懒加载旧集合(每本合集一条全量 SELECT),
        # set_committed_value 跳过旧值直接落新值。
        set_committed_value(c, "photos", by_col.get(c.id, []))


def _collection_payload(s: Session, c: Collection,
                        counts: dict[int, int] | None = None,
                        covers: dict[int, str] | None = None) -> dict:
    cover = _collection_cover(s, c, covers)
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "", "featured": c.featured,
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else "未分类",
        "cover": cover,
        "coverThumb": f"t/s{THUMB_SHORT_CARD}/{cover}" if cover else None,
        "photos": [{"idx": i, "file": p.filename, "w": p.width, "h": p.height}
                   for i, p in enumerate(c.photos)],
        "tags": [t.name for t in c.tags],
        "count": (counts or {}).get(c.id, len(c.photos)),
    }


def _collection_card(s: Session, c: Collection,
                     counts: dict[int, int] | None = None,
                     covers: dict[int, str] | None = None) -> dict:
    """列表瘦身条目(无 photos 数组)。"""
    cover = _collection_cover(s, c, covers)
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "",
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else "未分类",
        "cover": cover,
        "coverThumb": f"t/s{THUMB_SHORT_CARD}/{cover}" if cover else None,
        "count": (counts or {}).get(c.id, 0),
        "tags": [t.name for t in c.tags],
    }


def _model_payload(s: Session, m: Model, collections: list[Collection] | None = None,
                   counts: dict[int, int] | None = None,
                   covers: dict[int, str] | None = None) -> dict:
    works = collections if collections is not None else m.collections
    photo_count = sum((counts or {}).get(c.id, 0) for c in works)
    # 与 web 端 _model_payload 对齐: latest = 最新作品的入库日期(非源站发布日期)
    _latest = max((c.created_at for c in works if c.created_at), default=None)
    latest = _latest.date().isoformat() if _latest else ""
    avatar = m.avatar_path
    if not avatar:  # 头像兜底:封面照片(covers 命中时零查询)
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
        # 与 web.py 对齐: 卡片/详情都要 c.model, 不 eager load 会按合集逐条查模特
        .options(selectinload(Collection.model))
        .order_by(desc(Collection.published_at), desc(Collection.id))).all())


# ---- discover ----

@router.get("/discover")
async def mobile_discover(s: Session = Depends(get_db),
                          if_none_match: str | None = Header(default=None)):
    cols = _published_collections(s)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    counts = _photo_counts(s, cols)
    featured = [c for c in cols if c.featured][:4] or cols[:4]
    # 12 个:发现页轮播吃前 12(客户端 HeroCarousel take(12));网格只展示前 6。
    # 最新入库 = 入库时间(created_at)新→旧,同刻按 id 兜底,与写真 tab 的
    # added_latest 同语义;cols 自身是发布日期序,不能直接截断。
    latest = sorted(cols, key=lambda c: (c.created_at, c.id), reverse=True)[:12]
    models = s.scalars(select(Model).where(Model.status == "published")
                       .order_by(desc(Model.featured), Model.name)).all()
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()

    tag_counts: dict[str, dict] = {}
    for c in cols:
        for t in c.tags:
            d = tag_counts.setdefault(t.name, {"collections": 0, "models": set()})
            d["collections"] += 1
            if c.model:
                d["models"].add(c.model.slug)

    # 轮播/网格要照片数组: 只有 featured + latest 两个小集合真要
    load_photos(s, list(dict.fromkeys(featured + latest)))

    return _etag_response({
        "featured": [_collection_payload(s, c, counts, covers) for c in featured],
        "latest": [_collection_payload(s, c, counts, covers) for c in latest],
        "models": [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                   for m in models],
        "tags": [{"name": t.name, "collections": tag_counts.get(t.name, {}).get("collections", 0),
                  "models": len(tag_counts.get(t.name, {}).get("models", set()))} for t in tags],
        "stats": {"collections": len(cols), "models": len(models)},
    }, if_none_match)


# ---- collections 列表/详情 ----

@router.get("/collections")
async def mobile_collections(s: Session = Depends(get_db), tag: str = "",
                             page: int = Query(1, ge=1),
                             page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
                             sort: str = Query("latest",
                                               pattern="^(latest|oldest|added_latest|added_oldest)$")):
    cols = _published_collections(s)
    if tag:
        cols = [c for c in cols if any(t.name == tag for t in c.tags)]
    if sort == "oldest":
        cols = list(reversed(cols))
    elif sort == "added_latest":
        # 入库日期:created_at 新→旧,同刻按 id 稳定
        cols = sorted(cols, key=lambda c: (c.created_at, c.id), reverse=True)
    elif sort == "added_oldest":
        cols = sorted(cols, key=lambda c: (c.created_at, c.id))
    total = len(cols)
    start = (page - 1) * page_size
    items = cols[start:start + page_size]
    page_counts = _photo_counts(s, items)
    covers = load_covers(s, items)
    return {"items": [_collection_card(s, c, page_counts, covers) for c in items],
            "total": total, "page": page, "pageSize": page_size}


@router.get("/collections/{slug}")
async def mobile_collection_detail(slug: str, s: Session = Depends(get_db)):
    c = s.scalar(select(Collection).where(Collection.slug == slug,
                                          Collection.status == "published")
                 .options(selectinload(Collection.model)))
    if not c:
        raise ApiError("not_found", "Collection not found", 404)
    load_photos(s, [c])
    payload = _collection_payload(s, c, _photo_counts(s, [c]),
                                  load_covers(s, [c]))
    payload["coverThumb"] = (f"t/s{THUMB_SHORT_HERO}/{payload['cover']}"
                             if payload["cover"] else None)
    payload["model"] = ({"slug": c.model.slug, "name": c.model.name}
                        if c.model else None)
    return payload


# ---- models(列表/详情)-----------------------------------------------------

@router.get("/models")
async def mobile_models(s: Session = Depends(get_db),
                        featured: str = Query("", pattern="^(|1)$"),
                        sort: str = Query("latest", pattern="^(latest|oldest)$"),
                        if_none_match: str | None = Header(default=None)):
    # 精选永远置顶(与时间排序解耦),组内按创建时间 latest 新→旧 / oldest 旧→新
    created = Model.created_at.desc() if sort == "latest" else Model.created_at.asc()
    mid = Model.id.desc() if sort == "latest" else Model.id.asc()
    models = s.scalars(select(Model).where(Model.status == "published")
                       .order_by(desc(Model.featured), created, mid)).all()
    if featured:
        models = [m for m in models if m.featured]
    cols = _published_collections(s)
    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    return _etag_response(
        {"items": [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                   for m in models], "total": len(models)},
        if_none_match)


@router.get("/models/{slug}")
async def mobile_model_detail(slug: str, s: Session = Depends(get_db)):
    m = s.scalar(select(Model).where(Model.slug == slug,
                                     Model.status == "published"))
    if not m:
        raise ApiError("not_found", "Model not found", 404)
    works = [c for c in _published_collections(s) if c.model_id == m.id]
    work_counts = _photo_counts(s, works)
    covers = load_covers(s, works)
    payload = _model_payload(s, m, works, work_counts, covers)
    payload["collections"] = [_collection_card(s, c, work_counts, covers) for c in works]
    return payload


# ---- search(复用 search_api 的匹配逻辑;返回 rel,客户端自拼 URL)----------

@router.get("/search")
async def mobile_search(q: str = Query(""), s: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return {"q": "", "models": [], "collections": [], "tags": []}
    like = q.lower()

    models = s.scalars(select(Model).where(Model.status == "published")
                       .order_by(Model.name)).all()
    hit_models = [m for m in models
                  if like in (m.name + " " + (m.stage_name or "") + " " +
                              " ".join(t.name for t in m.tags) + " " +
                              (m.agency or "")).lower()][:8]

    cols = _published_collections(s)
    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    hit_cols = [c for c in cols
                if like in (c.title + " " +
                            (c.model.name if c.model else "") + " " +
                            " ".join(t.name for t in c.tags)).lower()][:10]

    tags = s.scalars(select(Tag).order_by(Tag.name)).all()
    hit_tags = [t.name for t in tags if like in t.name.lower()][:8]

    def _model_card(m: Model) -> dict:
        avatar = m.avatar_path
        if not avatar:  # 头像兜底:封面照片(不拖全 photos)
            for c in m.collections:
                if c.id in covers:
                    avatar = covers[c.id]
                    break
                if c.cover_photo_id:
                    ph = s.get(Photo, c.cover_photo_id)
                    if ph:
                        avatar = ph.filename
                        break
        return {"slug": m.slug, "name": m.name, "stage": m.stage_name or "",
                "avatar": avatar, "thumb": (f"t/s{THUMB_SHORT_CARD}/{avatar}" if avatar else None),
                "count": len(m.collections), "tags": [t.name for t in m.tags]}

    return {
        "q": q,
        "models": [_model_card(m) for m in hit_models],
        "collections": [_collection_card(s, c, counts, covers) for c in hit_cols],
        "tags": hit_tags,
    }


# ---- favorites(读允许匿名,写需登录;复用 favorites 表)-------------------

@router.get("/favorites/resolve")
async def mobile_favorites_resolve(s: Session = Depends(get_db),
                                   user: User = Depends(require_mobile_user),
                                   if_none_match: str | None = Header(default=None)):
    """收藏三段解析为实体(S7 直接渲染,免客户端逐段反查):
    model 段 = _model_payload;collection 段 = _collection_card;
    photo 段 = key slug:idx 反查文件名 + 缩略 rel + 所在合集标题。"""
    out = {"models": [], "collections": [], "photos": []}
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user.id)).all()
    favs = {"model": set(), "collection": set(), "photo": set()}
    for r in rows:
        if r.target_type in favs:
            favs[r.target_type].add(r.target_key)
    if not any(favs.values()):
        return _etag_response(out, if_none_match)

    cols = _published_collections(s)
    counts = _photo_counts(s, cols)
    covers = load_covers(s, cols)
    by_model = _collections_by_model(cols)
    if favs["model"]:
        models = s.scalars(select(Model).where(Model.status == "published")
                           .order_by(desc(Model.featured), Model.name)).all()
        out["models"] = [_model_payload(s, m, by_model.get(m.id, []), counts, covers)
                         for m in models if m.slug in favs["model"]]
    if favs["collection"]:
        out["collections"] = [_collection_card(s, c, counts, covers) for c in cols
                              if c.slug in favs["collection"]]
    if (favs["photo"]):
        photos = []
        # 只有含收藏照片的合集才需要照片数组, 显式加载这一小撮
        fav_col_slugs = {k.split(":")[0] for k in favs["photo"]}
        photo_cols = [c for c in cols if c.slug in fav_col_slugs]
        load_photos(s, photo_cols)
        for c in photo_cols:
            for i, p in enumerate(c.photos):
                if f"{c.slug}:{i}" in favs["photo"]:
                    photos.append({
                        "key": f"{c.slug}:{i}", "slug": c.slug, "idx": i,
                        "file": p.filename, "title": c.title,
                        "thumb": f"t/s{THUMB_SHORT_CARD}/{p.filename}",
                        "w": p.width, "h": p.height,
                    })
        out["photos"] = photos
    return _etag_response(out, if_none_match)


@router.get("/favorites")
async def mobile_favorites(s: Session = Depends(get_db),
                           user: User | None = Depends(mobile_user)):
    out = {"model": [], "collection": [], "photo": []}
    if not user:
        return out
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user.id)).all()
    for r in rows:
        if r.target_type in out:
            out[r.target_type].append(r.target_key)
    return out


class FavoriteIn(BaseModel):
    type: str            # model | collection | photo
    key: str             # slug 或 collection:idx
    added: bool


@router.post("/favorites")
async def mobile_toggle_favorite(body: FavoriteIn, s: Session = Depends(get_db),
                                 user: User = Depends(require_mobile_user)):
    if body.type not in ("model", "collection", "photo"):
        raise ApiError("validation", "bad type", 400)
    row = s.scalar(select(Favorite).where(
        Favorite.user_id == user.id, Favorite.target_type == body.type,
        Favorite.target_key == body.key))
    if body.added:
        if not row:
            s.add(Favorite(user_id=user.id, target_type=body.type, target_key=body.key))
    elif row:
        s.delete(row)
    s.commit()
    return {"ok": True, "type": body.type, "key": body.key, "added": body.added}
