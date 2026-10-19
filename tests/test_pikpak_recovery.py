"""PikPak 恢复逻辑: 启动无条件重排 + 续跑不被半成品目录误跳过。

背景: 容器重启时 P20 只更新过 1 分钟, 30 分钟停滞阈值让它躲过启动恢复;
即便被看门狗重置, 目录里的半成品又会让 _skip_if_imported 判「已存在」,
剩下 200+ 文件永远不下载。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.db import PikPakJob
from app.services.pikpak import worker as pk_worker


PREFIX = "pkrecover-"


def _cleanup():
    s = SessionLocal()
    try:
        s.execute(delete(PikPakJob).where(PikPakJob.file_id.like(f"{PREFIX}%")))
        s.commit()
    finally:
        s.close()


@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()


def _job() -> int:
    """一个刚更新过的活动任务 —— 看门狗会认为它「健康」。"""
    s = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        j = PikPakJob(batch_id="recover-test", name="恢复测试",
                      file_id=f"{PREFIX}job", status="downloading",
                      started_at=now, updated_at=now)
        s.add(j)
        s.commit()
        return j.id
    finally:
        s.close()


def _get(job_id: int) -> PikPakJob:
    s = SessionLocal()
    try:
        return s.get(PikPakJob, job_id)
    finally:
        s.close()


def test_startup_requeues_active_job_even_if_fresh(clean):
    job_id = _job()
    pk_worker._recover_and_watchdog(at_startup=True)

    job = _get(job_id)
    assert job.status == "queued"
    # started_at 保留: 重跑时据此判定 resumed, 继续下载而不是跳过
    assert job.started_at is not None


def test_watchdog_keeps_fresh_job_running(clean):
    job_id = _job()
    pk_worker._recover_and_watchdog()
    assert _get(job_id).status == "downloading"


def test_resume_does_not_skip_partial_album(clean, tmp_path, monkeypatch):
    job_id = _job()
    album = tmp_path / "album"
    album.mkdir()
    (album / "001.jpg").write_bytes(b"partial")
    monkeypatch.setattr(pk_worker.library_import, "collection_exists",
                        lambda *a, **k: False)

    s = SessionLocal()
    try:
        job = s.get(PikPakJob, job_id)
        # 首次推送撞上已有目录: 保持原语义, 整包跳过
        assert pk_worker._skip_if_imported(s, job, album) == "→ 已存在,跳过"
        # 中断续跑: 半成品目录必须继续下载
        assert pk_worker._skip_if_imported(s, job, album, resumed=True) is None
    finally:
        s.close()
