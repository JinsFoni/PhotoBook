"""浏览器联动 API(/api/ext/*)— 供油猴脚本推送下载与查询入库状态。

鉴权: X-PhotoBook-Key 请求头, 与 settings 表 ext.api_key 比对(常量时间)。
不走路由/会话鉴权; GM_xmlhttpRequest 不受 CORS 限制, 服务端无需 CORS 头。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..database import get_db
from ..db import Collection, HarvestHistory, HarvestJob, Photo
from ..i18n import t
from ..services import settings_store
from ..services.harvest import net
from ..services.harvest.titlematch import title_matches_collection
from ..services.harvest.worker import enqueue, ACTIVE_JOB_STATES
from ..services.pikpak import worker as pikpak_worker

router = APIRouter(prefix="/api/ext")

API_KEY_SETTING = "ext.api_key"
# 单次状态查询/推送的 serial 数上限(一页卡片 24~48 个, 留余量)
MAX_SERIALS = 100
# status-by-url 回源解析序号的并发上限(老帖整页 URL 都要拉详情页,
# 逐个串行 1s+ 会超过脚本 30s 超时; 并发太高对源站不礼貌)
_URL_RESOLVE_WORKERS = 5
_url_resolve_pool = ThreadPoolExecutor(
    max_workers=_URL_RESOLVE_WORKERS, thread_name_prefix="pb-url-resolve")
# PikPak 单次推送的勾选项个数上限(每人一次勾几个/几十个写真集)
MAX_PIKPAK_ITEMS = 5000
# 单次推送展开后的文件总数上限(勾选项较多时总量兜底, 防请求体过大)
MAX_PIKPAK_FILES = 50000


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


def _register_serial_title(s: Session, serial: int, title: str) -> bool:
    """按标题等价比对,把 serial 登记进命中的 collection.source_serials。

    同一本写真三站序号各自独立,序号只在「本站采集过」时才进得了
    source_serials;用户在另一站浏览时该站序号服务端无从知晓 —— 脚本
    查状态时把页面标题带上,这里比对命中即登记(状态查询顺带成了登记
    通道)。已登记(序号已在)返回 False,避免每 5s 轮询重复写库。

    性能: 全量候选快照缓存在进程内(TTL 60s), 避免每个未知标题都全表
    加载 289 个合集 ORM(连带 photos 时代实测单标题 0.4s, 一页 24 卡
    就是 10s)。快照是标量列, 比对纯内存, 写库只在命中时发生一次。
    快照带各合集的真实照片数(GROUP BY 一条)—— 入库 title 不带
    「(N photos)」尾缀, 标题等价必须以真实张数守卫, 否则泛化系列标题
    ([AI Generated] 诛仙-陆雪琪)的不同批次全会误登记(44755 实录)。
    """
    import json as _json

    if not (title or "").strip():
        return False

    # ---- 内存缓存: (id, title, source_serial, source_serials 原文, 张数) ----
    global _title_cache_data, _title_cache_at
    now = time.monotonic()
    with _title_cache_lock:
        if now - _title_cache_at > 60 or _title_cache_data is None:
            counts = dict(s.execute(
                select(Photo.collection_id, func.count(Photo.id))
                .group_by(Photo.collection_id)).all())
            _title_cache_data = [
                (cid, col_title, col_serial, raw_serials, counts.get(cid))
                for cid, col_title, col_serial, raw_serials in s.execute(
                    select(Collection.id, Collection.title,
                           Collection.source_serial, Collection.source_serials)
                    .where(Collection.source_serial.is_not(None))).all()]
            _title_cache_at = now
        snapshot = _title_cache_data

    def _load(json_raw: str | None) -> list:
        try:
            return _json.loads(json_raw or "[]")
        except (ValueError, TypeError):
            return []

    for cid, col_title, col_serial, raw_serials, col_photos in snapshot:
        if not title_matches_collection(title, col_title, col_photos):
            continue
        known = {col_serial, *_load(raw_serials)}
        known.discard(None)
        if serial in known:
            return False
        # 缓存快照可能滞后: 登记前按 DB 现值重读一次,防并发覆盖
        fresh = s.execute(
            select(Collection.source_serials, Collection.source_serial)
            .where(Collection.id == cid)).first()
        fresh_raw, fresh_serial = fresh if fresh else ("", None)
        known = {fresh_serial, *_load(fresh_raw)}
        known.discard(None)
        if serial in known:
            return False
        known.add(serial)
        col = s.get(Collection, cid)
        col.source_serials = _json.dumps(sorted(known))
        s.commit()
        _invalidate_title_cache()
        return True
    return False


_title_cache_data: list | None = None
_title_cache_at: float = 0.0
_title_cache_lock = threading.Lock()


def _invalidate_title_cache() -> None:
    global _title_cache_data, _title_cache_at
    with _title_cache_lock:
        _title_cache_data = None
        _title_cache_at = 0.0


@router.get("/status")
async def status_api(serials: str, s: Session = Depends(require_key)):
    """批量查询入库状态。serials=逗号分隔的源站序号。

    旧入口(不带标题): 只按序号判态。新脚本走 POST /status。
    """
    try:
        ids = [int(x) for x in serials.split(",") if x.strip()][:MAX_SERIALS]
    except ValueError:
        raise HTTPException(422, "serials must be integers")
    if not ids:
        raise HTTPException(422, "serials required")
    return {"items": [{"serial": i, "state": state_for_serial(s, i)} for i in ids]}


class StatusItem(BaseModel):
    serial: int
    title: str = ""


class StatusBody(BaseModel):
    items: list[StatusItem]


@router.post("/status")
async def status_api_v2(body: StatusBody, s: Session = Depends(require_key)):
    """批量查询入库状态 + 标题登记。

    items 每项 = (序号, 页面标题)。序号命中即返回状态;未命中但标题与
    已入库写真等价 → 登记进该写真的 source_serials 并返回 done(下次
    查询序号直接命中,不再做比对)。标题可比对不出(未入库/非同本)按
    普通判态返回。
    """
    items = body.items[:MAX_SERIALS]
    if not items:
        raise HTTPException(422, "items required")
    out = []
    for it in items:
        state = state_for_serial(s, it.serial)
        if state == "new" and it.title.strip():
            # 登记成功 → 本写真确认已在库(标题等价)
            if _register_serial_title(s, it.serial, it.title):
                state = "done"
        out.append({"serial": it.serial, "state": state})
    return {"items": out}


class StatusByUrlBody(BaseModel):
    urls: list[str]
    # url → 页面标题(可选)。老帖通道与 /status v2 同源:状态 new 且标题
    # 与已入库写真等价 → 登记进 source_serials 并返回 done。
    titles: dict[str, str] = {}


# ---- PikPak(油猴脚本 PikPak to PhotoBook)-----------------------------------

class PikPakFileItem(BaseModel):
    """勾选项展开后的单个文件(直链)。

    rel = 相对勾选项的路径(含文件名), 下载时按它落到写真目录,
    因此勾选的文件夹里有子目录时结构能原样保留。
    """
    file_id: str = ""
    url: str
    rel: str = ""
    size: int = 0


class PikPakItem(BaseModel):
    """一个勾选项(文件或文件夹) = 一个写真集 = 一个下载任务。"""
    file_id: str
    name: str
    files: list[PikPakFileItem] = []
    size: int = 0


class PikPakPushBody(BaseModel):
    items: list[PikPakItem]
    model_name: str = ""      # 模特名(空 = 未分类)
    tags: list[str] = []      # 脚本输入的标签


@router.post("/pikpak")
async def push_pikpak(body: PikPakPushBody, s: Session = Depends(require_key)):
    """推送 PikPak 勾选项入队。返回 {ok, queued, skipped, batchId}。

    一个勾选项 = 一个任务: 文件夹由脚本在本地递归展开成 files[](直链),
    worker 逐个下载到同一个写真目录; 压缩包也走 files[](单元素), 下载后
    解压归档。同 file_id 已在队列 → skipped。
    """
    if not body.items:
        raise HTTPException(422, "items required")
    if len(body.items) > MAX_PIKPAK_ITEMS:
        raise HTTPException(422, f"too many items (max {MAX_PIKPAK_ITEMS})")
    total_files = sum(len(i.files) for i in body.items)
    if total_files > MAX_PIKPAK_FILES:
        raise HTTPException(422, f"too many files (max {MAX_PIKPAK_FILES})")
    items = [i.model_dump() for i in body.items
             if (i.file_id or "").strip()]
    queued, skipped, batch_id = pikpak_worker.enqueue_batch(
        items, model_name=body.model_name, tags=body.tags)
    return {"ok": queued > 0, "queued": queued, "skipped": skipped,
            "batchId": batch_id}


@router.post("/status-by-url")
async def status_by_url(body: StatusByUrlBody, s: Session = Depends(require_key)):
    """按详情 URL 查入库状态(服务端解析序号)。

    misskon 老帖的 slug 没有 <序号>- 前缀,油猴脚本本地取不到序号,
    只能把 URL 交给服务端:序号能解析的按序号判态,解析不出的回
    state=new + serial=null(脚本照常显示「下载」,点了推送时再由
    /harvest 从 URL 解析)。

    脚本 1.6.0 起随 urls 带上 titles(url → 页面标题):状态 new 且
    标题与已入库写真等价 → 登记进 source_serials 并返回 done(老帖
    列表页卡片取不到序号,这是它们唯一的登记通道)。

    序号解析可能回源拉 misskon 详情页(单条 1s+, 冷缓存整页几十条
    串行会超过脚本超时), 放线程池并发做; 池内不碰 DB, 判态与标题
    登记回到协程用请求级 Session 串行做(SQLAlchemy Session 非线
    程安全)。整个解析走 to_thread, 避免 fetch 的同步 IO 卡住事件循环。
    """

    def resolve(url: str) -> int | None:
        try:
            return _serial_from_url(url)
        except ValueError:
            return None

    urls = [u.strip() for u in (body.urls or []) if u.strip()][:MAX_SERIALS]
    if not urls:
        raise HTTPException(422, "urls required")

    def _resolve_all() -> list[int | None]:
        return list(_url_resolve_pool.map(resolve, urls))

    serials = await asyncio.to_thread(_resolve_all)

    items = []
    for url, serial in zip(urls, serials):
        if serial is None:
            items.append({"url": url, "serial": None, "state": "new"})
            continue
        state = state_for_serial(s, serial)
        if state == "new" and (body.titles.get(url) or "").strip():
            # 登记成功 → 本写真确认已在库(标题等价)
            if _register_serial_title(s, serial, body.titles[url]):
                state = "done"
        items.append({"url": url, "serial": serial, "state": state})
    return {"items": items}


@router.get("/ping")
async def ping(s: Session = Depends(require_key)):
    return {"ok": True, "version": __version__}
