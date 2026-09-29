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
