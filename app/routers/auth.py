"""登录页。"""

from __future__ import annotations

import random

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..auth import COOKIE_NAME, create_session, destroy_session, verify_password
from ..database import SessionLocal
from ..db import Collection, Model, User
from ..i18n import t
from ..templating import templates

router = APIRouter()


@router.post("/language")
async def set_language(request: Request, lang: str = Form(""), next: str = Form("")):
    """切换界面语言(公开路由):设 cookie 一年;已登录用户同时写入个人设置。"""
    from ..i18n import LANGUAGES, normalize_lang
    code = normalize_lang(lang)
    if code not in LANGUAGES:
        code = ""
    if code:
        user = getattr(request.state, "user", None)
        if user is not None:
            s = SessionLocal()
            try:
                u = s.get(User, user.id)
                if u:
                    u.language = code
                    s.commit()
            finally:
                s.close()
    nxt = next or request.headers.get("referer") or "/"
    if not nxt.startswith("/") and not nxt.startswith(request.base_url.path):
        nxt = "/"
    resp = RedirectResponse(nxt, 303)
    if code:
        resp.set_cookie("pb_lang", code, max_age=365 * 24 * 3600,
                        httponly=False, samesite="lax", path="/")
    return resp


def _login_cover(s) -> dict:
    """随机挑几本已发布写真做登录页散落墙, 前端每 3s 轮换一套。

    只取标量列(合集 id/照片文件名), 绝不 joinedload 全库照片 ——
    那会把 2.5 万张 Photo 拖成 ORM 对象, 登录页 TTFB 2s+(实测)。
    首套随 HTML 直出(无 JS 也有完整画面), 其余套进 JSON 由脚本轮换。
    """
    import json

    from sqlalchemy import func

    from ..db import Photo
    from ..services.media import thumb_url, _cache_path
    rows = s.execute(
        select(Collection.id)
        .join(Photo, Photo.collection_id == Collection.id)
        .where(Collection.status == "published")
        .group_by(Collection.id)
        .having(func.count(Photo.id) >= 8)).all()
    cids = [r[0] for r in rows]
    if not cids:
        return {}
    random.shuffle(cids)
    sets: list[list[str]] = []
    for cid in cids[:5]:
        files = s.scalars(
            select(Photo.filename).where(Photo.collection_id == cid)
            .order_by(Photo.sort_order).limit(4)).all()
        if len(files) < 4:
            continue
        # 登录页图不回源: 只挑 s900 档已在磁盘缓存的图, 缺档的照片整本跳过
        # (没预热过的图会 404, onerror 隐藏后右侧照片就空了)。
        urls = [thumb_url(f.lstrip("/"), 900, short=True) for f in files
                if _cache_path(900, None, 78, f.lstrip("/"), short=True).is_file()]
        if len(urls) >= 4:
            sets.append(urls[:4])
    if len(sets) < 2:
        return {}
    return {
        "login_shots": sets[0],
        "login_sets_json": json.dumps(sets, ensure_ascii=False),
    }


def _login_ctx(s) -> dict:
    try:
        return _login_cover(s)
    except Exception:
        return {}


@router.get("/login")
async def login_page(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return RedirectResponse("/", 302)
    s = SessionLocal()
    try:
        ctx = _login_ctx(s)
    finally:
        s.close()
    return templates.TemplateResponse(request, "login.html", {
        "error": None, "username": "",
        "login_shots": [], "login_sets_json": "[]", **ctx})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    error = None
    s = SessionLocal()
    try:
        user = s.scalar(select(User).where(User.username == username.strip()))
        if user and verify_password(password, user.password_hash):
            sid = create_session(s, user.id)
            s.commit()
            s.close()
            resp = RedirectResponse("/", 303)
            resp.set_cookie(COOKIE_NAME, sid, httponly=True, samesite="lax",
                            max_age=14 * 24 * 3600, path="/")
            return resp
        error = t("用户名或密码不正确。")
    finally:
        s.close()
    s2 = SessionLocal()
    try:
        ctx = _login_ctx(s2)
    finally:
        s2.close()
    return templates.TemplateResponse(request, "login.html", {
        "error": error, "username": username,
        "login_shots": [], "login_sets_json": "[]", **ctx}, status_code=401)


@router.post("/logout")
@router.get("/logout")
async def logout(request: Request):
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        s = SessionLocal()
        try:
            destroy_session(s, sid)
            s.commit()
        finally:
            s.close()
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
