"""Jinja2 环境 — 模板放在 app/templates,复用设计系统的宏。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import i18n
from . import __version__

TEMPLATES_DIR = Path(__file__).parent / "templates"

# _blur_src 请求内缓存的"未计算"标记(None 是合法结果: 整条链挑不到图)
_SENTINEL = object()

# 静态资产版本号: 每次启动取文件修改时间, 避免浏览器缓存旧 JS/CSS
ASSET_VER = str(int(max((TEMPLATES_DIR.parent / "static" / f).stat().st_mtime
                        for f in ("app.css", "app.js"))))

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def media_url(rel: str | None, w: int = 900, h: int | None = None,
              short: bool = False) -> str:
    """模板里的缩略图 URL。rel 为空 → data URI 占位(1px 灰点)。

    全站只预热 s900/s2400 两档短边图(入库时生成,其余规格冷生成要回源
    云盘拉原图),模板一律用 short=True(或 media_short)。
    """
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    rel = rel.lstrip("/")
    from .services.media import thumb_url
    return thumb_url(rel, w, h, short=short)


def media_short(rel: str | None, w: int) -> str:
    """短边钳制档(/t/s<w>/) — 全站只预热 s900/s2400 两档,模板必须走这里
    或 media(rel, w) 的短边变体;钳宽/裁剪档缓存冷生成会触发云盘回源。"""
    if not rel:
        return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    from .services.media import thumb_url
    return thumb_url(rel.lstrip("/"), w, short=True)


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
        "version": __version__,
        "i18n": i18n.js_strings(lang),
        "stats": {"collections": None, "models": None},
        "tags": [],
        "suggestions": [],
        "tag_grid": [],
        "blur_src": _blur_src(request),
    }
    try:
        from sqlalchemy import func, select

        from .database import SessionLocal
        from .db import Collection, CollectionTag, Model, Tag
        s = SessionLocal()
        try:
            boot["stats"]["collections"] = s.scalar(
                select(func.count(Collection.id)).where(Collection.status == "published"))
            boot["stats"]["models"] = s.scalar(
                select(func.count(Model.id)).where(Model.status == "published"))
            boot["tags"] = [t.name for t in s.scalars(
                select(Tag).order_by(Tag.name).limit(8)).all()]
            boot["suggestions"] = boot["tags"]
            # 搜索空状态的标签网格: 一条 join 聚合(曾遍历全部合集连带照片,
            # 全库 ORM 加载 0.3s+/页 —— 见 db.py Collection.photos 注释)
            rows = s.execute(
                select(Tag.name, func.count(CollectionTag.collection_id))
                .join(CollectionTag, CollectionTag.tag_id == Tag.id)
                .join(Collection, Collection.id == CollectionTag.collection_id)
                .where(Collection.status == "published")
                .group_by(Tag.id)).all()
            boot["tag_grid"] = [{"name": n, "collections": cnt} for n, cnt in rows]
            # 数量多的在前(发现页底部与搜索页同一份), 同数按名称
            boot["tag_grid"].sort(key=lambda d: (-d["collections"], d["name"]))
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


def _first_photo_filename(s, collection_id: int) -> str | None:
    """合集第一张照片的文件名(标量子查询,不加载 Photo ORM)。"""
    from sqlalchemy import select

    from .db import Photo
    return s.scalar(select(Photo.filename).where(Photo.collection_id == collection_id)
                    .order_by(Photo.sort_order).limit(1))


def _blur_src(request: Request) -> str | None:
    """虚化主题的垫底图源:模特主页用头像, 写真详情用第一张图,
    其他页面用首页精选轮播的封面(整条查询链都挑不到则返回 None)。

    只取文件名字符串(标量查询), 绝不触碰 c.photos 关系 —— 那会把
    整个合集的照片拖成 ORM 对象。请求内缓存: base.html 同时渲染
    blur_src_json 和 boot_json(内部也调这里), 一页只算一次。
    """
    cached = getattr(request.state, "_blur_src", None)
    if cached is not _SENTINEL:
        return cached
    path = request.url.path
    rel: str | None = None
    try:
        from sqlalchemy import select

        from .database import SessionLocal
        from .db import Collection, Model

        s = SessionLocal()
        try:
            if path.startswith("/models/"):
                slug = path.split("/")[2] if len(path.split("/")) > 2 else ""
                m = s.scalar(select(Model).where(Model.slug == slug))
                if m:
                    rel = m.avatar_path
                    if not rel:
                        # 头像缺省 → 该模特最新发布合集的第一张(标量查询)
                        cid = s.scalar(
                            select(Collection.id).where(
                                Collection.model_id == m.id,
                                Collection.status == "published")
                            .order_by(Collection.published_at.desc()).limit(1))
                        if cid:
                            rel = _first_photo_filename(s, cid)
            elif path.startswith("/collections/"):
                slug = path.split("/")[2] if len(path.split("/")) > 2 else ""
                c = s.scalar(select(Collection).where(Collection.slug == slug))
                if c:
                    rel = _first_photo_filename(s, c.id)
            if not rel:
                c = s.scalar(
                    select(Collection).where(Collection.status == "published",
                                             Collection.featured == True)  # noqa: E712
                    .order_by(Collection.published_at.desc()))
                if not c:
                    c = s.scalar(
                        select(Collection).where(Collection.status == "published")
                        .order_by(Collection.published_at.desc()))
                if c:
                    rel = _first_photo_filename(s, c.id)
        finally:
            s.close()
        if rel:
            # 垫底图层重度模糊(46px), s900 短边档足够(全站统一低清档);
            # 2400px 预载太慢, 点击切虚化后要黑好几秒
            rel = "/t/s900/" + rel.lstrip("/") + ".webp"
    except Exception:
        rel = None
    request.state._blur_src = rel
    return rel


def blur_src_json(request: Request) -> str:
    """内联首帧脚本用的 JSON 字面量: {"src": .., "fp": ..} 或 null。
    服务端算图源指纹, 客户端据此判断是否与上一页同一张(免重淡入)。"""
    src = _blur_src(request)
    if not src:
        return "null"
    import json
    return json.dumps({"src": src, "fp": _blur_fingerprint(src)}, ensure_ascii=False)


def is_pwa(request: Request) -> bool:
    """PWA 注册开关, 环境变量 PWA_ENABLED 可关(Docker 部署不需要时)。"""
    from .config import settings
    return settings.pwa_enabled


templates.env.globals["media"] = media_url
templates.env.globals["media_short"] = media_short
templates.env.globals["media_orig"] = media_orig
from .services.avatar import avatar_data_uri as _avatar_uri  # noqa: E402
templates.env.globals["avatar"] = _avatar_uri
templates.env.globals["app_name"] = "Photo Collection"
templates.env.globals["boot_json"] = boot_json
templates.env.globals["asset_ver"] = ASSET_VER
templates.env.globals["blur_src_json"] = blur_src_json
templates.env.globals["is_pwa"] = is_pwa
templates.env.globals["t"] = i18n.translate
from .db import local_dt as _local_dt  # noqa: E402
templates.env.globals["local_time"] = lambda dt: (
    _local_dt(dt).strftime("%m-%d %H:%M") if dt else "")
templates.env.globals["lang"] = i18n.get_language
templates.env.globals["LANGUAGES"] = i18n.LANGUAGES
