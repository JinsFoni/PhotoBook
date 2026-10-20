"""采集任务恢复: 启动无条件重排 + 看门狗只收停滞的。

背景: 2026-10-20 热补丁重启容器,#585 重启前 2 秒还在写进度,
30 分钟的停滞阈值让它躲过启动恢复 —— 明明进程都换了, 任务却一直挂着
「downloading」, 要等半小时才被看门狗捡回来。启动这一刻必然没有任务在跑,
不该套阈值(PikPak 侧同样的坑已先修, 见 test_pikpak_recovery.py)。

隔离方式: 恢复函数按 ACTIVE_JOB_STATES 扫全表, 直接用它会把其它用例留下的
活动任务一起重置, 后台消费线程随即真的去跑它们(往 harvest_history 写行,
撞掉 test_worker 的 990002)。这里把 ACTIVE_JOB_STATES 换成专用状态值,
只扫本模块自己的行。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.db import HarvestHistory, HarvestJob
from app.services.harvest import worker as h_worker

STATUS = "recovery-test"      # 专用「活动」状态, 见模块 docstring
SERIAL = 950001


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(h_worker, "ACTIVE_JOB_STATES", (STATUS,))
    _cleanup()
    yield
    _cleanup()


def _cleanup() -> None:
    s = SessionLocal()
    try:
        s.execute(delete(HarvestJob).where(HarvestJob.serial == SERIAL))
        s.execute(delete(HarvestHistory).where(HarvestHistory.serial == SERIAL))
        s.commit()
    finally:
        s.close()


def _job(age_seconds: int = 0) -> int:
    """一个「刚更新过」的活动任务 —— 默认会被看门狗判为健康。"""
    s = SessionLocal()
    try:
        ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        j = HarvestJob(serial=SERIAL, url=f"https://x/{SERIAL}", title="恢复测试",
                       status=STATUS, started_at=ts, updated_at=ts)
        s.add(j)
        s.commit()
        return j.id
    finally:
        s.close()


def _get(job_id: int) -> HarvestJob:
    s = SessionLocal()
    try:
        return s.get(HarvestJob, job_id)
    finally:
        s.close()


def test_startup_requeues_active_job_even_if_fresh():
    job_id = _job()
    h_worker._recover_and_watchdog(at_startup=True)

    job = _get(job_id)
    assert job.status == "queued"
    # started_at 保留: 重跑时据此判定 resumed, 继续下载而不是跳过
    assert job.started_at is not None
    assert "重新排队" in job.error


def test_watchdog_keeps_fresh_job_running():
    job_id = _job()
    h_worker._recover_and_watchdog()
    assert _get(job_id).status == STATUS


def test_watchdog_resets_stale_job(monkeypatch):
    monkeypatch.setattr(h_worker, "STALE_SECONDS", 60)
    job_id = _job(age_seconds=600)
    h_worker._recover_and_watchdog()
    assert _get(job_id).status == "queued"
