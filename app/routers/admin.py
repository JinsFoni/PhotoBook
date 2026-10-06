"""管理端 — Dashboard / CRUD / 采集任务 / 设置。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, unquote as _unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services import media, tagging
from . import ext_api
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..config import settings
from ..db import (Collection, Favorite, HarvestHistory, HarvestJob, local_dt, Model, Photo,
                  Session as DbSession, Setting, Tag, User)
from ..database import get_db
from ..i18n import t
from ..templating import templates
from ..services import settings_store
from ..services.harvest import worker as harvest_worker

log = logging.getLogger("photobook.admin")

# 采集任务列表:每页条数与状态筛选分组(接口/模板/JS 共用同一份定义)
JOBS_PER_PAGE = 20
JOB_STATUS_GROUPS: dict[str, tuple[str, ...]] = {
    "active": ("queued", "parsing", "downloading", "extracting"),
    "done": ("done", "exists"),
    "skipped": ("skipped",),
    "failed": ("failed",),
}


def _jobs_query(s: Session, status: str):
    """任务列表查询:status 为分组键(active/done/skipped/failed)时按状态过滤。

    状态有索引(ix_jobs_status_id),过滤后按 id 倒序取页都是索引扫描。
    """
    q = select(HarvestJob)
    statuses = JOB_STATUS_GROUPS.get(status or "")
    if statuses:
        q = q.where(HarvestJob.status.in_(statuses))
    return q.order_by(desc(HarvestJob.id))


def _clamp_page(page: int, total: int, per_page: int) -> int:
    """把请求页码限制在 [1, total_pages];无数据时返回 1。"""
    pages = max(1, -(-total // per_page))
    return min(max(1, page), pages)


def _paged_items(s: Session, q, page: int, per_page: int, order_by) -> tuple[list, int, int, int]:
    """通用列表分页:返回 (items, page, total_pages, total)。

    与 _clamp_page 一样把页码钳回合法范围,越界(如删完最后一页的最后一条)
    自动落到有效页。
    """
    total = s.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    page = _clamp_page(page, total, per_page)
    items = s.scalars(q.order_by(order_by)
                      .offset((page - 1) * per_page).limit(per_page)).all()
    return items, page, max(1, -(-total // per_page)), total


def _search_q(model, q: str, *columns):
    """列表页搜索:q 非空时对给定列做不区分大小写的 LIKE,空串返回原查询。"""
    base = select(model)
    if q:
        like = f"%{q.lower()}%"
        return base.where(or_(*[func.lower(col).like(like) for col in columns]))
    return base


def _thumb_status_text(s: Session, job) -> str | None:
    """导入后的任务状态文案(实时,替代导入瞬间写死的静态字符串)。

    导入成功时 error 停留在「…缩略图生成中#n」,但缩略图队列完成后没人回写。
    这里对带 collection_slug 的 done 任务查写真状态:
      - 已 published → 把「,缩略图生成中#n」尾巴换成「,已完成」
      - 仍 processing → 保持原文案(真实仍在生成)
    返回 None = 不需要调整(非 done / 无 slug / 非该文案)。
    """
    from ..db import Collection

    if job.status != "done" or not job.collection_slug or not job.error:
        return None
    if "缩略图生成中" not in job.error:
        return None
    col = s.scalar(select(Collection).where(Collection.slug == job.collection_slug))
    if col is None or col.status != "published":
        return None
    return re.sub(r",缩略图生成中#\d+$", "," + t("已完成"), job.error)


def _job_display_error(s: Session, job) -> str:
    """任务展示用 error(可能被实时缩略图状态覆盖)。"""
    overridden = _thumb_status_text(s, job)
    return overridden if overridden is not None else (job.error or "")


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _conf_value(s: Session, key: str, dflt: str) -> str:
    v = settings_store.get_setting(s, key)
    return v if v is not None and v != "" else dflt


def _back_qs(status: str, page: int) -> str:
    """操作后回跳列表的查询串(保持筛选与页码;默认值则省略)。
    只做一次 urlencode —— 再叠 quote 会把 &/= 也编进值里,
    _back_params 的白名单正则解析不出 status/page, AJAX 操作会静默回落第 1 页。"""
    params: dict[str, str] = {}
    if status in JOB_STATUS_GROUPS:
        params["status"] = status
    if page > 1:
        params["page"] = str(page)
    return ("?" + urlencode(params)) if params else ""


# 模板全局:操作表单的回跳查询串(在定义后挂载,避免与 templating 循环导入)
templates.env.globals["_back_qs"] = _back_qs


def _back_qsp(q: str, page: int) -> str:
    """模特/写真集列表操作表单的回跳查询串(保持搜索词与页码;默认值则省略)。
    只做一次 urlencode —— 再叠 quote 会把 &/= 也编进值里,
    _list_action_response 的白名单正则解析不出 q/page, AJAX 删除会静默回落第 1 页。"""
    params: dict[str, str] = {}
    if q:
        params["q"] = q
    if page > 1:
        params["page"] = str(page)
    return ("?" + urlencode(params)) if params else ""


templates.env.globals["_back_qsp"] = _back_qsp


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

ADMIN_PAGE_SIZE = 20  # 模特/写真集列表每页条数


@router.get("/models")
async def admin_models(request: Request, s: Session = Depends(get_db),
                       q: str = "", page: int = 1):
    q = q.strip()[:100]
    query = _search_q(Model, q, Model.name, Model.slug, Model.stage_name)
    models, page, total_pages, total = _paged_items(
        s, query, page, ADMIN_PAGE_SIZE, Model.name)
    counts = dict(s.execute(
        select(Collection.model_id, func.count(Collection.id))
        .group_by(Collection.model_id)).all())
    return templates.TemplateResponse(request, "admin/models.html", {
        "page": "admin", "models": models,
        "col_counts": counts, "error": request.query_params.get("error", ""),
        "q": q, "cur_page": page, "total_pages": total_pages, "total_count": total,
        "flash": request.query_params.get("flash", ""),
    })


@router.get("/api/models")
async def admin_models_api(s: Session = Depends(get_db), q: str = "", page: int = 1):
    """模特列表翻页端点:前端拦截翻页链接 fetch 后原地重绘,不整页刷新。"""
    return _models_list_payload(s, q, page)


def _models_list_payload(s: Session, q: str, page: int) -> dict:
    """模特列表分页 payload(翻页 API 与删除后 AJAX 重绘共用, 保证口径一致)。"""
    q = q.strip()[:100]
    query = _search_q(Model, q, Model.name, Model.slug, Model.stage_name)
    models, page, total_pages, total = _paged_items(
        s, query, page, ADMIN_PAGE_SIZE, Model.name)
    counts = dict(s.execute(
        select(Collection.model_id, func.count(Collection.id))
        .group_by(Collection.model_id)).all())
    return {"models": [{"id": m.id, "name": m.name, "slug": m.slug,
                        "stageName": m.stage_name or "",
                        "collections": counts.get(m.id, 0)} for m in models],
            "page": page, "totalPages": total_pages, "total": total}


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
async def admin_model_delete(request: Request, model_id: int, s: Session = Depends(get_db),
                             back: str = Form("")):
    m = s.get(Model, model_id)
    flash = ""
    if m:
        # 该模特名下所有写真集一并删除(DB + 磁盘: 照片/缩略图/收藏);
        # ORM 无级联(DB 层 model_id SET NULL 只会留下无主写真集), 显式删
        victims = [(c.slug, [p.filename for p in c.photos])
                   for c in s.scalars(select(Collection).where(Collection.model_id == model_id)).all()]
        for slug, filenames in victims:
            col = s.scalar(select(Collection).where(Collection.slug == slug))
            if col:
                s.delete(col)
        s.delete(m)
        s.commit()
        for slug, filenames in victims:
            media.purge_collection_files(slug, filenames)
        tagging.prune_empty_tags(s)
        flash = t("模特已删除: {n}", n=m.name)
    return _list_action_response(request, s, _models_list_payload,
                                 "/admin/models", back, flash)


# ---- Collections CRUD ------------------------------------------------------------

@router.get("/collections")
async def admin_collections(request: Request, s: Session = Depends(get_db),
                            q: str = "", page: int = 1):
    q = q.strip()[:100]
    query = _search_q(Collection, q, Collection.title, Collection.slug)
    cols, page, total_pages, total = _paged_items(
        s, query, page, ADMIN_PAGE_SIZE, desc(Collection.id))
    models = s.scalars(select(Model).order_by(Model.name)).all()
    return templates.TemplateResponse(request, "admin/collections.html", {
        "page": "admin", "collections": cols, "models": models,
        "error": request.query_params.get("error", ""),
        "q": q, "cur_page": page, "total_pages": total_pages, "total_count": total,
        "flash": request.query_params.get("flash", ""),
    })


@router.get("/api/collections")
async def admin_collections_api(s: Session = Depends(get_db), q: str = "", page: int = 1):
    """写真集列表翻页端点:前端拦截翻页链接 fetch 后原地重绘,不整页刷新。"""
    return _collections_list_payload(s, q, page)


def _collections_list_payload(s: Session, q: str, page: int) -> dict:
    """写真集列表分页 payload(翻页 API 与删除后 AJAX 重绘共用, 保证口径一致)。"""
    q = q.strip()[:100]
    query = _search_q(Collection, q, Collection.title, Collection.slug)
    cols, page, total_pages, total = _paged_items(
        s, query, page, ADMIN_PAGE_SIZE, desc(Collection.id))
    return {"collections": [{"id": c.id, "title": c.title or "", "slug": c.slug,
                             "model": c.model.name if c.model else "",
                             "publishedAt": str(c.published_at or ""),
                             "status": c.status} for c in cols],
            "page": page, "totalPages": total_pages, "total": total}
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
async def admin_collection_delete(request: Request, col_id: int, s: Session = Depends(get_db),
                                  back: str = Form("")):
    c = s.get(Collection, col_id)
    flash = ""
    if c:
        slug, filenames = c.slug, [p.filename for p in c.photos]
        model_id = c.model_id
        s.delete(c)
        # 名下写真集删光后模特一并删除(前台模特无写真即不可见, 留着成死链)
        if model_id is not None:
            m = s.get(Model, model_id)
            if m and not s.scalar(select(Collection.id).where(Collection.model_id == model_id).limit(1)):
                s.delete(m)
        s.commit()
        media.purge_collection_files(slug, filenames)
        tagging.prune_empty_tags(s)
        flash = t("写真集已删除: {t}", t=c.title or slug)
    return _list_action_response(request, s, _collections_list_payload,
                                 "/admin/collections", back, flash)


# ---- Tags ----------------------------------------------------------------------

@router.get("/tags")
async def admin_tags(request: Request, s: Session = Depends(get_db),
                     flash: str = ""):
    tags = s.scalars(select(Tag).order_by(Tag.name)).all()
    return templates.TemplateResponse(request, "admin/tags.html", {
        "page": "admin", "tags": tags, "error": "", "flash": flash,
    })


@router.post("/tags/retag")
async def admin_tags_retag(s: Session = Depends(get_db)):
    """补录:重新解析已 done 采集任务的详情页,把 tag 补到合集与模特。"""
    stats = tagging.retag_from_history(s)
    pruned = tagging.prune_empty_tags(s)
    msg = t("补录完成:匹配 {m} 个,新关联 {n} 条,跳过 {k} 个"
            + (f",清理孤儿标签 {pruned} 个" if pruned else ""),
            m=stats["matched"], n=stats["tagged"], k=stats["skipped"])
    return RedirectResponse(f"/admin/tags?flash={quote(msg)}", 303)


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
async def admin_harvest(request: Request, s: Session = Depends(get_db),
                        page: int = 1, status: str = ""):
    total = s.scalar(select(func.count()).select_from(
        _jobs_query(s, status).subquery())) or 0
    page = _clamp_page(page, total, JOBS_PER_PAGE)
    jobs = s.scalars(_jobs_query(s, status)
                     .offset((page - 1) * JOBS_PER_PAGE)
                     .limit(JOBS_PER_PAGE)).all()
    # 展示文案实时化:「缩略图生成中」在队列完成后显示「已完成」(见 _thumb_status_text)
    display_errors = {j.id: _job_display_error(s, j) for j in jobs}
    total_pages = max(1, -(-total // JOBS_PER_PAGE))
    # 各筛选分组的任务数(一次分组查询,供筛选胶囊显示计数)
    status_counts = dict(s.execute(
        select(HarvestJob.status, func.count(HarvestJob.id)).group_by(HarvestJob.status)).all())
    chip_counts = {g: sum(status_counts.get(st, 0) for st in sts)
                   for g, sts in JOB_STATUS_GROUPS.items()}
    chip_counts[""] = sum(status_counts.values())
    active_count = chip_counts["active"]
    history_count = s.scalar(select(func.count(HarvestHistory.serial))) or 0
    conf = settings_store.harvest_conf(s)
    status_icon = {"queued": "clock", "parsing": "search", "downloading": "download",
                   "extracting": "archive", "done": "check-circle", "exists": "check-circle",
                   "skipped": "minus", "failed": "close"}
    return templates.TemplateResponse(request, "admin/harvest.html", {
        "page": "admin", "jobs": jobs, "history_count": history_count,
        "display_errors": display_errors,
        "conf": conf, "harvest_keys": settings_store.HARVEST_KEYS,
        "status_icon": status_icon,
        "job_status_groups": JOB_STATUS_GROUPS,
        "cur_status": status, "cur_page": page,
        "total_count": total, "total_pages": total_pages,
        "chip_counts": chip_counts, "active_count": active_count,
        "per_page": JOBS_PER_PAGE,
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


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "fetch"


def _list_action_response(request: Request, s: Session, payload_fn,
                          list_path: str, back: str, flash: str):
    """模特/写真集列表操作(删除)的统一响应, 与任务队列 _action_response 同模式:

    AJAX 请求返回列表 payload(前端原地重绘, 不整页刷新);
    普通表单提交保持 303 重定向(无 JS 环境兼容)。
    back 仅接受 ?q=<词>&page=<n> / 子集的白名单形态, 不匹配则回第 1 页。
    注意匹配用的 q 已是原始编码(percent-encoded)形态, 深层解码交给 payload_fn。
    """
    if _is_ajax(request):
        m = re.fullmatch(r"\?q=([^&]*)(?:&page=(\d+))?|\?page=(\d+)", back or "")
        q = ""
        page = 1
        if m:
            # q 里的空格有两种来源: 服务端 _back_qsp 的 urlencode 编成 "+",
            # 前端 encodeURIComponent 编成 "%20" —— 先归一成 %20 再解码,
            # 否则带空格的搜索词会查不到任何条目, AJAX 重绘成空列表。
            q = _unquote((m.group(1) or "").replace("+", "%20")) if m.group(1) is not None else ""
            page = int(m.group(2) or m.group(3) or 1)
        payload = payload_fn(s, q, page)
        if flash:
            payload["flash"] = flash
        return payload
    target = list_path + (back if back.startswith("?") else "")
    if flash:
        target += ("&" if back else "?") + "flash=" + quote(flash)
    return RedirectResponse(target, 303)


def _action_response(request: Request, s: Session, status: str, page: int,
                     back: str, flash: str):
    """AJAX 请求返回列表 payload(前端原地重绘, 不整页刷新);
    普通表单提交保持 303 重定向(无 JS 环境兼容)。"""
    if _is_ajax(request):
        payload = _harvest_list_payload(s, status, page)
        if flash:
            payload["flash"] = flash
        return payload
    target = f"/admin/harvest{back}"
    if flash:
        target += ("&" if back else "?") + "flash=" + quote(flash)
    return RedirectResponse(target, 303)


def _back_params(back: str) -> tuple[str, int]:
    """从白名单形态的 back 查询串解析 (status, page),供 AJAX 响应重绘当前页。

    仅接受本方 _back_qs 生成的形态: ?status=<组>&page=<n> / 子集。
    """
    m = re.fullmatch(r"\?status=(active|done|skipped|failed)(?:&page=(\d+))?"
                     r"|\?page=(\d+)", back or "")
    if not m:
        return "", 1
    if m.group(3):
        return "", int(m.group(3))
    return m.group(1), int(m.group(2) or 1)


@router.post("/harvest/{job_id}/retry")
async def admin_harvest_retry(request: Request, job_id: int, s: Session = Depends(get_db),
                              back: str = Form("")):
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
    status, page = _back_params(back)
    return _action_response(request, s, status, page, back, "")


@router.post("/harvest/{job_id}/cancel")
async def admin_harvest_cancel(request: Request, job_id: int, s: Session = Depends(get_db),
                               back: str = Form("")):
    job = s.get(HarvestJob, job_id)
    if job and job.status == "queued":
        s.delete(job)
        s.commit()
    status, page = _back_params(back)
    return _action_response(request, s, status, page, back, "")


@router.post("/harvest/{job_id}/delete")
async def admin_harvest_delete(request: Request, job_id: int, s: Session = Depends(get_db),
                               back: str = Form("")):
    """删除终态任务记录。

    - 正常 done/exists/skipped:只删记录,不碰任何文件(done 已导入平台,
      exists/skipped 本就无残留)
    - 带 archive_dir 的任务(import 失败,残包留在 library):删除时连带清理
      残留目录 — 它未入库,不删就是孤儿。路径必须是 library 子目录,防误删。
    """
    status, page = _back_params(back)  # 白名单校验在 _back_params 内, 不匹配则回第 1 页
    if back and not (status or page > 1):
        back = ""  # 非白名单形态: AJAX 重绘已安全, 303 重定向退回干净列表
    job = s.get(HarvestJob, job_id)
    if not job:
        return _action_response(request, s, status, page, back, "")
    if job.status not in ("done", "exists", "skipped", "failed"):
        # 运行中/排队中不能用删除(应走取消/等完成), 防误删进行中的任务记录
        return _action_response(request, s, status, page, back, t("任务进行中,不能删除"))
    if job.archive_dir:
        # failed(下载/导入失败)或存量 done(旧版 import 失败未改判)可能带归档残留;
        # 正常 done 任务无 archive_dir, 不会误删任何文件。
        import shutil
        from ..services.settings_store import harvest_conf
        conf = harvest_conf(s)
        library_root = Path(str(conf["library.dir"])).resolve()
        try:
            target = Path(job.archive_dir).resolve()
            # 只删 library 内的目录; 保护根与 _tmp
            if (target.is_dir() and str(target).startswith(str(library_root) + "/")
                    and target != library_root and target.name != "_tmp"):
                shutil.rmtree(target, ignore_errors=True)
                log.info("deleted failed-job residue: %s", target)
        except Exception:
            log.exception("delete residue failed: %s", job.archive_dir)
    hist = s.get(HarvestHistory, job.serial)
    if hist:
        s.delete(hist)
    s.delete(job)
    s.commit()
    return _action_response(request, s, status, page, back, t("任务已删除"))


def local_time_fmt(dt):
    d = local_dt(dt)
    return d.strftime("%m-%d %H:%M") if d else ""


def _harvest_list_payload(s: Session, status: str, page: int) -> dict:
    """任务列表分页 payload(API 与 AJAX 动作响应共用,保证前端重绘口径一致)。"""
    status = status if status in JOB_STATUS_GROUPS else ""
    total = s.scalar(select(func.count()).select_from(
        _jobs_query(s, status).subquery())) or 0
    page = _clamp_page(page, total, JOBS_PER_PAGE)
    jobs = s.scalars(_jobs_query(s, status)
                     .offset((page - 1) * JOBS_PER_PAGE)
                     .limit(JOBS_PER_PAGE)).all()
    status_counts = dict(s.execute(
        select(HarvestJob.status, func.count(HarvestJob.id)).group_by(HarvestJob.status)).all())
    chip_counts = {g: sum(status_counts.get(st, 0) for st in sts)
                   for g, sts in JOB_STATUS_GROUPS.items()}
    chip_counts[""] = sum(status_counts.values())
    return {"jobs": [{
        "id": j.id, "serial": j.serial, "status": j.status, "title": j.title or "",
        "model": j.model_name or "", "error": _job_display_error(s, j),
        "bytesDone": j.bytes_done, "bytesTotal": j.bytes_total,
        "source": j.source,
        "createdAt": local_time_fmt(j.created_at),
    } for j in jobs],
        "page": page, "totalPages": max(1, -(-total // JOBS_PER_PAGE)),
        "total": total,
        "chipCounts": chip_counts,
        "workerRunning": harvest_worker.worker_running(),
        "preheatRunning": media.preheat_running(),
        "preheatProgress": media.preheat_progress()}


@router.get("/api/harvest/jobs")
async def admin_harvest_jobs_api(s: Session = Depends(get_db),
                                 page: int = 1, status: str = ""):
    """轮询/翻页/筛选端点:页码与筛选由前端透传,原地重绘不整页刷新。"""
    return _harvest_list_payload(s, status, page)


# ---- 设置 -----------------------------------------------------------------------

@router.get("/settings")
async def admin_settings(request: Request, s: Session = Depends(get_db)):
    conf = settings_store.harvest_conf(s)
    return templates.TemplateResponse(request, "admin/settings.html", {
        "page": "admin", "conf": conf,
        "harvest_keys": settings_store.HARVEST_KEYS,
        "ext_key_tail": (settings_store.get_setting(s, ext_api.API_KEY_SETTING) or "")[-4:],
        "script_url": str(request.base_url).rstrip("/") + "/static/buondua-bridge.user.js",
        "flash": request.query_params.get("flash", ""),
    })


# ---- 浏览器联动 ---------------------------------------------------------------

@router.post("/settings/ext-key")
async def admin_ext_key_reset(s: Session = Depends(get_db)):
    key = ext_api.reset_api_key(s)
    msg = t("API Key 已重置: {k}(请立即复制,之后只显示尾号)", k=key)
    return RedirectResponse(f"/admin/settings?flash={quote(msg)}", 303)


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
