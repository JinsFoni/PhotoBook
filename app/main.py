"""FastAPI 入口 — 挂路由/静态/认证中间件/启动 worker。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .auth import COOKIE_NAME, current_user
from .config import settings
from .database import SessionLocal, init_db
from .db import Session as DbSession, User
from .routers import admin, auth, favorites_api, search_api, web
from .services.media import serve_media, serve_thumb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("photobook")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed()
    from .services import media
    from .services.harvest import worker
    if settings.harvest_enabled:
        worker.start_worker()
    media.preheat_all()  # daemon 线程预热缩略图,不阻塞启动
    log.info("PhotoBook started — http://%s:%s", settings.host, settings.port)
    yield
    from .services.harvest import worker
    worker.stop_worker()
    media._preheat_done.set()  # 通知预热线程提前退出


app = FastAPI(title="Photo Collection", lifespan=lifespan)


# ---- 认证墙 + 语言解析 --------------------------------------------------------
# 1) 静态/媒体/admin 轮询 API 早退(不查库)
# 2) 解析 session → user,同时确定语言(user.language → cookie → 站点默认)
#    必须在 call_next 之前 set_language,模板渲染才能读到;
# 3) 公共路径(含 /login)检查——登录页无 user,用 cookie → 站点默认;
# 4) 鉴权拦截。

PUBLIC_PATHS = ("/login", "/logout", "/healthz", "/language")


def _resolve_lang(s, request: Request, user) -> str:
    """语言优先级:user.language → cookie pb_lang → settings 表 site.language → zh-CN。"""
    from .i18n import DEFAULT_LANG, normalize_lang
    if user is not None and getattr(user, "language", ""):
        code = normalize_lang(user.language)
        if code:
            return code
    code = normalize_lang(request.cookies.get("pb_lang"))
    if code:
        return code
    try:
        from .db import Setting
        row = s.get(Setting, "site.language")
        if row and row.value:
            code = normalize_lang(row.value)
            if code:
                return code
    except Exception:
        pass
    return DEFAULT_LANG


@app.middleware("http")
async def auth_wall(request: Request, call_next):
    path = request.url.path
    if (path.startswith("/static") or path.startswith("/assets")
            or path.startswith("/media") or path.startswith("/t/")
            or path.startswith("/admin/api/")):
        return await call_next(request)

    # 解析用户与语言(同一连接)
    s = SessionLocal()
    try:
        user = None
        sid = request.cookies.get(COOKIE_NAME)
        if sid:
            sess = s.get(DbSession, sid)
            if sess:
                from datetime import datetime, timezone
                expires = sess.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    s.delete(sess)
                    s.commit()
                else:
                    user = s.get(User, sess.user_id)
        lang = _resolve_lang(s, request, user)
    finally:
        s.close()

    from .i18n import set_language
    set_language(lang)
    request.state.lang = lang

    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS):
        return await call_next(request)

    request.state.user = user
    if not user:
        if path.startswith("/api/"):
            return RedirectResponse("/login", 302)
        return RedirectResponse(f"/login?next={path}", 302)
    return await call_next(request)


# ---- 种子数据 -----------------------------------------------------------------------

def _seed() -> None:
    """首启创建 admin;无用户时补 demo 数据,便于立即看到 UI 效果。"""
    s = SessionLocal()
    try:
        users = s.scalars(select(User)).all()
        if not users:
            from .auth import hash_password
            s.add(User(username="admin", password_hash=hash_password("admin123"),
                       role="admin", avatar_seed="admin"))
            s.add(User(username="demo", password_hash=hash_password("demo123"),
                       role="user", avatar_seed="demo"))
            s.commit()
            log.warning("seeded users: admin/admin123, demo/demo123")
        if not s.scalars(select(User).where(User.role == "admin")).all():
            admin_user = s.scalars(select(User).where(User.username == "admin")).first()
            if admin_user:
                admin_user.role = "admin"
                s.commit()
        # 种子内容(仅 SEED_DEMO=true 时导入;空库时一次)
        if settings.seed_demo:
            _seed_content(s)
            _backfill_model_avatars(s)
        _backfill_photo_dims(s)
    finally:
        s.commit()
        s.close()

    if settings.seed_demo:
        # 演示图片(离线 NAS 自动退化为占位图)
        try:
            from .seed_images import ensure_demo_images
            ensure_demo_images(settings.media_dir)
        except Exception:
            log.exception("demo images failed")
        # 模特头像文件(旧库自愈;ensure_demo_images 内部也会调,两者均幂等)
        try:
            from .seed_images import ensure_demo_avatars
            ensure_demo_avatars(settings.media_dir)
        except Exception:
            log.exception("demo avatars failed")


def _backfill_photo_dims(s) -> None:
    """旧库照片 w/h 为空时,从实际图片文件读真实尺寸回填(幂等)。"""
    from .db import Photo as P
    rows = s.scalars(select(P).where(P.width.is_(None) | P.height.is_(None))).all()
    if not rows:
        return
    from PIL import Image
    fixed = 0
    for p in rows:
        f = settings.media_dir / p.filename
        if not f.is_file():
            continue
        try:
            with Image.open(f) as im:
                p.width, p.height = im.size
                fixed += 1
        except Exception:
            continue
    if fixed:
        s.commit()
        log.info("backfilled %d photo dimensions", fixed)


def _backfill_model_avatars(s) -> None:
    """早期种子版本未写模特头像,启动时自愈(幂等)。"""
    from .db import Model as M
    from .seed_data import MODELS
    changed = False
    for md in MODELS:
        if not md.get("avatar"):
            continue
        m = s.scalars(select(M).where(M.slug == md["slug"])).first()
        if not m:
            continue
        if not m.avatar_path:
            m.avatar_path = f"demo/avatars/{md['avatar']}.jpg"
            changed = True
        if md.get("hero") and not m.hero_path:
            m.hero_path = f"demo/avatars/{md['hero']}.jpg"
            changed = True
    if changed:
        s.commit()
        log.info("backfilled model avatars")


def _photo_dims(ph: dict, demo_dir: Path, fname: str) -> tuple[int, int]:
    """解析种子照片的宽高。优先 "ar": "3/2" 声明;否则读实际文件尺寸;再退化默认竖图。"""
    ar = ph.get("ar")
    if ar and "/" in ar:
        try:
            a, b = ar.split("/", 1)
            a, b = int(a), int(b)
            if a > 0 and b > 0:
                scale = 1200 / max(a, b)  # 归一到长边 1200,仅用于比例
                return (round(a * scale), round(b * scale))
        except ValueError:
            pass
    f = demo_dir / fname
    if f.is_file():
        try:
            from PIL import Image
            with Image.open(f) as im:
                return im.size
        except Exception:
            pass
    return (1200, 1600)


def _seed_content(s) -> None:
    from .db import Collection as C, Model as M, Photo as P, Tag as T
    from .db import CollectionTag, ModelTag, Setting

    if s.scalar(select(Setting).where(Setting.key == "seeded")):
        return
    from .seed_data import COLLECTIONS, MODELS
    tags = {}
    for name in sorted({t for c in COLLECTIONS for t in c["tags"]} |
                       {t for m in MODELS for t in m.get("tags", [])}):
        t = T(name=name, slug=name.lower().replace(" ", "-"))
        s.add(t)
        tags[name] = t
    s.flush()

    models_by_slug = {}
    for md in MODELS:
        m = M(slug=md["slug"], name=md["name"], stage_name=md.get("stage") or None,
              gender=md.get("gender"), age=md.get("age"), height=md.get("height"),
              measurements=md.get("measurements"), agency=md.get("agency") or None,
              bio=md.get("bio"), since=md.get("since"), featured=md.get("featured", False),
              avatar_path=f"demo/avatars/{md['avatar']}.jpg" if md.get("avatar") else None,
              hero_path=f"demo/avatars/{md['hero']}.jpg" if md.get("hero") else None,
              status="published")
        s.add(m)
        models_by_slug[md["slug"]] = (m, md.get("tags", []))
    s.flush()

    for slug, (m, tag_names) in models_by_slug.items():
        for name in tag_names:
            if name in tags:
                s.add(ModelTag(model_id=m.id, tag_id=tags[name].id))

    for cd in COLLECTIONS:
        c = C(slug=cd["slug"], title=cd["title"],
              model_id=models_by_slug[cd["model"]][0].id,
              published_at=cd["date"], featured=cd.get("featured", False),
              status="published")
        s.add(c)
        s.flush()
        for i, ph in enumerate(cd["photos"]):
            # 宽高比:优先用声明的 ar(如 "3/2"),否则从已下载文件读真实尺寸
            w, h = _photo_dims(ph, demo_dir=settings.media_dir / "demo" / cd["slug"],
                               fname=Path(ph["file"]).name)
            s.add(P(collection_id=c.id, filename=ph["file"], width=w,
                    height=h, sort_order=i))
        for name in cd.get("tags", []):
            if name in tags:
                s.add(CollectionTag(collection_id=c.id, tag_id=tags[name].id))
    s.add(Setting(key="seeded", value="1"))
    s.commit()
    log.info("seeded demo content: %d collections, %d models", len(COLLECTIONS), len(MODELS))
    # 演示图片(离线 NAS 自动退化为占位图;内部含头像下载)
    try:
        from .seed_images import ensure_demo_images
        ensure_demo_images(settings.media_dir)
    except Exception:
        log.exception("demo images failed")


# ---- boot 上下文:每个 SSR 页面注入用户/统计,chrome 用 --------------------------

def _boot_context(request: Request, s=None) -> dict:
    from .db import Collection as C, Model as M, Tag as T
    user = getattr(request.state, "user", None)
    boot = {
        "user": {"name": user.username if user else "", "role": user.role if user else ""},
        "path": request.url.path,
        "stats": {"collections": None, "models": None},
        "tags": [],
        "suggestions": ["Editorial", "Studio", "Outdoor", "Monochrome"],
    }
    try:
        if s is not None:
            boot["stats"]["collections"] = s.query(C).filter_by(status="published").count()
            boot["stats"]["models"] = s.query(M).filter_by(status="published").count()
            boot["tags"] = [t.name for t in s.scalars(select(T).order_by(T.name)).all()[:8]]
    except Exception:
        pass
    return boot


# ---- 路由 -----------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(web.router)
app.include_router(favorites_api.router)
app.include_router(search_api.router)
app.include_router(admin.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# 媒体与缩略图
@app.get("/media/{path:path}")
async def media(path: str, request: Request):
    return serve_media(path, request)


@app.get("/t/{spec:path}")
async def thumb(spec: str, request: Request):
    return serve_thumb(spec, request)


# 静态资源(design 系统的 css/js)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
