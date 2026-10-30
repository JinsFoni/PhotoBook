"""采集任务恢复: 启动无条件重排 + 看门狗只收「真的在跑」的任务。

背景: 2026-10-20 热补丁重启容器,#585 重启前 2 秒还在写进度,
30 分钟的停滞阈值让它躲过启动恢复 —— 明明进程都换了, 任务却一直挂着
「downloading」, 要等半小时才被看门狗捡回来。启动这一刻必然没有任务在跑,
不该套阈值(PikPak 侧同样的坑已先修, 见 test_pikpak_recovery.py)。

2026-10-30 补第二课: 看门狗原先按 ACTIVE_JOB_STATES 扫, 里面含 queued。
串行消费下一个任务要跑几分钟, 19 个排队任务等下去就是几小时, updated_at
又只在开跑那一刻写过 —— 于是每分钟整批「还在排队」的任务被判「进度停滞」
重排一次, 错误列被覆写成「进度停滞/上次运行中断, 自动重新排队」。排队是等
轮次, 不是卡死: 停滞判定只认 RUNNING_JOB_STATES。

隔离方式: 恢复函数按状态扫全表, 直接扫真实状态会把其它用例留下的活动任务
一起重置, 后台消费线程随即真的去跑它们(往 harvest_history 写行, 撞掉
test_worker 的 990002)。这里把扫描用的 RUNNING_JOB_STATES 换成专用状态值,
只扫本模块自己的行。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.db import HarvestHistory, HarvestJob
from app.services.harvest import worker as h_worker

STATUS = "recovery-test"      # 专用「运行中」状态, 见模块 docstring
SERIAL = 950001
# 真实的运行态集合(隔离 fixture 会把它换掉, 契约用例要断言原件)
REAL_RUNNING = ("parsing", "downloading", "extracting")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(h_worker, "RUNNING_JOB_STATES", (STATUS,))
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
    job = _get(job_id)
    assert job.status == "queued"
    assert "重新排队" in job.error


def test_stall_scan_excludes_queued(monkeypatch):
    """停滞判定不能把 queued 算成「进行中」—— 排队是等轮次, 不是卡死。

    2026-10-30 实录: 这批 19 个排队任务每分钟被重排一次, 错误列全被覆写成
    「进度停滞/上次运行中断, 自动重新排队」, 日志每分钟几十行; 重排时还会
    撤掉运行令牌, 消费线程刚取起来的任务终态写不进库。
    """
    monkeypatch.setattr(h_worker, "RUNNING_JOB_STATES", REAL_RUNNING)
    assert "queued" not in h_worker.RUNNING_JOB_STATES
    # 运行态必须是活动态的子集(两套常量别各说各话)
    assert set(h_worker.RUNNING_JOB_STATES) < set(h_worker.ACTIVE_JOB_STATES)
    assert "downloading" in h_worker.RUNNING_JOB_STATES


def test_watchdog_leaves_stale_queued_job_alone(monkeypatch):
    """排了两小时没轮到 = 正常排队, 看门狗不得动它(按真实扫描状态跑)。

    STALE_SECONDS 放到 1 小时: 本用例之外不会有别的用例留下「一小时前的
    下载中任务」, 所以扫全表也不会误伤别人; 而本行排了 2 小时, 正是老实现
    会判「停滞」并盖戳的那种。
    """
    monkeypatch.setattr(h_worker, "RUNNING_JOB_STATES",
                        ("parsing", "downloading", "extracting"))
    monkeypatch.setattr(h_worker, "STALE_SECONDS", 3600)
    s = SessionLocal()
    try:
        ts = datetime.now(timezone.utc) - timedelta(seconds=7200)
        j = HarvestJob(serial=SERIAL, url=f"https://x/{SERIAL}", title="排队测试",
                       status="queued", created_at=ts, updated_at=ts)
        s.add(j)
        s.commit()
        job_id = j.id
    finally:
        s.close()
    h_worker._recover_and_watchdog()
    job = _get(job_id)
    assert job.status == "queued"
    assert job.error is None        # 没被盖上「进度停滞」的戳
