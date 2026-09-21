"""登录页。"""

from __future__ import annotations

import random

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..auth import COOKIE_NAME, create_session, destroy_session, verify_password
from ..database import SessionLocal
from ..db import Collection, User
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
    """随机挑一张已发布写真的照片做登录页背景。"""
    cols = s.scalars(
        select(Collection).where(Collection.status == "published")
        .options(joinedload(Collection.photos), joinedload(Collection.model))
        .order_by(Collection.id)).unique().all()
    if not cols:
        return {}
    c = random.choice(cols)
    if len(c.photos) < 3:
        return {}
    p = c.photos[2]
    return {
        "login_cover": p.filename,
        "login_title": c.title,
        "login_meta": t("{n} photos · {m}", n=len(c.photos),
                        m=c.model.name if c.model else t("未分类")),
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
    return templates.TemplateResponse(request, "login.html", {"error": None, "username": "", **ctx})


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
    return templates.TemplateResponse(request, "login.html",
                                      {"error": error, "username": username, **ctx}, status_code=401)


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
