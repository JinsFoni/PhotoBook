"""移动端 JSON API — Bearer token 认证(复用 sessions 表)+ 统一错误体。

认证模型:token = sessions 表主键(create_session 产出),客户端存 DataStore,
后续请求走 `Authorization: Bearer <token>`;auth_wall 中间件对 /api/mobile 早退,
鉴权完全由本模块的依赖完成。所有错误统一为 {"error": {"code", "message"}}。

媒体 URL 约定(客户端拿 rel 自拼):原图 /media/{rel},缩略图 /t/{w}x{h}/{rel}.webp。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import create_session, verify_password
from ..db import Collection, Favorite, Model, Photo, Session as DbSession, Tag, User
from ..database import get_db

router = APIRouter(prefix="/api/mobile")

THUMB_W_CARD = 600    # 列表卡片 /t/600x/
THUMB_W_HERO = 900    # 详情头图 /t/900x/


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

def _bearer_user(s: Session, authorization: str | None) -> User | None:
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
    return s.get(User, sess.user_id)


def mobile_user(s: Session = Depends(get_db),
                authorization: str | None = Header(default=None)) -> User | None:
    """可选鉴权:读接口匿名可用,收藏写接口用 require_mobile_user。"""
    return _bearer_user(s, authorization)


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

def _collection_cover(s: Session, c: Collection) -> str | None:
    """列表用封面文件名:优先 cover_photo_id,回退第一张(同 web.py)。"""
    if c.cover_photo_id:
        ph = s.get(Photo, c.cover_photo_id)
        if ph:
            return ph.filename
    ph = s.scalar(select(Photo).where(Photo.collection_id == c.id)
                  .order_by(Photo.sort_order).limit(1))
    return ph.filename if ph else None


def _collection_payload(s: Session, c: Collection) -> dict:
    cover = _collection_cover(s, c)
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "", "featured": c.featured,
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else "未分类",
        "cover": cover,
        "coverThumb": f"t/{THUMB_W_CARD}x/{cover}.webp" if cover else None,
        "photos": [{"idx": i, "file": p.filename, "w": p.width, "h": p.height}
                   for i, p in enumerate(c.photos)],
        "tags": [t.name for t in c.tags],
        "count": len(c.photos),
    }


def _collection_card(s: Session, c: Collection) -> dict:
    """列表瘦身条目(无 photos 数组)。"""
    cover = _collection_cover(s, c)
    return {
        "id": c.id, "slug": c.slug, "title": c.title,
        "date": c.published_at or "",
        "model_slug": c.model.slug if c.model else "",
        "model_name": c.model.name if c.model else "未分类",
        "cover": cover,
        "coverThumb": f"t/{THUMB_W_CARD}x/{cover}.webp" if cover else None,
        "count": len(c.photos),
        "tags": [t.name for t in c.tags],
    }


def _model_payload(s: Session, m: Model, collections: list[Collection] | None = None) -> dict:
    works = collections if collections is not None else m.collections
    photo_count = sum(len(c.photos) for c in works)
    latest = max((c.published_at or "" for c in works), default="")
    avatar = m.avatar_path
    if not avatar:  # 头像兜底:第一张合集封面(同 web.py)
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
    }


def _published_collections(s: Session) -> list[Collection]:
    return list(s.scalars(
        select(Collection).where(Collection.status == "published")
        .order_by(desc(Collection.published_at), desc(Collection.id))).all())


# ---- discover ----

@router.get("/discover")
async def mobile_discover(s: Session = Depends(get_db)):
    cols = _published_collections(s)
    featured = [c for c in cols if c.featured][:4] or cols[:4]
    latest = cols[:6]
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

    return {
        "featured": [_collection_payload(s, c) for c in featured],
        "latest": [_collection_payload(s, c) for c in latest],
        "models": [_model_payload(s, m, [c for c in cols if c.model_id == m.id])
                   for m in models],
        "tags": [{"name": t.name, "collections": tag_counts.get(t.name, {}).get("collections", 0),
                  "models": len(tag_counts.get(t.name, {}).get("models", set()))} for t in tags],
        "stats": {"collections": len(cols), "models": len(models)},
    }


# ---- collections 列表/详情 ----

@router.get("/collections")
async def mobile_collections(s: Session = Depends(get_db), tag: str = "",
                             page: int = Query(1, ge=1),
                             page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
                             sort: str = Query("latest", pattern="^(latest|oldest)$")):
    cols = _published_collections(s)
    if tag:
        cols = [c for c in cols if any(t.name == tag for t in c.tags)]
    if sort == "oldest":
        cols = list(reversed(cols))
    total = len(cols)
    start = (page - 1) * page_size
    items = cols[start:start + page_size]
    return {"items": [_collection_card(s, c) for c in items],
            "total": total, "page": page, "pageSize": page_size}


@router.get("/collections/{slug}")
async def mobile_collection_detail(slug: str, s: Session = Depends(get_db)):
    c = s.scalar(select(Collection).where(Collection.slug == slug,
                                          Collection.status == "published"))
    if not c:
        raise ApiError("not_found", "Collection not found", 404)
    payload = _collection_payload(s, c)
    payload["coverThumb"] = (f"t/{THUMB_W_HERO}x/{payload['cover']}.webp"
                             if payload["cover"] else None)
    payload["model"] = ({"slug": c.model.slug, "name": c.model.name}
                        if c.model else None)
    return payload


# ---- favorites(读允许匿名,写需登录;复用 favorites 表)-------------------

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
