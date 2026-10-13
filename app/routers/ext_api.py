"""浏览器联动 API(/api/ext/*)— 供油猴脚本推送下载与查询入库状态。

鉴权: X-PhotoBook-Key 请求头, 与 settings 表 ext.api_key 比对(常量时间)。
不走路由/会话鉴权; GM_xmlhttpRequest 不受 CORS 限制, 服务端无需 CORS 头。
"""

from __future__ import annotations

import hmac
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..database import get_db
from ..db import Collection, HarvestHistory, HarvestJob
from ..i18n import t
from ..services import settings_store
from ..services.harvest import net
from ..services.harvest.worker import enqueue, ACTIVE_JOB_STATES

router = APIRouter(prefix="/api/ext")

API_KEY_SETTING = "ext.api_key"
# 单次状态查询/推送的 serial 数上限(一页卡片 24~48 个, 留余量)
MAX_SERIALS = 100


# ---- API key ----------------------------------------------------------------

def get_or_create_api_key(s: Session) -> str:
    """读当前 key, 不存在则生成(首次打开设置页即生效)。"""
    key = settings_store.get_setting(s, API_KEY_SETTING)
    if not key:
        key = secrets.token_urlsafe(24)
        settings_store.set_setting(s, API_KEY_SETTING, key)
        s.commit()
    return key


def reset_api_key(s: Session) -> str:
    key = secrets.token_urlsafe(24)
    settings_store.set_setting(s, API_KEY_SETTING, key)
    s.commit()
    return key


def _check_key(s: Session, x_photobook_key: str | None) -> None:
    expected = settings_store.get_setting(s, API_KEY_SETTING)
    if not expected or not x_photobook_key or \
            not hmac.compare_digest(x_photobook_key, expected):
        raise HTTPException(401, "invalid or missing API key")


async def require_key(x_photobook_key: str | None = Header(default=None),
                      s: Session = Depends(get_db)) -> Session:
    _check_key(s, x_photobook_key)
    return s


# ---- 状态判定 ----------------------------------------------------------------

def collection_exists(s: Session, serial: int) -> bool:
    """该序号的写真是否真实在库(collections 行还在 → 已入库)。

    同一本写真常被三个源站各自转载, 序号体系相互独立(buondua 56556 ↔
    misskon 117727 ↔ nicesss 496839)。除 source_serial 外还要看
    source_serials 里收录的其他站序号, 否则从没下过的那一站打开链接
    会显示「可下载」, 点了重复下一遍已入库的包。
    """
    if s.scalar(select(Collection.id).where(
            Collection.source_serial == serial).limit(1)) is not None:
        return True
    # source_serials 是 JSON 数组文本;用 LIKE 兜一层粗筛再精确解析,
    # 免得每次全表 load JSON。序号 >= 3 位(见 net 各站解析), 逗号定界
    # 不会误命中更长数字的子串(如 1234 不命中 21234)。
    for (raw,) in s.execute(
            select(Collection.source_serials).where(
                Collection.source_serials.like(f"%{serial},%") |
                Collection.source_serials.like(f"%{serial}]%") |
                Collection.source_serials.like(f"%[{serial}%"))):
        try:
            if serial in json.loads(raw or "[]"):
                return True
        except (ValueError, TypeError):
            continue
    return False


def state_for_serial(s: Session, serial: int) -> str:
    """单个序号 → 联动状态。脚本只认这几个词:

    new      无任何记录, 可下载
    queued   任务排队/进行中
    done     已入库(collections 存在, 含 done/exists 历史)
    failed   上次失败, 可重推
    skipped  被黑白名单过滤, 可重推
    """
    if s.scalar(select(HarvestJob.id).where(
            HarvestJob.serial == serial,
            HarvestJob.status.in_(ACTIVE_JOB_STATES)).limit(1)):
        return "queued"
    if collection_exists(s, serial):
        return "done"
    hist = s.get(HarvestHistory, serial)
    if hist is not None:
        if hist.status in ("done", "exists"):
            # 处理过但写真已删 → 视为可重新下载
            return "new"
        return hist.status if hist.status in ("failed", "skipped") else "new"
    return "new"


# ---- 端点 --------------------------------------------------------------------

class PushBody(BaseModel):
    url: str | None = None
    urls: list[str] | None = None
    force: bool = False


SUPPORTED_HOSTS = ("buondua.com", net.NICESSS_HOST, net.MISSKON_HOST)


def _serial_from_url(url: str) -> int:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    if not any(h in host for h in SUPPORTED_HOSTS):
        raise ValueError(t("仅支持 {sites} 详情页链接",
                           sites=" / ".join(SUPPORTED_HOSTS)))
    return net.serial_from_url(url)  # ValueError: 无法解析序号


def _push_one(s: Session, url: str, force: bool) -> dict[str, Any]:
    """单条推送。返回 {ok, state, serial, message}。"""
    try:
        serial = _serial_from_url(url)
    except ValueError as e:
        return {"ok": False, "state": "rejected", "serial": None,
                "message": str(e)}

    # 已入库优先于一切(含没有 history 行的跨站序号): 同一本写真在三站
    # 序号各自独立, 另外两站的链接第一次点也会走到这里。
    if collection_exists(s, serial):
        return {"ok": False, "state": "duplicate", "serial": serial,
                "message": t("已入库,无需重复下载")}

    hist = s.get(HarvestHistory, serial)
    if hist is not None:
        if hist.status in ("done", "exists"):
            # 曾处理过但写真已删: 允许直接重推(清历史行重新入队)
            s.delete(hist)
            s.commit()
        elif hist.status in ("failed", "skipped"):
            if not force:
                return {"ok": False, "state": hist.status, "serial": serial,
                        "message": t("上次{what},如需重试请使用重推",
                                     what="失败" if hist.status == "failed" else "被跳过")}
            s.delete(hist)
            s.commit()
        else:
            return {"ok": False, "state": "duplicate", "serial": serial,
                    "message": t("该写真(序号 {s})已处理过", s=serial)}

    if s.scalar(select(HarvestJob.id).where(
            HarvestJob.serial == serial,
            HarvestJob.status.in_(ACTIVE_JOB_STATES)).limit(1)):
        return {"ok": False, "state": "queued", "serial": serial,
                "message": t("任务已在队列中")}

    job = enqueue(s, serial, url, source="manual")
    if job is None:
        return {"ok": False, "state": "queued", "serial": serial,
                "message": t("任务已在队列中")}
    s.commit()
    return {"ok": True, "state": "queued", "serial": serial,
            "message": t("已加入队列(序号 {s})", s=serial)}


@router.post("/harvest")
async def push_harvest(body: PushBody, s: Session = Depends(require_key)):
    urls = list(body.urls or ([] if not body.url else [body.url]))
    if not urls:
        raise HTTPException(422, "url or urls required")
    if len(urls) > MAX_SERIALS:
        raise HTTPException(422, f"too many urls (max {MAX_SERIALS})")
    items = [_push_one(s, u.strip(), body.force) for u in urls if u.strip()]
    ok = all(i["ok"] for i in items)
    return {"ok": ok, "items": items}


@router.get("/status")
async def status_api(serials: str, s: Session = Depends(require_key)):
    """批量查询入库状态。serials=逗号分隔的源站序号。"""
    try:
        ids = [int(x) for x in serials.split(",") if x.strip()][:MAX_SERIALS]
    except ValueError:
        raise HTTPException(422, "serials must be integers")
    if not ids:
        raise HTTPException(422, "serials required")
    return {"items": [{"serial": i, "state": state_for_serial(s, i)} for i in ids]}


class StatusByUrlBody(BaseModel):
    urls: list[str]


@router.post("/status-by-url")
async def status_by_url(body: StatusByUrlBody, s: Session = Depends(require_key)):
    """按详情 URL 查入库状态(服务端解析序号)。

    misskon 老帖的 slug 没有 <序号>- 前缀,油猴脚本本地取不到序号,
    只能把 URL 交给服务端:序号能解析的按序号判态,解析不出的回
    state=new + serial=null(脚本照常显示「下载」,点了推送时再由
    /harvest 从 URL 解析)。
    """
    urls = [u.strip() for u in (body.urls or []) if u.strip()][:MAX_SERIALS]
    if not urls:
        raise HTTPException(422, "urls required")
    items = []
    for url in urls:
        try:
            serial = _serial_from_url(url)
        except ValueError:
            items.append({"url": url, "serial": None, "state": "new"})
            continue
        items.append({"url": url, "serial": serial,
                      "state": state_for_serial(s, serial)})
    return {"items": items}


@router.get("/ping")
async def ping(s: Session = Depends(require_key)):
    return {"ok": True, "version": __version__}
