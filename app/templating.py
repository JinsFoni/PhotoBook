"""Jinja2 环境 — 模板放在 app/templates,复用设计系统的宏。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import i18n

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def media_url(rel: str | None, w: int = 900, h: int | None = None) -> str:
    """模板里的缩略图 URL。rel 为空 → data URI 占位(1px 灰点)。"""
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    rel = rel.lstrip("/")
    from .services.media import thumb_url
    return thumb_url(rel, w, h)


def media_orig(rel: str | None) -> str:
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    return "/media/" + rel.lstrip("/")


def boot_json(request: Request) -> str:
    """chrome 启动上下文:用户、路径、统计、标签、语言、虚化背景图源(每响应一次轻查询)。"""
    from .services.avatar import avatar_data_uri

    user = getattr(request.state, "user", None)
    lang = getattr(request.state, "lang", None) or i18n.get_language()
    boot: dict = {
        "user": {"name": user.username if user else "", "role": user.role if user else "",
                 "avatar": avatar_data_uri(user.avatar_seed or user.username) if user else ""},
        "path": request.url.path,
        "lang": lang,
        "i18n": i18n.js_strings(lang),
        "stats": {"collections": None, "models": None},
        "tags": [],
        "suggestions": ["Editorial", "Studio", "Outdoor", "Monochrome"],
        "blur_src": _blur_src(request),
    }
    try:
        from sqlalchemy import func, select

        from .database import SessionLocal
        from .db import Collection, Model, Tag
        s = SessionLocal()
        try:
            boot["stats"]["collections"] = s.scalar(
                select(func.count(Collection.id)).where(Collection.status == "published"))
            boot["stats"]["models"] = s.scalar(
                select(func.count(Model.id)).where(Model.status == "published"))
            boot["tags"] = [t.name for t in s.scalars(
                select(Tag).order_by(Tag.name).limit(8)).all()]
        finally:
            s.close()
    except Exception:
        pass
    return json.dumps(boot, ensure_ascii=False)


def _blur_src(request: Request) -> str | None:
    """虚化主题的垫底图源:模特主页用头像, 写真详情用第一张图,
    其他页面用首页精选轮播的封面(整条查询链都挑不到则返回 None)。"""
    path = request.url.path
    try:
        from sqlalchemy import select

        from .database import SessionLocal
        from .db import Collection, Model

        rel: str | None = None
        s = SessionLocal()
        try:
            if path.startswith("/models/"):
                slug = path.split("/")[2] if len(path.split("/")) > 2 else ""
                m = s.scalar(select(Model).where(Model.slug == slug))
                if m:
                    rel = m.avatar_path
                    if not rel:
                        for c in m.collections:
                            if c.status == "published" and c.photos:
                                rel = c.photos[0].filename
                                break
            elif path.startswith("/collections/"):
                slug = path.split("/")[2] if len(path.split("/")) > 2 else ""
                c = s.scalar(select(Collection).where(Collection.slug == slug))
                if c and c.photos:
                    rel = c.photos[0].filename
            if not rel:
                c = s.scalar(
                    select(Collection).where(Collection.status == "published",
                                             Collection.featured == True)  # noqa: E712
                    .order_by(Collection.published_at.desc()))
                if not c:
                    c = s.scalar(
                        select(Collection).where(Collection.status == "published")
                        .order_by(Collection.published_at.desc()))
                if c and c.photos:
                    rel = c.photos[0].filename
        finally:
            s.close()
        if rel:
            from .config import settings as _settings
            return "/t/2400/" + rel.lstrip("/") + ".webp"
    except Exception:
        pass
    return None


templates.env.globals["media"] = media_url
templates.env.globals["media_orig"] = media_orig
from .services.avatar import avatar_data_uri as _avatar_uri  # noqa: E402
templates.env.globals["avatar"] = _avatar_uri
templates.env.globals["app_name"] = "Photo Collection"
templates.env.globals["boot_json"] = boot_json
templates.env.globals["t"] = i18n.translate
templates.env.globals["lang"] = i18n.get_language
templates.env.globals["LANGUAGES"] = i18n.LANGUAGES
