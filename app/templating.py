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
    """chrome 启动上下文:用户、路径、统计、标签、语言(每响应一次轻查询)。"""
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


templates.env.globals["media"] = media_url
templates.env.globals["media_orig"] = media_orig
from .services.avatar import avatar_data_uri as _avatar_uri  # noqa: E402
templates.env.globals["avatar"] = _avatar_uri
templates.env.globals["app_name"] = "Photo Collection"
templates.env.globals["boot_json"] = boot_json
templates.env.globals["t"] = i18n.translate
templates.env.globals["lang"] = i18n.get_language
templates.env.globals["LANGUAGES"] = i18n.LANGUAGES
