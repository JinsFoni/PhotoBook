"""管理端 — Dashboard / CRUD / 采集任务 / 设置。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..config import settings
from ..db import (Collection, HarvestHistory, HarvestJob, Model, Photo, Session as DbSession,
                  Setting, Tag, User)
from ..database import get_db
from ..i18n import t
from ..templating import templates
from ..services import settings_store
from ..services.harvest import worker as harvest_worker

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _conf_value(s: Session, key: str, dflt: str) -> str:
    v = settings_store.get_setting(s, key)
    return v if v is not None and v != "" else dflt


# ---- Dashboard ----------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, s: Session = Depends(get_db)):
    stats = {
        "models": s.scalar(select(func.count(Model.id))) or 0,
        "collections": s.scalar(select(func.count(Collection.id))) or 0,
        "photos": s.scalar(select(func.count(Photo.id))) or 0,
        "users": s.scalar(select(func.count(User.id))) or 0,
        "tags": s.scalar(select(func.count(Tag.id))) or 0,
        "jobs_active": s.scalar(select(func.count(HarvestJob.id)).where(
            HarvestJob.status.in_(["queued", "parsing", "downloading", "extracting"]))) or 0,
        "jobs_done": s.scalar(select(func.count(HarvestJob.id)).where(
            HarvestJob.status.in_(["done", "exists"]))) or 0,
        "jobs_failed": s.scalar(select(func.count(HarvestJob.id)).where(
            HarvestJob.status == "failed")) or 0,
    }
    recent = s.scalars(select(HarvestJob).order_by(desc(HarvestJob.id)).limit(8)).all()
    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "page": "admin", "stats": stats, "recent_jobs": recent,
        "worker_running": harvest_worker.worker_running(),
    })


# ---- Models CRUD ----------------------------------------------------------------

@router.get("/models")
async def admin_models(request: Request, s: Session = Depends(get_db)):
    models = s.scalars(select(Model).order_by(Model.name)).all()
    counts = dict(s.execute(
        select(Collection.model_id, func.count(Collection.id))
        .group_by(Collection.model_id)).all())
    return templates.TemplateResponse(request, "admin/models.html", {
        "page": "admin", "models": models,
        "col_counts": counts, "error": request.query_params.get("error", ""),
    })


@router.get("/models/new")
async def admin_model_new(request: Request):
    return templates.TemplateResponse(request, "admin/model_form.html", {
        "page": "admin", "m": None, "action": "/admin/models/new", "error": "",
    })


@router.post("/models/new")
async def admin_model_create(request: Request, s: Session = Depends(get_db),
                             name: str = Form(...), slug: str = Form(""),
                             stage_name: str = Form(""), gender: str = Form(""),
                             age: str = Form(""), height: str = Form(""),
                             measurements: str = Form(""), agency: str = Form(""),
                             bio: str = Form(""), featured: str = Form("")):
    slug = (slug or name).strip().lower().replace(" ", "-")
    if s.scalar(select(Model).where(Model.slug == slug)):
        return templates.TemplateResponse(request, "admin/model_form.html", {
            "page": "admin", "m": None, "action": "/admin/models/new",
            "error": t("slug 已存在: {slug}", slug=slug),
        }, status_code=400)
    m = Model(name=name.strip(), slug=slug, stage_name=stage_name or None,
              gender=gender or None, age=int(age) if age.isdigit() else None,
              height=height or None, measurements=measurements or None,
              agency=agency or None, bio=bio or None, featured=bool(featured),
              since=datetime.now().strftime("%Y"))
    s.add(m)
    s.commit()
    return RedirectResponse("/admin/models", 303)


@router.get("/models/{model_id}/edit")
async def admin_model_edit(request: Request, model_id: int, s: Session = Depends(get_db)):
    m = s.get(Model, model_id)
    if not m:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "admin/model_form.html", {
        "page": "admin", "m": m, "action": f"/admin/models/{model_id}/edit", "error": "",
    })


@router.post("/models/{model_id}/edit")
async def admin_model_update(request: Request, model_id: int, s: Session = Depends(get_db),
                             name: str = Form(...), slug: str = Form(""),
                             stage_name: str = Form(""), gender: str = Form(""),
                             age: str = Form(""), height: str = Form(""),
                             measurements: str = Form(""), agency: str = Form(""),
                             bio: str = Form(""), featured: str = Form("")):
    m = s.get(Model, model_id)
    if not m:
        raise HTTPException(404)
    m.name = name.strip()
    if slug:
        m.slug = slug.strip().lower().replace(" ", "-")
    m.stage_name = stage_name or None
    m.gender = gender or None
    m.age = int(age) if age.isdigit() else None
    m.height = height or None
    m.measurements = measurements or None
    m.agency = agency or None
    m.bio = bio or None
    m.featured = bool(featured)
    s.commit()
    return RedirectResponse("/admin/models", 303)


@router.post("/models/{model_id}/delete")
async def admin_model_delete(model_id: int, s: Session = Depends(get_db)):
    m = s.get(Model, model_id)
    if m:
        s.delete(m)
        s.commit()
    return RedirectResponse("/admin/models", 303)


# ---- Collections CRUD ------------------------------------------------------------

@router.get("/collections")
async def admin_collections(request: Request, s: Session = Depends(get_db)):
    cols = s.scalars(select(Collection).order_by(desc(Collection.id))).all()
    models = s.scalars(select(Model).order_by(Model.name)).all()
    return templates.TemplateResponse(request, "admin/collections.html", {
        "page": "admin", "collections": cols, "models": models,
        "error": request.query_params.get("error", ""),
    })


@router.get("/collections/new")
async def admin_collection_new(request: Request, s: Session = Depends(get_db)):
    models = s.scalars(select(Model).order_by(Model.name)).all()
    return templates.TemplateResponse(request, "admin/collection_form.html", {
        "page": "admin", "c": None, "models": models,
        "action": "/admin/collections/new", "error": "",
    })


@router.post("/collections/new")
async def admin_collection_create(request: Request, s: Session = Depends(get_db),
                                  title: str = Form(...), slug: str = Form(""),
                                  model_id: str = Form(""), published_at: str = Form(""),
                                  status: str = Form("published"), featured: str = Form("")):
    slug = (slug or title).strip().lower().replace(" ", "-")
    if s.scalar(select(Collection).where(Collection.slug == slug)):
        return RedirectResponse("/admin/collections/new?error=slug-exists", 303)
    c = Collection(title=title.strip(), slug=slug,
                   model_id=int(model_id) if model_id.isdigit() else None,
                   published_at=published_at or datetime.now().strftime("%Y.%m.%d"),
                   status=status, featured=bool(featured))
    s.add(c)
    s.commit()
    return RedirectResponse(f"/admin/collections/{c.id}/edit", 303)


@router.get("/collections/{col_id}/edit")
async def admin_collection_edit(request: Request, col_id: int, s: Session = Depends(get_db)):
    c = s.get(Collection, col_id)
    if not c:
        raise HTTPException(404)
    models = s.scalars(select(Model).order_by(Model.name)).all()
    return templates.TemplateResponse(request, "admin/collection_form.html", {
        "page": "admin", "c": c, "models": models,
        "action": f"/admin/collections/{col_id}/edit", "error": "",
    })


@router.post("/collections/{col_id}/edit")
async def admin_collection_update(request: Request, col_id: int, s: Session = Depends(get_db),
                                  title: str = Form(...), slug: str = Form(""),
                                  model_id: str = Form(""), published_at: str = Form(""),
                                  status: str = Form("published"), featured: str = Form("")):
    c = s.get(Collection, col_id)
    if not c:
        raise HTTPException(404)
    c.title = title.strip()
    if slug:
        c.slug = slug.strip().lower().replace(" ", "-")
    c.model_id = int(model_id) if model_id.isdigit() else None
    c.published_at = published_at or None
    c.status = status
    c.featured = bool(featured)
    s.commit()
    return RedirectResponse(f"/admin/collections/{col_id}/edit", 303)


@router.post("/collections/{col_id}/delete")
async def admin_collection_delete(col_id: int, s: Session = Depends(get_db)):
    c = s.get(Collection, col_id)
    if c:
        s.delete(c)
        s.commit()
    return RedirectResponse("/admin/collections", 303)


# ---- Tags ----------------------------------------------------------------------

@router.get("/tags")
async def admin_tags(request: Request, s: Session = Depends(get_db)):
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()
    return templates.TemplateResponse(request, "admin/tags.html", {
        "page": "admin", "tags": tags, "error": "",
    })


@router.post("/tags/new")
async def admin_tag_create(request: Request, s: Session = Depends(get_db), name: str = Form(...)):
    name = name.strip()
    slug = name.lower().replace(" ", "-")
    if name and not s.scalar(select(Tag).where(Tag.slug == slug)):
        s.add(Tag(name=name, slug=slug))
        s.commit()
    return RedirectResponse("/admin/tags", 303)


@router.post("/tags/{tag_id}/delete")
async def admin_tag_delete(tag_id: int, s: Session = Depends(get_db)):
    t = s.get(Tag, tag_id)
    if t:
        s.delete(t)
        s.commit()
    return RedirectResponse("/admin/tags", 303)


# ---- Users ---------------------------------------------------------------------

@router.get("/users")
async def admin_users(request: Request, s: Session = Depends(get_db)):
    users = s.scalars(select(User).order_by(User.id)).all()
    return templates.TemplateResponse(request, "admin/users.html", {
        "page": "admin", "users": users, "error": request.query_params.get("error", ""),
    })


@router.post("/users/new")
async def admin_user_create(request: Request, s: Session = Depends(get_db),
                            username: str = Form(...), password: str = Form(...),
                            role: str = Form("user")):
    username = username.strip()
    if not username or len(password) < 6:
        return RedirectResponse(f"/admin/users?error={t('密码至少 6 位')}", 303)
    if s.scalar(select(User).where(User.username == username)):
        return RedirectResponse(f"/admin/users?error={t('用户名已存在')}", 303)
    s.add(User(username=username, password_hash=hash_password(password),
               role=role if role in ("user", "admin") else "user"))
    s.commit()
    return RedirectResponse("/admin/users", 303)


@router.post("/users/{user_id}/role")
async def admin_user_role(user_id: int, role: str = Form(...), s: Session = Depends(get_db)):
    u = s.get(User, user_id)
    if u and role in ("user", "admin"):
        u.role = role
        s.commit()
    return RedirectResponse("/admin/users", 303)


@router.post("/users/{user_id}/password")
async def admin_user_password(user_id: int, password: str = Form(...), s: Session = Depends(get_db)):
    u = s.get(User, user_id)
    if u and len(password) >= 6:
        u.password_hash = hash_password(password)
        # 踢掉所有会话
        for sess in s.scalars(select(DbSession).where(DbSession.user_id == user_id)).all():
            s.delete(sess)
        s.commit()
    return RedirectResponse("/admin/users", 303)


@router.post("/users/{user_id}/delete")
async def admin_user_delete(user_id: int, request: Request, s: Session = Depends(get_db)):
    if request.state.user.id == user_id:
        return RedirectResponse(f"/admin/users?error={t('不能删除自己')}", 303)
    u = s.get(User, user_id)
    if u:
        s.delete(u)
        s.commit()
    return RedirectResponse("/admin/users", 303)


@router.post("/collections/{col_id}/tags")
async def admin_collection_tag_add(col_id: int, tag: str = Form(...), s: Session = Depends(get_db)):
    c = s.get(Collection, col_id)
    if not c:
        raise HTTPException(404)
    name = tag.strip()
    if name:
        slug = name.lower().replace(" ", "-")
        t = s.scalar(select(Tag).where(Tag.slug == slug))
        if not t:
            t = Tag(name=name, slug=slug)
            s.add(t)
            s.flush()
        if t not in c.tags:
            c.tags.append(t)
            s.commit()
    return RedirectResponse(f"/admin/collections/{col_id}/edit", 303)


@router.post("/collections/{col_id}/tags/{tag_id}/delete")
async def admin_collection_tag_remove(col_id: int, tag_id: int, s: Session = Depends(get_db)):
    c = s.get(Collection, col_id)
    t = s.get(Tag, tag_id)
    if c and t and t in c.tags:
        c.tags.remove(t)
        s.commit()
    return RedirectResponse(f"/admin/collections/{col_id}/edit", 303)


# ---- 采集(§29)--------------------------------------------------------------------

@router.get("/harvest")
async def admin_harvest(request: Request, s: Session = Depends(get_db)):
    jobs = s.scalars(select(HarvestJob).order_by(desc(HarvestJob.id)).limit(100)).all()
    history_count = s.scalar(select(func.count(HarvestHistory.serial))) or 0
    conf = settings_store.harvest_conf(s)
    return templates.TemplateResponse(request, "admin/harvest.html", {
        "page": "admin", "jobs": jobs, "history_count": history_count,
        "conf": conf, "harvest_keys": settings_store.HARVEST_KEYS,
        "worker_running": harvest_worker.worker_running(),
        "flash": request.query_params.get("flash", ""),
    })


@router.post("/harvest/submit")
async def admin_harvest_submit(request: Request, url: str = Form(...)):
    ok, msg = harvest_worker.enqueue_manual(url.strip())
    return RedirectResponse(f"/admin/harvest?flash={quote(msg)}", 303)


@router.post("/harvest/scan")
async def admin_harvest_scan(request: Request):
    stats = harvest_worker.scan_once()
    msg = t("扫描 {n} 页,新任务 {m}", n=stats["scanned_pages"], m=stats["enqueued"])
    if stats.get("error"):
        msg = t("扫描失败: {e}", e=stats["error"])
    return RedirectResponse(f"/admin/harvest?flash={quote(msg)}", 303)


@router.post("/harvest/import")
async def admin_harvest_import(s: Session = Depends(get_db)):
    """扫描归档库(library)导入平台:移动图片到 /media + 建库,导入即发布。"""
    from ..services import library_import
    conf = settings_store.harvest_conf(s)
    stats = library_import.import_library(
        s, Path(str(conf["library.dir"])), settings.media_dir,
        unsorted_dir=str(conf["harvest.unsorted_dir"]))
    if stats["errors"]:
        msg = t("导入 {n} 个写真({p} 张),失败 {e} 个",
                n=stats["imported"], p=stats["photos"], e=len(stats["errors"]))
    elif stats["albums"] == 0:
        msg = t("归档库为空 — 没有可导入的写真")
    else:
        msg = t("导入 {n} 个写真({p} 张照片),跳过 {s} 个",
                n=stats["imported"], p=stats["photos"], s=stats["skipped"])
    return RedirectResponse(f"/admin/harvest?flash={quote(msg)}", 303)


@router.post("/harvest/{job_id}/retry")
async def admin_harvest_retry(job_id: int, s: Session = Depends(get_db)):
    job = s.get(HarvestJob, job_id)
    if job and job.status in ("failed", "skipped"):
        job.status = "queued"
        job.error = None
        job.finished_at = None
        # 从历史移除,允许重新处理
        hist = s.get(HarvestHistory, job.serial)
        if hist:
            s.delete(hist)
        s.commit()
    return RedirectResponse("/admin/harvest", 303)


@router.post("/harvest/{job_id}/cancel")
async def admin_harvest_cancel(job_id: int, s: Session = Depends(get_db)):
    job = s.get(HarvestJob, job_id)
    if job and job.status == "queued":
        s.delete(job)
        s.commit()
    return RedirectResponse("/admin/harvest", 303)


@router.get("/api/harvest/jobs")
async def admin_harvest_jobs_api(s: Session = Depends(get_db)):
    """轮询端点:返回最近任务状态(2s 轮询用)。"""
    jobs = s.scalars(select(HarvestJob).order_by(desc(HarvestJob.id)).limit(30)).all()
    return {"jobs": [{
        "id": j.id, "serial": j.serial, "status": j.status, "title": j.title or "",
        "model": j.model_name or "", "error": j.error or "",
        "bytesDone": j.bytes_done, "bytesTotal": j.bytes_total,
        "source": j.source,
        "createdAt": j.created_at.strftime("%m-%d %H:%M") if j.created_at else "",
    } for j in jobs],
        "workerRunning": harvest_worker.worker_running()}


# ---- 设置 -----------------------------------------------------------------------

@router.get("/settings")
async def admin_settings(request: Request, s: Session = Depends(get_db)):
    conf = settings_store.harvest_conf(s)
    return templates.TemplateResponse(request, "admin/settings.html", {
        "page": "admin", "conf": conf,
        "harvest_keys": settings_store.HARVEST_KEYS,
        "flash": request.query_params.get("flash", ""),
    })


@router.post("/settings")
async def admin_settings_save(request: Request, s: Session = Depends(get_db)):
    form = await request.form()
    for key, (_dflt, _label, _typ) in settings_store.HARVEST_KEYS.items():
        if key == "library.dir":
            continue  # 运行时从 env 改,避免运行中换根目录
        val = form.get(key)
        if val is None:
            continue
        settings_store.set_setting(s, key, str(val))
    # 站点默认语言(可选提交)
    site_lang = form.get("site.language")
    if site_lang:
        from ..i18n import LANGUAGES, normalize_lang
        code = normalize_lang(str(site_lang))
        if code in LANGUAGES:
            settings_store.set_setting(s, "site.language", code)
    # checkbox 显式关闭存 "0"(空串会被误读为默认值 "1")
    for key, (_d, _l, typ) in settings_store.HARVEST_KEYS.items():
        if typ is bool and key not in form:
            settings_store.set_setting(s, key, "0")
    s.commit()
    return RedirectResponse(f"/admin/settings?flash={t('已保存')}", 303)
