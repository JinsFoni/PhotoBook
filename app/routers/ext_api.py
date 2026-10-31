"""浏览器联动 API(/api/ext/*)— 供油猴脚本推送下载与查询入库状态。

鉴权: X-PhotoBook-Key 请求头, 与 settings 表 ext.api_key 比对(常量时间)。
不走路由/会话鉴权; GM_xmlhttpRequest 不受 CORS 限制, 服务端无需 CORS 头。
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import __version__
from ..database import get_db
from ..db import Collection, HarvestHistory, HarvestJob, Photo
from ..i18n import t
from ..services import settings_store
from ..services.harvest import net
from ..services.harvest.titlematch import (PreparedTitle, prepare_title,
                                           title_matches_collection)
from ..services.harvest.worker import enqueue, ACTIVE_JOB_STATES
from ..services.pikpak import worker as pikpak_worker

router = APIRouter(prefix="/api/ext")
log = logging.getLogger("photobook.ext")

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
    """单个序号 → 联动状态(批量版 states_for_serials 的单条门面, 判态规则同源)。"""
    return states_for_serials(s, [serial])[serial]


def states_for_serials(s: Session, serials: list[int]) -> dict[int, str]:
    """批量判态 — 一页卡片一条 SQL 序列问完, 判态规则与 state_for_serial 一致。

    脚本只认这几个词:
    new      无任何记录, 可下载
    queued   任务排队/进行中
    done     已入库(collections 存在, 含 done/exists 历史)
    failed   上次失败, 可重推
    skipped  被黑白名单过滤, 可重推

    逐条版每个序号要 3~4 条 SQL(活跃任务 / source_serial / source_serials
    JSON 粗筛 / 历史行), 一页 24 张就是 70+ 次扫表, 实测 35ms; 而这条
    路径是油猴脚本每 5s 一次的常驻轮询, 徽标要等它算完才画得出来
    (2026-10-29「角标隔一会儿才显示」)。这里把三类记录各用一条批量
    SQL 取回, 再在内存里按同一优先级 queued → done → 历史 定态。
    """
    uniq = list(dict.fromkeys(serials))
    out = {n: "new" for n in uniq}
    if not uniq:
        return out

    for (n,) in s.execute(
            select(HarvestJob.serial).where(
                HarvestJob.serial.in_(uniq),
                HarvestJob.status.in_(ACTIVE_JOB_STATES)).distinct()):
        if n in out:
            out[n] = "queued"

    # 在库: 本站序号精确匹配
    pending = [n for n in uniq if out[n] == "new"]
    if pending:
        for (n,) in s.execute(
                select(Collection.source_serial).where(
                    Collection.source_serial.in_(pending)).distinct()):
            if n in out:
                out[n] = "done"

    # 在库: 跨站序号藏在 source_serials(JSON 数组文本)里。LIKE 只当粗筛
    # (按数值子串, 会命中 21234 里的 1234 之类), 命中后必须解析 JSON 确认;
    # 全部 miss 时用一个 or_ 合成单条 SQL, 不再逐序号扫表。
    miss = [n for n in uniq if out[n] == "new"]
    if miss:
        rows = s.execute(
            select(Collection.source_serials).where(or_(
                *[Collection.source_serials.like(f"%{n}%") for n in miss]))).all()
        if rows:
            want = set(miss)
            for (raw,) in rows:
                try:
                    got = want.intersection(json.loads(raw or "[]"))
                except (ValueError, TypeError):
                    continue
                for n in got:
                    out[n] = "done"

    # 历史行: 处理过但写真已删(done/exists) → 视为可重新下载
    rest = [n for n in uniq if out[n] == "new"]
    if rest:
        for serial, status in s.execute(
                select(HarvestHistory.serial, HarvestHistory.status).where(
                    HarvestHistory.serial.in_(rest))).all():
            if serial in out and status in ("failed", "skipped"):
                out[serial] = status
    return out


# ---- 端点 --------------------------------------------------------------------

class PushBody(BaseModel):
    url: str | None = None
    urls: list[str] | None = None
    force: bool = False


SUPPORTED_HOSTS = ("buondua.com", net.NICESSS_HOST, net.MISSKON_HOST,
                   net.FOURKUP_HOST)


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
def push_harvest(body: PushBody, s: Session = Depends(require_key)):
    urls = list(body.urls or ([] if not body.url else [body.url]))
    if not urls:
        raise HTTPException(422, "url or urls required")
    if len(urls) > MAX_SERIALS:
        raise HTTPException(422, f"too many urls (max {MAX_SERIALS})")
    items = [_push_one(s, u.strip(), body.force) for u in urls if u.strip()]
    ok = all(i["ok"] for i in items)
    return {"ok": ok, "items": items}


def _revoke_stale_registration(s: Session, serial: int, title: str) -> bool:
    """上报标题与登记所在合集标题毫无交集 → 撤销该跨站登记(撤销过返回 True)。

    source_serials 只在「上报标题与合集标题等价」时写入(_register_serial_title),
    但写进去的是**当时**那个标题。若后来同一序号上报的标题与该合集标题连一个
    token 都不共有, 说明当初那笔登记本身就是错的 —— 脚本把某张卡片的标题配到了
    另一张卡片的序号上(15445 实录: 4kup 的「LEEHEE EXPRESS LEBE-011 GMS」被
    登记进「MiStar Vol.265 Mu Fei Fei (穆菲菲)」那本, 于是用户在 4kup 上看到
    LEBE-011「已入库」, 库里却没有, 点下载也没反应)。

    只撤销「零交集」这一种:跨站转载的标题写法差异(站点尾缀/冒号连字符/
    张数尾缀)都过不了 token 化 —— 真同一本写真必定共有模特名或番号 token,
    所以这条判据不会误伤(反过来重名系列的不同批次本来就不会共 token)。

    collections.source_serial(自家序号)永远不动 —— 那是「本服务确实按这个
    序号采过」的铁证, 与跨站登记无关。
    """
    prep = prepare_title(title)
    toks = set(prep[0])
    # 无信号:标题太短/取不出 token 时不做任何判断(交回原状态)
    if len(prep[0]) < 2 or max(len(x) for x in prep[0]) < 6:
        return False

    revoked = False
    for cid, col_title, col_serial, raw in s.execute(
            select(Collection.id, Collection.title, Collection.source_serial,
                   Collection.source_serials).where(or_(
                       Collection.source_serials.like(f"%{serial},%"),
                       Collection.source_serials.like(f"%{serial}]%"),
                       Collection.source_serials.like(f"%[{serial}%")))).all():
        if col_serial == serial:
            continue          # 自家序号, 不走跨站登记判据
        try:
            known = json.loads(raw or "[]")
        except (ValueError, TypeError):
            continue
        if serial not in known:
            continue
        if toks & set(prepare_title(col_title)[0]):
            continue          # 有共 token → 是同一本的跨站写法差异, 保留
        known = [n for n in known if n != serial]
        col = s.get(Collection, cid)
        col.source_serials = json.dumps(sorted(known))
        s.commit()
        log.warning("revoke stale cross-site serial %s from #%s %r "
                    "(reported title %r shares no token)",
                    serial, cid, col_title, title)
        revoked = True
    if revoked:
        _invalidate_title_cache()   # 快照里的 source_serials 已过期
    return revoked


def _register_serial_title(s: Session, serial: int, title: str,
                           title_prep: PreparedTitle | None = None) -> bool:
    """按标题等价比对,把 serial 登记进命中的 collection.source_serials。

    同一本写真三站序号各自独立,序号只在「本站采集过」时才进得了
    source_serials;用户在另一站浏览时该站序号服务端无从知晓 —— 脚本
    查状态时把页面标题带上,这里比对命中即登记(状态查询顺带成了登记
    通道)。已登记(序号已在)返回 False,避免每 5s 轮询重复写库。

    性能: 全量候选快照缓存在进程内(TTL 60s), 避免每个未知标题都全表
    加载合集 ORM(连带 photos 时代实测单标题 0.4s, 一页 24 卡就是 10s)。
    快照带各合集的真实照片数(GROUP BY 一条)—— 入库 title 不带
    「(N photos)」尾缀, 标题等价必须以真实张数守卫, 否则泛化系列标题
    ([AI Generated] 诛仙-陆雪琪)的不同批次全会误登记(44755 实录)。

    2026-10-29 二次加速(徽标要 1s 才出来的根因): 快照里预编译好每个
    合集的标题 tokens, 并建 token→候选 的倒排索引。以前每个上报标题都
    把 835 本重算一遍 tokens(8ms)+子序列比对, 一页 24~48 张卡片就是
    0.5~1.3s, 徽标只能等这一串算完才画得出来。子序列匹配要求「短的一
    方的全部 token 都出现在长的一方」, 所以真命中必然与上报标题至少
    共用一个 token —— 按倒排取候选是等价剪枝, 不是近似。
    """
    import json as _json

    if not (title or "").strip():
        return False
    prep = title_prep or prepare_title(title)
    # 上报标题不足 2 个 token 时, 两侧谁当「短的一方」都过不了辨识度门槛
    if len(prep[0]) < 2:
        return False

    snapshot, index = _title_snapshot(s)

    # 候选 = 与上报标题共享任一 token 的合集(命中者必在其中)
    cand: set[int] = set()
    for tok in prep[0]:
        hit = index.get(tok)
        if hit:
            cand.update(hit)
    if not cand:
        return False

    def _load(json_raw: str | None) -> list:
        try:
            return _json.loads(json_raw or "[]")
        except (ValueError, TypeError):
            return []

    for i in sorted(cand):
        cid, col_title, col_serial, raw_serials, col_photos, col_prep = snapshot[i]
        if not title_matches_collection(title, col_title, col_photos,
                                        title_prep=prep, col_prep=col_prep):
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
        # 就地更新快照里这条的 source_serials: 只改序号、不动 tokens/张数,
        # 所以不必整表重建(重建要 GROUP BY 8 万行 photos 再编译 835 个标题,
        # 一页连中几本就会连着重build几次)。下个标题再比到时直接判「已登记」。
        with _title_cache_lock:
            if _title_cache_data is not None and _title_cache_data[i][0] == cid:
                _title_cache_data[i] = (cid, col_title, col_serial,
                                        col.source_serials, col_photos, col_prep)
        return True
    return False


_title_cache_data: list | None = None
_title_cache_index: dict[str, list[int]] | None = None
_title_cache_at: float = 0.0
_title_cache_lock = threading.Lock()


def _title_snapshot(s: Session) -> tuple[list, dict[str, list[int]]]:
    """进程内候选快照(TTL 60s): [(id, title, serial, serials, 张数, prep)] + 倒排索引。"""
    global _title_cache_data, _title_cache_index, _title_cache_at
    now = time.monotonic()
    with _title_cache_lock:
        if now - _title_cache_at > 60 or _title_cache_data is None:
            counts = dict(s.execute(
                select(Photo.collection_id, func.count(Photo.id))
                .group_by(Photo.collection_id)).all())
            data = []
            index: dict[str, list[int]] = {}
            for cid, col_title, col_serial, raw_serials in s.execute(
                    select(Collection.id, Collection.title,
                           Collection.source_serial, Collection.source_serials)
                    .where(Collection.source_serial.is_not(None))).all():
                col_prep = prepare_title(col_title)
                for tok in col_prep[0]:
                    bucket = index.get(tok)
                    if bucket is None:
                        index[tok] = [len(data)]
                    else:
                        bucket.append(len(data))
                data.append((cid, col_title, col_serial, raw_serials,
                             counts.get(cid), col_prep))
            _title_cache_data = data
            _title_cache_index = index
            _title_cache_at = now
        return _title_cache_data, _title_cache_index or {}


def _invalidate_title_cache() -> None:
    global _title_cache_data, _title_cache_index, _title_cache_at
    with _title_cache_lock:
        _title_cache_data = None
        _title_cache_index = None
        _title_cache_at = 0.0


@router.get("/status")
def status_api(serials: str, s: Session = Depends(require_key)):
    """批量查询入库状态。serials=逗号分隔的源站序号。

    旧入口(不带标题): 只按序号判态。新脚本走 POST /status。
    """
    try:
        ids = [int(x) for x in serials.split(",") if x.strip()][:MAX_SERIALS]
    except ValueError:
        raise HTTPException(422, "serials must be integers")
    if not ids:
        raise HTTPException(422, "serials required")
    states = states_for_serials(s, ids)
    return {"items": [{"serial": i, "state": states[i]} for i in ids]}


class StatusItem(BaseModel):
    serial: int
    title: str = ""


class StatusBody(BaseModel):
    items: list[StatusItem]


@router.post("/status")
def status_api_v2(body: StatusBody, s: Session = Depends(require_key)):
    """批量查询入库状态 + 标题登记。

    items 每项 = (序号, 页面标题)。序号命中即返回状态;未命中但标题与
    已入库写真等价 → 登记进该写真的 source_serials 并返回 done(下次
    查询序号直接命中,不再做比对)。标题可比对不出(未入库/非同本)按
    普通判态返回。反过来:标题与该序号登记所在合集毫无交集 → 判为当初
    登记串了台, 撤销登记并按 new 返回(_revoke_stale_registration)。
    """
    items = body.items[:MAX_SERIALS]
    if not items:
        raise HTTPException(422, "items required")
    states = states_for_serials(s, [it.serial for it in items])
    out = []
    for it in items:
        state = states[it.serial]
        if state == "done" and it.title.strip():
            # 跨站登记自查: 上报标题与合集标题连一个 token 都不共有 → 撤销
            if _revoke_stale_registration(s, it.serial, it.title):
                state = states_for_serials(s, [it.serial])[it.serial]
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
def push_pikpak(body: PikPakPushBody, s: Session = Depends(require_key)):
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
def status_by_url(body: StatusByUrlBody, s: Session = Depends(require_key)):
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
    登记回到本线程用请求级 Session 串行做(SQLAlchemy Session 非线
    程安全)。

    端点是同步 def(FastAPI 丢线程池执行): 判态/标题比对是同步 sqlite
    活, 一页 24~48 条最坏上百毫秒, 写成 async 会直接卡住整个事件循环
    (常驻轮询每 5s 一次, 前台页面与采集 worker 都会被拖慢)。
    """

    def resolve(url: str) -> int | None:
        try:
            return _serial_from_url(url)
        except ValueError:
            return None
        except Exception:
            # 回源拉详情页失败(源站限流 403/超时): 不让单条坏 URL 打翻
            # 整批, 按「解析不出序号」同路回 new, 脚本下次轮询再重试
            return None

    urls = [u.strip() for u in (body.urls or []) if u.strip()][:MAX_SERIALS]
    if not urls:
        raise HTTPException(422, "urls required")

    def _resolve_all() -> list[int | None]:
        return list(_url_resolve_pool.map(resolve, urls))

    serials = _resolve_all()   # 同步端点已在线程池线程里, 直接阻塞即可

    states = states_for_serials(s, [x for x in serials if x is not None])
    items = []
    for url, serial in zip(urls, serials):
        if serial is None:
            items.append({"url": url, "serial": None, "state": "new"})
            continue
        state = states[serial]
        title = (body.titles.get(url) or "").strip()
        if state == "done" and title:
            # 跨站登记自查(与 /status v2 同源): 标题零交集 → 撤销登记
            if _revoke_stale_registration(s, serial, title):
                state = states_for_serials(s, [serial])[serial]
        if state == "new" and title:
            # 登记成功 → 本写真确认已在库(标题等价)
            if _register_serial_title(s, serial, title):
                state = "done"
        items.append({"url": url, "serial": serial, "state": state})
    return {"items": items}


@router.get("/ping")
async def ping(s: Session = Depends(require_key)):
    return {"ok": True, "version": __version__}
