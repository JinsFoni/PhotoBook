"""采集任务队列 — 分页与状态筛选(SSR 页面 + 轮询 API)。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session as OrmSession  # noqa: F401

from app.database import SessionLocal
from app.db import HarvestJob

# 994xxx 段独立序号,避免与其它测试文件冲突(参照 test_harvest_delete.py 惯例)
SERIALS = list(range(994001, 994046))  # 45 条 done
FAILED_SERIAL = 994090
CLEANUP_SERIALS = list(range(994001, 994101))


def _cleanup():
    from sqlalchemy import delete
    s = SessionLocal()
    try:
        s.execute(delete(HarvestJob).where(HarvestJob.serial.in_(CLEANUP_SERIALS)))
        s.commit()
    finally:
        s.close()


def _job(serial: int, status: str = "done") -> HarvestJob:
    s = SessionLocal()
    try:
        j = HarvestJob(serial=serial, url=f"https://www.buondua.com/x-{serial}-photos-z",
                       status=status)
        s.add(j)
        s.commit()
        return j
    finally:
        s.close()


@pytest.fixture()
def jobs45():
    """45 条 done 任务 → 每页 20 条共 3 页;外加 1 条 failed(筛选用)。"""
    _cleanup()
    ids = [_job(n, "done").id for n in SERIALS]
    failed_id = _job(FAILED_SERIAL, "failed").id
    yield {"done_ids": ids, "failed_id": failed_id}
    _cleanup()


def test_jobs_paginated_20_per_page(admin_client, jobs45):
    """默认第一页 20 条,按 id 倒序(最新在前)。"""
    page = admin_client.get("/admin/harvest").text
    assert "第 1 / 3 页" in page
    assert "共 46 条" in page  # 45 done + 1 failed
    # 第一页应为 id 最大的 20 条 done(994045…994026),不含 failed
    from app.db import HarvestJob as J
    s = SessionLocal()
    try:
        top20 = [str(j.id) for j in s.query(J).order_by(J.id.desc()).limit(20).all()]
    finally:
        s.close()
    for jid in top20:
        assert f'data-job-row="{jid}"' in page


def test_jobs_second_page(admin_client, jobs45):
    page = admin_client.get("/admin/harvest?page=2").text
    assert "第 2 / 3 页" in page
    s = SessionLocal()
    try:
        from app.db import HarvestJob as J
        rows = s.query(J).order_by(J.id.desc()).offset(20).limit(20).all()
    finally:
        s.close()
    for j in rows:
        assert f'data-job-row="{j.id}"' in page


def test_jobs_page_out_of_range_clamped(admin_client, jobs45):
    page = admin_client.get("/admin/harvest?page=99").text
    assert "第 3 / 3 页" in page
    page = admin_client.get("/admin/harvest?page=0").text
    assert "第 1 / 3 页" in page


def test_jobs_status_filter_failed(admin_client, jobs45):
    page = admin_client.get("/admin/harvest?status=failed").text
    assert "共 1 条" in page
    assert f'data-job-row="{jobs45["failed_id"]}"' in page
    # done 任务不应出现在 failed 筛选里
    assert f'data-job-row="{jobs45["done_ids"][0]}"' not in page


def test_jobs_status_filter_done_excludes_failed(admin_client, jobs45):
    page = admin_client.get("/admin/harvest?status=done").text
    assert "共 45 条" in page
    assert f'data-job-row="{jobs45["failed_id"]}"' not in page


def test_jobs_api_paginated(admin_client, jobs45):
    r = admin_client.get("/admin/api/harvest/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["totalPages"] == 3
    assert body["total"] == 46
    assert len(body["jobs"]) == 20

    r = admin_client.get("/admin/api/harvest/jobs?page=3")
    body = r.json()
    assert body["page"] == 3
    assert len(body["jobs"]) == 46 - 40  # 6 条

    # 越界页码收敛到最后一页
    r = admin_client.get("/admin/api/harvest/jobs?page=99")
    body = r.json()
    assert body["page"] == 3


def test_jobs_api_status_filter(admin_client, jobs45):
    r = admin_client.get("/admin/api/harvest/jobs?status=failed")
    body = r.json()
    assert body["total"] == 1
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["status"] == "failed"

    # 非法 status 回退为全部
    r = admin_client.get("/admin/api/harvest/jobs?status=whatever")
    assert r.json()["total"] == 46


def test_filter_chips_have_counts(admin_client, jobs45):
    page = admin_client.get("/admin/harvest").text
    assert "全部" in page and "进行中" in page and "已完成" in page
    assert "已跳过" in page and "失败" in page


def test_delete_keeps_page_via_back(admin_client, jobs45):
    """删除时带 back 参数:操作后留在原筛选原页(且不能变成开放重定向)。"""
    from app.db import HarvestJob as J
    last_done = jobs45["done_ids"][-1]  # id 最小的 done,在第 3 页
    r = admin_client.post(
        f"/admin/harvest/{last_done}/delete",
        data={"back": "?status=done&page=3"},
        follow_redirects=False)
    assert r.status_code == 303
    # 回到原筛选原页,并带上删除成功 flash(quote 后的「任务已删除」)
    assert r.headers["location"].startswith("/admin/harvest?status=done&page=3&flash=")
    from urllib.parse import quote
    from app.i18n import t as _t
    assert quote(_t("任务已删除")) in r.headers["location"]
    s = SessionLocal()
    try:
        assert s.get(J, last_done) is None
    finally:
        s.close()


def test_delete_back_param_sanitized(admin_client, jobs45):
    """back 只接受白名单形态,其它值丢弃(防开放重定向)。"""
    from app.db import HarvestJob as J
    target = jobs45["done_ids"][0]
    r = admin_client.post(
        f"/admin/harvest/{target}/delete",
        data={"back": "https://evil.example.com/x"},
        follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/harvest")


def test_empty_filter_shows_placeholder(admin_client, jobs45):
    """有筛选但该状态无任务:显示状态占位而非「队列为空」。"""
    page = admin_client.get("/admin/harvest?status=active").text
    assert "该状态下没有任务" in page
    # 「队列为空」只允许出现在内联 JS 回退字符串里,不得作为 SSR 空态单元格渲染
    assert ">队列为空" not in page


def test_pager_disabled_on_first_and_last_page(admin_client, jobs45):
    """边界页:上一页/下一页带 aria-disabled 且 href 钳制,不会指向 page=0 或越界页。"""
    import re

    first = admin_client.get("/admin/harvest").text
    prev = re.search(r'<a class="btn btn--quiet btn--sm pager__prev"[^>]*>', first).group(0)
    nxt = re.search(r'<a class="btn btn--quiet btn--sm pager__next"[^>]*>', first).group(0)
    # 第一页:上一页禁用 + href 钳到 page=1(而非 page=0)
    assert 'aria-disabled="true"' in prev
    assert "page=1" in prev
    assert "page=0" not in prev
    # 第一页:下一页可用且指向 page=2
    assert 'aria-disabled="true"' not in nxt
    assert "page=2" in nxt

    last = admin_client.get("/admin/harvest?page=3").text
    prev = re.search(r'<a class="btn btn--quiet btn--sm pager__prev"[^>]*>', last).group(0)
    nxt = re.search(r'<a class="btn btn--quiet btn--sm pager__next"[^>]*>', last).group(0)
    # 最后一页:下一页禁用 + href 钳到最后一页(而非 page=4)
    assert 'aria-disabled="true"' in nxt
    assert "page=3" in nxt
    assert "page=4" not in nxt
    # 最后一页:上一页可用
    assert 'aria-disabled="true"' not in prev


# ---- 缩略图状态文案实时化 ----

def _make_processing_collection(slug: str, title: str):
    from app.db import Collection, Model
    s = SessionLocal()
    try:
        m = s.query(Model).filter(Model.name == "tester").first()
        if not m:
            m = Model(name="tester", slug="tester")
            s.add(m)
            s.flush()
        c = Collection(slug=slug, title=title, model_id=m.id,
                       published_at="2026.09.29", status="processing")
        s.add(c)
        s.commit()
        return c.id
    finally:
        s.close()


def test_thumb_generating_stays_while_processing(admin_client, jobs45):
    """collection 仍 processing 时,任务文案保持「缩略图生成中」。"""
    from app.db import HarvestJob
    _make_processing_collection("tester-some-album", "some album")
    s = SessionLocal()
    try:
        j = _job(994050, "done")
        j.collection_slug = "tester-some-album"
        j.error = "→ 10 张已入库,缩略图生成中#1"
        s.merge(j); s.commit()
    finally:
        s.close()
    page = admin_client.get("/admin/harvest").text
    assert "缩略图生成中#1" in page


def test_thumb_generating_becomes_done_after_publish(admin_client, jobs45):
    """collection 翻转 published 后,文案实时变为「已完成」(DB 里不回写)。"""
    from app.db import Collection, HarvestJob
    _make_processing_collection("tester-album-two", "album two")
    s = SessionLocal()
    try:
        j = _job(994051, "done")
        j.collection_slug = "tester-album-two"
        j.error = "→ 10 张已入库,缩略图生成中#1"
        s.merge(j); s.commit()
        # 队列完成 → published
        c = s.query(Collection).filter(Collection.slug == "tester-album-two").one()
        c.status = "published"
        s.commit()
        # DB 里的 error 未被回写,仍是旧文案
        raw = s.get(HarvestJob, j.id).error
        assert "缩略图生成中" in raw
    finally:
        s.close()
    page = admin_client.get("/admin/harvest").text
    assert "→ 10 张已入库,已完成" in page
    assert "缩略图生成中" not in page
    # 轮询 API 同样实时
    import json as _json
    api = _json.loads(admin_client.get("/admin/api/harvest/jobs").text)
    err = [x["error"] for x in api["jobs"] if x["id"] == j.id][0]
    assert err == "→ 10 张已入库,已完成"
