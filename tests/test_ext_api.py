"""浏览器联动 API(/api/ext/*)— 推送与入库状态判定。

入库判定核心: collections.source_serial 精确匹配(合集删除即失效),
历史 done/exists 但合集不在 → 可重新下载。
"""

from __future__ import annotations

import pytest
from app.database import SessionLocal
from app.db import Collection, HarvestHistory, HarvestJob


@pytest.fixture()
def ext_key(admin_client):
    """管理员打开设置页(首次自动生成 key),返回完整 key。

    通过 reset 端点拿完整 key(响应 flash 里带新 key),而非直接读 DB —— 顺带覆盖该端点。
    """
    from app.database import SessionLocal
    from app.services import settings_store
    from app.routers import ext_api

    # 标题快照是进程级缓存(生产上 TTL 60s), 测试间必须清, 否则上个
    # 用例的合集快照会串到下个用例
    ext_api._invalidate_title_cache()
    from app.routers.ext_api import get_or_create_api_key

    s = SessionLocal()
    try:
        return get_or_create_api_key(s)
    finally:
        s.close()


def _mk_collection_with_serial(serial: int | None, slug: str):
    from app.database import SessionLocal
    from app.db import Collection

    s = SessionLocal()
    try:
        c = Collection(slug=slug, title=slug, status="published",
                       source_serial=serial)
        s.add(c)
        s.commit()
        return c.id
    finally:
        s.close()


def _rm_collection(slug: str):
    from app.database import SessionLocal
    from app.db import Collection

    s = SessionLocal()
    try:
        for c in s.query(Collection).filter(Collection.slug == slug).all():
            s.delete(c)
        s.commit()
    finally:
        s.close()


def _hist(serial: int, status: str):
    from app.database import SessionLocal
    from app.db import HarvestHistory

    s = SessionLocal()
    try:
        s.merge(HarvestHistory(serial=serial, status=status, title=f"t{serial}"))
        s.commit()
    finally:
        s.close()


def _rm_hist(serial: int):
    from app.database import SessionLocal
    from app.db import HarvestHistory

    s = SessionLocal()
    try:
        h = s.get(HarvestHistory, serial)
        if h:
            s.delete(h)
            s.commit()
    finally:
        s.close()


URL = "https://buondua.com/test-album-88-photos-b6c7eb50fddbf3f9f634f1115ce95b5e-{serial}"
H = lambda k: {"X-PhotoBook-Key": k}


# ---- 鉴权 ---------------------------------------------------------------------

def test_ping_requires_key(client):
    r = client.get("/api/ext/ping")
    assert r.status_code == 401
    r = client.get("/api/ext/ping", headers=H("wrong-key"))
    assert r.status_code == 401


def test_ping_ok(ext_key, client):
    r = client.get("/api/ext/ping", headers=H(ext_key))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "version" in r.json()


# ---- 状态判定 -------------------------------------------------------------------

def test_status_new(ext_key, client):
    r = client.get("/api/ext/status?serials=9990001", headers=H(ext_key))
    assert r.json()["items"][0]["state"] == "new"


def test_status_done_by_source_serial(ext_key, client):
    """已入库 = collections.source_serial 命中(即使历史显示 done)。"""
    _mk_collection_with_serial(9990002, "ext-done-album")
    try:
        r = client.get("/api/ext/status?serials=9990002", headers=H(ext_key))
        assert r.json()["items"][0]["state"] == "done"
    finally:
        _rm_collection("ext-done-album")


def _mk_collection_with_serials(slug: str, own: int, others: list[int]):
    """入库时那一站的序号 + 同本写真在其他站的序号。"""
    import json

    from app.database import SessionLocal
    from app.db import Collection

    s = SessionLocal()
    try:
        c = Collection(slug=slug, title=slug, status="published",
                       source_serial=own,
                       source_serials=json.dumps(others))
        s.add(c)
        s.commit()
    finally:
        s.close()


def _mk_collection_with_title(own: int, slug: str, title: str):
    """指定 title 的已入库写真(跨站标题比对测试用)。"""
    from app.database import SessionLocal
    from app.db import Collection

    s = SessionLocal()
    try:
        c = Collection(slug=slug, title=title, status="published",
                       source_serial=own, source_serials=f"[{own}]")
        s.add(c)
        s.commit()
    finally:
        s.close()


def test_status_done_by_cross_site_serial(ext_key, client):
    """同一本写真从没下过的那一站查 → 也判已入库。

    用户报的实例: 写真从 buondua(序号 56556)入库, 在 misskon
    (序号 117727)打开链接应显示「已入库」而不是「可下载」。
    """
    _mk_collection_with_serials("ext-cross-album", 56556, [117727, 496839])
    try:
        r = client.get("/api/ext/status?serials=117727,496839,56556",
                       headers=H(ext_key))
        states = {i["serial"]: i["state"] for i in r.json()["items"]}
        assert states == {117727: "done", 496839: "done", 56556: "done"}
    finally:
        _rm_collection("ext-cross-album")


def test_status_cross_site_serial_no_false_positive(ext_key, client):
    """source_serials 里的数字不能按子串误命中(1234 ≠ 21234)。"""
    _mk_collection_with_serials("ext-cross-album-2", 1234, [5678])
    try:
        r = client.get("/api/ext/status?serials=21234,56781,12345",
                       headers=H(ext_key))
        states = {i["serial"]: i["state"] for i in r.json()["items"]}
        assert all(v == "new" for v in states.values()), states
    finally:
        _rm_collection("ext-cross-album-2")


def test_status_empty_cross_site_serials(ext_key, client):
    """source_serials = [] 与 NULL 等价, 不影响 source_serial 判定。"""
    _mk_collection_with_serials("ext-cross-album-3", 777, [])
    try:
        r = client.get("/api/ext/status?serials=777,778", headers=H(ext_key))
        states = {i["serial"]: i["state"] for i in r.json()["items"]}
        assert states == {777: "done", 778: "new"}
    finally:
        _rm_collection("ext-cross-album-3")


def test_push_duplicate_by_cross_site_serial(ext_key, client):
    """跨站序号命中 → 推送直接判 duplicate, 不会重复入队下载。"""
    _mk_collection_with_serials("ext-cross-album-4", 56556, [117727])
    try:
        r = client.post("/api/ext/harvest",
                        json={"url": "https://misskon.com/117727-yeonyu-yeon-yu-blue-101-photos-6-videos/",
                              "force": True},
                        headers=H(ext_key))
        item = r.json()["items"][0]
        assert item["ok"] is False and item["state"] == "duplicate", item
    finally:
        _rm_collection("ext-cross-album-4")


def test_status_by_url_resolves_misskon_serial(ext_key, client):
    """老帖 slug 无序号 → 服务端按 URL 解析(misskon 抓 postid 前先用 URL)。"""
    _mk_collection_with_serials("ext-cross-album-5", 117727, [])
    try:
        r = client.post("/api/ext/status-by-url",
                        json={"urls": ["https://misskon.com/117727-yeonyu-yeon-yu-blue-101-photos-6-videos/",
                                       "https://buondua.com/x-y-88-photos-abc-9990777"]},
                        headers=H(ext_key))
        items = {i["url"]: i for i in r.json()["items"]}
        assert items["https://misskon.com/117727-yeonyu-yeon-yu-blue-101-photos-6-videos/"] == \
            {"url": "https://misskon.com/117727-yeonyu-yeon-yu-blue-101-photos-6-videos/",
             "serial": 117727, "state": "done"}
        # buondua URL 序号不在库 → new
        assert items["https://buondua.com/x-y-88-photos-abc-9990777"]["state"] == "new"
    finally:
        _rm_collection("ext-cross-album-5")


def test_status_by_url_requires_key(client):
    r = client.post("/api/ext/status-by-url", json={"urls": ["https://misskon.com/1-a/"]})
    assert r.status_code == 401


# ---- 状态查询 + 标题登记(POST /status) ----------------------------------------

def test_status_post_title_registers_cross_site_serial(ext_key, client):
    """同一本写真从 misskon 入库;在 buondua(序号从未进过服务端)打开,
    脚本带页面标题查询 → 服务端按标题等价比对,登记序号并返回 done。"""
    _mk_collection_with_title(119035, "ext-cross-album-6",
                              "Coser@九言 - 鸣潮 坎特蕾拉")
    try:
        r = client.post("/api/ext/status", headers=H(ext_key), json={"items": [
            {"serial": 56909, "title":
                "Coser@九言: 鸣潮 坎特蕾拉 (58 photos + 2 videos)  - ( Page 1 / 2 )"},
        ]})
        item = r.json()["items"][0]
        assert item == {"serial": 56909, "state": "done"}, item
        # 登记后纯序号查询(GET 旧入口)也命中
        r2 = client.get("/api/ext/status?serials=56909", headers=H(ext_key))
        assert r2.json()["items"][0]["state"] == "done"
    finally:
        _rm_collection("ext-cross-album-6")


def test_status_post_no_false_positive(ext_key, client):
    """不同写真的标题比对不出 → 不登记、照常返回 new。"""
    _mk_collection_with_title(119235, "ext-cross-album-7",
                              "Coser@Tokar浵卡 - 坎特蕾拉Cantarella")
    try:
        r = client.post("/api/ext/status", headers=H(ext_key), json={"items": [
            {"serial": 56909, "title":
                "Coser@九言: 鸣潮 坎特蕾拉 (58 photos + 2 videos)  -"},
        ]})
        assert r.json()["items"][0] == {"serial": 56909, "state": "new"}
    finally:
        _rm_collection("ext-cross-album-7")


def test_status_post_generic_series_count_guard(ext_key, client):
    """泛化系列标题必须被真实张数守卫拦下(44755 实录):库里 100 张那本
    「[AI Generated] 诛仙-陆雪琪」在库,上报 310 张的同名标题 → 不登记,
    照常返回 new(否则该批次永远显示已入库、不被下载)。"""
    import json as _json

    from app.database import SessionLocal
    from app.db import Collection, Photo

    s = SessionLocal()
    try:
        c = Collection(slug="ext-cross-album-11", title="[AI Generated] 诛仙-陆雪琪",
                       status="published", source_serial=47799,
                       source_serials=_json.dumps([47799]))
        s.add(c)
        s.commit()
        # 100 张那本: photos 表落 100 行 filename
        for i in range(100):
            s.add(Photo(collection_id=c.id, filename=f"ext11-{i:03d}.jpg"))
        s.commit()
        r = client.post("/api/ext/status", headers=H(ext_key), json={"items": [
            {"serial": 44755,
             "title": "[AI Generated] 诛仙-陆雪琪 (310 photos)  - ( Page 1 / 16 )"},
        ]})
        assert r.json()["items"][0] == {"serial": 44755, "state": "new"}
        # 张数相等 → 照常登记
        r2 = client.post("/api/ext/status", headers=H(ext_key), json={"items": [
            {"serial": 42981,
             "title": "[AI Generated] 诛仙-陆雪琪 (100 photos)  -"},
        ]})
        assert r2.json()["items"][0] == {"serial": 42981, "state": "done"}
    finally:
        _rm_collection("ext-cross-album-11")


def test_status_post_queued_not_rechecked(ext_key, client):
    """状态不是 new(排队中)时跳过标题比对 —— 排队任务完成后序号自会登记。"""
    _mk_collection_with_title(119035, "ext-cross-album-8",
                              "Coser@九言 - 鸣潮 坎特蕾拉")
    s = SessionLocal()
    try:
        s.add(HarvestJob(serial=56909, url="https://buondua.com/x-56909",
                         status="queued"))
        s.commit()
        r = client.post("/api/ext/status", headers=H(ext_key), json={"items": [
            {"serial": 56909, "title":
                "Coser@九言: 鸣潮 坎特蕾拉 (58 photos + 2 videos)"},
        ]})
        assert r.json()["items"][0]["state"] == "queued"
    finally:
        for j in s.query(HarvestJob).filter(HarvestJob.serial == 56909).all():
            s.delete(j)
        s.commit()
        s.close()
        _rm_collection("ext-cross-album-8")


def test_status_post_requires_key(client):
    r = client.post("/api/ext/status", json={"items": [{"serial": 1}]})
    assert r.status_code == 401


def test_status_post_requires_items(ext_key, client):
    r = client.post("/api/ext/status", json={"items": []}, headers=H(ext_key))
    assert r.status_code == 422


def test_status_by_url_requires_urls(ext_key, client):
    r = client.post("/api/ext/status-by-url", json={"urls": []}, headers=H(ext_key))
    assert r.status_code == 422


MISSKON_OLD_URL = "https://misskon.com/jp-sena-natsuki-nai-yue-senaism-79-photos/"


def _mock_misskon_postid(monkeypatch):
    """老帖序号来自页面 body 的 postid-N;测试里屏蔽真实网络。"""
    from app.services.harvest import net
    monkeypatch.setattr(net, "fetch_html",
                        lambda url, **kw:
                        '<body class="single postid-85932"></body>')


def test_status_by_url_title_registers_cross_site_serial(ext_key, client, monkeypatch):
    """老帖(无序号 URL)通道同样做标题比对:状态 new 且标题等价 → 登记 + done。

    misskon 老帖卡片本地取不到序号,status-by-url 是它唯一的登记通道;
    不带 titles 的旧请求照常只按序号判态(向后兼容由旧用例覆盖)。
    """
    _mock_misskon_postid(monkeypatch)
    _mk_collection_with_title(43940, "ext-cross-album-9",
                              "[JP] Sena Natsuki (奈月セナ) - Senaism")
    try:
        r = client.post("/api/ext/status-by-url", headers=H(ext_key),
                        json={"urls": [MISSKON_OLD_URL],
                              "titles": {MISSKON_OLD_URL:
                                         "[JP] Sena Natsuki (奈月セナ): Senaism (79 photos)"}})
        item = r.json()["items"][0]
        assert item["serial"] == 85932, item
        assert item["state"] == "done", item
        # 登记生效: 纯序号查询(GET 旧入口)也命中
        r2 = client.get("/api/ext/status?serials=85932", headers=H(ext_key))
        assert r2.json()["items"][0]["state"] == "done"
    finally:
        _rm_collection("ext-cross-album-9")


def test_status_by_url_title_no_false_positive(ext_key, client, monkeypatch):
    """老帖标题比对不上(非同一本)→ 不登记,照常返回 new。"""
    _mock_misskon_postid(monkeypatch)
    _mk_collection_with_title(43940, "ext-cross-album-10",
                              "[JP] Sena Natsuki (奈月セナ) - SILK of the MOON")
    try:
        r = client.post("/api/ext/status-by-url", headers=H(ext_key),
                        json={"urls": [MISSKON_OLD_URL],
                              "titles": {MISSKON_OLD_URL:
                                         "[JP] Sena Natsuki (奈月セナ): Senaism (79 photos)"}})
        item = r.json()["items"][0]
        assert item == {"url": MISSKON_OLD_URL, "serial": 85932, "state": "new"}, item
    finally:
        _rm_collection("ext-cross-album-10")


def test_status_deleted_collection_becomes_new(ext_key, client):
    """历史 done 但合集已删 → 可重新下载(不是已入库)。"""
    _hist(9990003, "done")
    try:
        r = client.get("/api/ext/status?serials=9990003", headers=H(ext_key))
        assert r.json()["items"][0]["state"] == "new"
    finally:
        _rm_hist(9990003)


def test_status_failed_and_skipped(ext_key, client):
    _hist(9990004, "failed")
    _hist(9990005, "skipped")
    try:
        r = client.get("/api/ext/status?serials=9990004,9990005", headers=H(ext_key))
        states = {i["serial"]: i["state"] for i in r.json()["items"]}
        assert states[9990004] == "failed"
        assert states[9990005] == "skipped"
    finally:
        _rm_hist(9990004)
        _rm_hist(9990005)


# ---- 推送 ----------------------------------------------------------------------

def test_push_enqueues_and_dedupes(ext_key, client):
    url = URL.format(serial=9990010)
    r = client.post("/api/ext/harvest", json={"url": url}, headers=H(ext_key))
    body = r.json()
    assert body["ok"] is True and body["items"][0]["ok"] is True
    assert body["items"][0]["state"] == "queued"

    # 再推 → 历史去重 → 拒绝但 state=queued
    r = client.post("/api/ext/harvest", json={"url": url}, headers=H(ext_key))
    item = r.json()["items"][0]
    assert item["ok"] is False and item["state"] == "queued"

    _cleanup_serial(9990010)


def test_push_rejects_non_buondua(ext_key, client):
    r = client.post("/api/ext/harvest",
                    json={"url": "https://example.com/x-123"},
                    headers=H(ext_key))
    item = r.json()["items"][0]
    assert item["ok"] is False and item["state"] == "rejected"


def test_push_accepts_misskon(ext_key, client):
    """misskon URL 也走同一推送入口(序号体系独立,取 slug 前缀)。"""
    url = "https://misskon.com/994020-misskon-ext-test-photos/"
    try:
        r = client.post("/api/ext/harvest", json={"url": url}, headers=H(ext_key))
        item = r.json()["items"][0]
        assert item["ok"] is True and item["serial"] == 994020
    finally:
        _cleanup_serial(994020)


def test_push_force_requeues_failed(ext_key, client):
    _hist(9990011, "failed")
    url = URL.format(serial=9990011)
    # 不带 force → 拒绝
    r = client.post("/api/ext/harvest", json={"url": url}, headers=H(ext_key))
    item = r.json()["items"][0]
    assert item["ok"] is False and item["state"] == "failed"
    # 带 force → 重新入队
    r = client.post("/api/ext/harvest", json={"url": url, "force": True},
                    headers=H(ext_key))
    assert r.json()["items"][0]["ok"] is True
    _cleanup_serial(9990011)


def test_push_force_rejects_done(ext_key, client):
    """已入库(done)即使 force 也不重推 —— 防误操作重复下载。"""
    _hist(9990012, "done")
    _mk_collection_with_serial(9990012, "ext-done-album-12")
    try:
        r = client.post("/api/ext/harvest",
                        json={"url": URL.format(serial=9990012), "force": True},
                        headers=H(ext_key))
        item = r.json()["items"][0]
        assert item["ok"] is False and item["state"] == "duplicate"
    finally:
        _rm_collection("ext-done-album-12")
        _rm_hist(9990012)


def test_push_requeues_deleted_collection(ext_key, client):
    """历史 done 但合集已删 → 推送清历史行直接重入队(无需 force)。"""
    _hist(9990013, "done")
    r = client.post("/api/ext/harvest",
                    json={"url": URL.format(serial=9990013)},
                    headers=H(ext_key))
    item = r.json()["items"][0]
    assert item["ok"] is True, item
    _cleanup_serial(9990013)


def test_push_batch(ext_key, client):
    _hist(9990014, "failed")
    r = client.post("/api/ext/harvest",
                    json={"urls": [URL.format(serial=9990014),
                                   URL.format(serial=9990015)],
                          "force": True},
                    headers=H(ext_key))
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["ok"] is True    # failed + force → 重入队
    assert items[1]["ok"] is True    # 新 → 入队
    _cleanup_serial(9990014)
    _cleanup_serial(9990015)


# ---- 设置页 ---------------------------------------------------------------------

def test_settings_page_shows_ext_block(admin_client):
    r = admin_client.get("/admin/settings")
    assert r.status_code == 200
    assert "buondua-bridge.user.js" in r.text


def _cleanup_serial(serial: int):
    from app.database import SessionLocal
    from app.db import HarvestHistory, HarvestJob

    s = SessionLocal()
    try:
        h = s.get(HarvestHistory, serial)
        if h:
            s.delete(h)
        for j in s.query(HarvestJob).filter(HarvestJob.serial == serial).all():
            s.delete(j)
        s.commit()
    finally:
        s.close()
