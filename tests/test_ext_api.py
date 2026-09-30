"""浏览器联动 API(/api/ext/*)— 推送与入库状态判定。

入库判定核心: collections.source_serial 精确匹配(合集删除即失效),
历史 done/exists 但合集不在 → 可重新下载。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def ext_key(admin_client):
    """管理员打开设置页(首次自动生成 key),返回完整 key。

    通过 reset 端点拿完整 key(响应 flash 里带新 key),而非直接读 DB —— 顺带覆盖该端点。
    """
    from app.database import SessionLocal
    from app.services import settings_store
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
