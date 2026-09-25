"""Jinja2 环境 — 模板放在 app/templates,复用设计系统的宏。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import i18n

TEMPLATES_DIR = Path(__file__).parent / "templates"

# 静态资产版本号: 每次启动取文件修改时间, 避免浏览器缓存旧 JS/CSS
ASSET_VER = str(int(max((TEMPLATES_DIR.parent / "static" / f).stat().st_mtime
                        for f in ("app.css", "app.js"))))

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


def _blur_fingerprint(rel: str) -> str:
    """图源稳定指纹: 长路径哈希短码, 给内联脚本当 localStorage 键,
    判定"本页垫底图与上一页是否同一张"(跨页导航背景不重淡入)。"""
    import hashlib
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]


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
            # 垫底图层重度模糊(46px), 900px 档足够; 2400px 预载太慢,
            # 点击切虚化后要黑好几秒
            return "/t/900/" + rel.lstrip("/") + ".webp"
    except Exception:
        pass
    return None


def blur_src_json(request: Request) -> str:
    """内联首帧脚本用的 JSON 字面量: {"src": .., "fp": ..} 或 null。
    服务端算图源指纹, 客户端据此判断是否与上一页同一张(免重淡入)。"""
    src = _blur_src(request)
    if not src:
        return "null"
    import json
    return json.dumps({"src": src, "fp": _blur_fingerprint(src)}, ensure_ascii=False)


templates.env.globals["media"] = media_url
templates.env.globals["media_orig"] = media_orig
from .services.avatar import avatar_data_uri as _avatar_uri  # noqa: E402
templates.env.globals["avatar"] = _avatar_uri
templates.env.globals["app_name"] = "Photo Collection"
templates.env.globals["boot_json"] = boot_json
templates.env.globals["asset_ver"] = ASSET_VER
templates.env.globals["blur_src_json"] = blur_src_json
templates.env.globals["t"] = i18n.translate
templates.env.globals["lang"] = i18n.get_language
templates.env.globals["LANGUAGES"] = i18n.LANGUAGES
