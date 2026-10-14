"""PikPak 并发下载 — 4 路同时跑、进度并发安全、token 撤销即停。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.db import PikPakFile, PikPakJob
from app.services.pikpak import worker as pk_worker


FILE_ID_PREFIX = "pkconc-"


def _cleanup():
    s = SessionLocal()
    try:
        s.execute(delete(PikPakFile).where(PikPakFile.file_id.like(f"{FILE_ID_PREFIX}%")))
        s.execute(delete(PikPakJob).where(PikPakJob.file_id.like(f"{FILE_ID_PREFIX}%")))
        s.commit()
    finally:
        s.close()


def _job(n_files: int) -> tuple[int, Path]:
    """建任务 + n_files 个待下载文件, 返回 (job_id, album_dir)。"""
    s = SessionLocal()
    try:
        j = PikPakJob(batch_id="conc-test", name="并发测试", file_id=f"{FILE_ID_PREFIX}job",
                      status="downloading", files_total=n_files)
        s.add(j)
        s.flush()
        for i in range(n_files):
            s.add(PikPakFile(job_id=j.id, file_id=f"{FILE_ID_PREFIX}{i}",
                             url=f"https://dl/{i}.jpg", rel=f"{i}.jpg", size=1024))
        s.commit()
        album = Path(settings.library_dir) / "_conc_test_album"
        return j.id, album
    finally:
        s.close()


@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()


def test_download_files_runs_concurrently(clean, monkeypatch):
    """4 路并发: 最多同时 4 个下载在飞; 全部完成后 files_done/bytes 正确。"""
    import shutil
    shutil.rmtree(Path(settings.library_dir) / "_conc_test_album", ignore_errors=True)
    job_id, album_dir = _job(12)
    token = "tok-conc-1"
    pk_worker._run_tokens[job_id] = token

    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def fake_download(url, dest, *, max_bytes=0, on_progress=None, stream_key=None):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.15)   # 模拟网络耗时, 给并发窗口留重叠
        with lock:
            active["n"] -= 1
        Path(dest).write_bytes(b"x" * 1024)
        if on_progress:
            on_progress(1024, 1024)

    from app.services.harvest import pipeline
    monkeypatch.setattr(pipeline, "download_stream", fake_download)

    s = SessionLocal()
    try:
        job = s.get(PikPakJob, job_id)
        files = s.query(PikPakFile).where(PikPakFile.job_id == job_id).all()
        pk_worker._download_files(s, job, files, album_dir, token)
    finally:
        pk_worker._run_tokens.pop(job_id, None)
        s.close()

    # 线程调度抖动可能让瞬时重叠少 1, 但绝不应退化到串行(=1)
    assert active["max"] >= pk_worker.DOWNLOAD_CONCURRENCY - 1, \
        f"expected ~{pk_worker.DOWNLOAD_CONCURRENCY} concurrent downloads, got {active['max']}"

    s = SessionLocal()
    try:
        j = s.get(PikPakJob, job_id)
        assert j.files_done == 12
        assert j.bytes_done == 12 * 1024
        rows = s.query(PikPakFile).where(PikPakFile.job_id == job_id).all()
        assert all(r.status == "done" for r in rows)
    finally:
        s.close()
    # 目录结构保留
    assert (album_dir / "0.jpg").exists()


def test_download_files_partial_failure(clean, monkeypatch):
    """单文件失败不拖垮整批; files_done 仍计满(失败也是完成数)。"""
    import shutil
    shutil.rmtree(Path(settings.library_dir) / "_conc_test_album", ignore_errors=True)
    job_id, album_dir = _job(6)
    token = "tok-conc-2"
    pk_worker._run_tokens[job_id] = token

    calls = {"n": 0}
    lock = threading.Lock()

    def fake_download(url, dest, **kw):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if n == 3:   # 第 3 个下载的文件失败
            raise RuntimeError("boom")
        Path(dest).write_bytes(b"x" * 2048)
        if kw.get("on_progress"):
            kw["on_progress"](2048, 2048)

    from app.services.harvest import pipeline
    monkeypatch.setattr(pipeline, "download_stream", fake_download)

    s = SessionLocal()
    try:
        job = s.get(PikPakJob, job_id)
        files = s.query(PikPakFile).where(PikPakFile.job_id == job_id).all()
        pk_worker._download_files(s, job, files, album_dir, token)
    finally:
        pk_worker._run_tokens.pop(job_id, None)
        s.close()

    s = SessionLocal()
    try:
        rows = s.query(PikPakFile).where(PikPakFile.job_id == job_id).all()
        assert sum(1 for r in rows if r.status == "done") == 5
        failed = [r for r in rows if r.status == "failed"]
        assert len(failed) == 1 and "boom" in failed[0].error
        j = s.get(PikPakJob, job_id)
        assert j.files_done == 6
    finally:
        s.close()


def test_download_files_stops_on_token_revoke(clean, monkeypatch):
    """看门狗撤销 token 后, 未开始的文件不再启动下载。"""
    import shutil
    shutil.rmtree(Path(settings.library_dir) / "_conc_test_album", ignore_errors=True)
    job_id, album_dir = _job(40)
    token = "tok-conc-3"
    pk_worker._run_tokens[job_id] = token

    started = {"n": 0}
    lock = threading.Lock()

    def fake_download(url, dest, **kw):
        with lock:
            started["n"] += 1
        # 第一个下载把 token 撤走(模拟看门狗重置)
        pk_worker._run_tokens.pop(job_id, None)
        time.sleep(0.05)
        Path(dest).write_bytes(b"x")

    from app.services.harvest import pipeline
    monkeypatch.setattr(pipeline, "download_stream", fake_download)

    s = SessionLocal()
    try:
        job = s.get(PikPakJob, job_id)
        files = s.query(PikPakFile).where(PikPakFile.job_id == job_id).all()
        pk_worker._download_files(s, job, files, album_dir, token)
    finally:
        pk_worker._run_tokens.pop(job_id, None)
        s.close()

    # 4 个在途线程完成后, 队列里其余文件不再启动 — 远小于 40
    assert started["n"] < 10, f"token revoked but {started['n']} downloads started"


def test_close_job_streams_closes_all_concurrent_keys(monkeypatch):
    """close_job_streams 关掉 <job>:<file> 全部在途流 + 兼容裸 job_id key。"""
    from app.services.harvest import pipeline

    closed = []
    class FakeResp:
        def close(self): closed.append(self.key)

    def mk(key):
        r = FakeResp(); r.key = key; return r

    pipeline._STREAMS.clear()
    pipeline._STREAMS[7] = mk(7)                    # harvest 风格裸 key
    pipeline._STREAMS["7:a"] = mk("7:a")            # pikpak 并发流
    pipeline._STREAMS["7:b"] = mk("7:b")
    pipeline._STREAMS["8:a"] = mk("8:a")            # 别的任务, 不该被关

    n = pipeline.close_job_streams(7)
    assert n == 3
    assert sorted(map(repr, closed)) == sorted(map(repr, [7, "7:a", "7:b"]))
    assert "8:a" in pipeline._STREAMS
    pipeline._STREAMS.clear()
