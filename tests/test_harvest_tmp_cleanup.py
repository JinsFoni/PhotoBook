"""_tmp 清理策略 — .part 保留续传; 完整包/work 目录按归属清理。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete

from app.config import settings
from app.db import HarvestHistory, HarvestJob
from app.database import SessionLocal
from app.services.harvest import worker

SERIALS = [995001]


@pytest.fixture()
def s():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def tmp_dir():
    d = Path(settings.library_dir) / "_tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cleanup():
    ss = SessionLocal()
    try:
        for serial in SERIALS:
            ss.execute(delete(HarvestHistory).where(HarvestHistory.serial == serial))
            ss.execute(delete(HarvestJob).where(HarvestJob.serial == serial))
        ss.commit()
    finally:
        ss.close()


def _stub_pipeline(monkeypatch, tmp_dir: Path, *, fail_download: bool):
    """网络链路打桩; download 可选择抛错模拟传输中断。"""
    from app.services.harvest import net as hnet
    from app.services.harvest import pipeline as hpipe

    detail = ('<html><head><meta property="og:title" content="Tmp Cleanup"></head><body>'
              '<div class="article-tags"><div class="tags">'
              '<a href="/tag/tmpclean-1"><span>TmpClean</span></a>'
              '</div></div><a href="https://ouo.io/AbCdEf">x</a></body></html>')
    monkeypatch.setattr(hnet, "fetch_html", lambda url, **kw: detail)
    monkeypatch.setattr(hnet, "resolve_ouo", lambda link, **kw: "https://x/y.rar")
    monkeypatch.setattr(hnet, "mediafire_info_from_url",
                        lambda u: {"direct_url": "https://x/y.rar", "filename": "y.rar",
                                   "size": 3, "sha256": None})

    def fake_download(url, dest, **kw):
        p = Path(dest)
        part = p.with_suffix(p.suffix + ".part")
        part.write_bytes(b"x" * 1024)  # 模拟断点文件
        if fail_download:
            raise RuntimeError("curl: (28) Operation too slow")
        p.write_bytes(b"rar")
        return p

    monkeypatch.setattr(hpipe, "download_stream", fake_download)


def test_failed_download_keeps_part(s, tmp_dir, monkeypatch):
    """下载中断 → 任务 failed, .part 保留(重试续传), 完整包/脏目录不残留。"""
    _cleanup()
    _stub_pipeline(monkeypatch, tmp_dir, fail_download=True)
    job = worker.enqueue(s, SERIALS[0], f"https://www.buondua.com/a-{SERIALS[0]}")
    s.commit()
    worker._run_job(job.id)
    s.expire_all()
    j = s.get(HarvestJob, job.id)
    assert j.status == "failed", j.error
    try:
        assert (tmp_dir / "y.rar.part").is_file(), "断点文件必须保留供重试续传"
        assert not (tmp_dir / "y.rar").exists()
    finally:
        _cleanup()


def test_success_deletes_archive_and_workdir_keeps_nothing_stale(s, tmp_dir, monkeypatch):
    """成功路径: 完整包删除、work 目录删除(旧全局 glob 行为不回归)。"""
    from PIL import Image

    from app.services.harvest import pipeline as hpipe
    from app.services import library_import

    _cleanup()
    _stub_pipeline(monkeypatch, tmp_dir, fail_download=False)
    # 解压/归档打桩(假包不是真压缩档); import 打桩成跳过, 避免真入库
    def fake_extract(archive, out, password=None):
        out.mkdir(parents=True, exist_ok=True)
        return [out]
    monkeypatch.setattr(hpipe, "extract_archive", fake_extract)
    monkeypatch.setattr(hpipe, "archive_collection",
                        lambda work, root, **kw: Path(work))
    monkeypatch.setattr(library_import, "import_album",
                        lambda *a, **kw: {"skipped": True, "photos": 0, "videos": 0,
                                          "slug": "", "broken": []})
    job = worker.enqueue(s, SERIALS[0], f"https://www.buondua.com/a-{SERIALS[0]}")
    s.commit()
    worker._run_job(job.id)
    s.expire_all()
    j = s.get(HarvestJob, job.id)
    assert j.status == "done", j.error
    try:
        assert not (tmp_dir / "y.rar").exists(), "完整包应删除"
        assert not (tmp_dir / f"work-{j.serial}").exists(), "work 目录应删除"
    finally:
        _cleanup()


def test_prune_tmp_only_touches_orphans(s, tmp_dir):
    """兜底清理: 老 work 目录清掉, 零字节 .part 清掉, 活跃任务的与有内容的 .part 不动。"""
    old_work = tmp_dir / "work-990001"
    old_work.mkdir(parents=True, exist_ok=True)
    import os
    two_weeks_ago = __import__("time").time() - 8 * 86400
    os.utime(old_work, (two_weeks_ago, two_weeks_ago))
    active_work = tmp_dir / "work-990002"
    active_work.mkdir(parents=True, exist_ok=True)

    stale_part = tmp_dir / "orphan.rar.part"
    stale_part.write_bytes(b"x" * 100)
    empty_part = tmp_dir / "empty.rar.part"
    empty_part.write_bytes(b"")
    ss = SessionLocal()
    try:
        ss.add(HarvestJob(serial=990002, url="https://x/990002", status="downloading"))
        ss.commit()
    finally:
        ss.close()
    try:
        worker._prune_tmp(tmp_dir)
        assert not old_work.exists(), "无主老 work 目录应清理"
        assert active_work.exists(), "活跃任务的 work 目录不动"
        assert stale_part.is_file(), "有内容的 .part 永远保留"
        assert not empty_part.exists(), "零字节 .part 兜底清理"
    finally:
        _cleanup()
        import shutil
        shutil.rmtree(old_work, ignore_errors=True)
        shutil.rmtree(active_work, ignore_errors=True)
        stale_part.unlink(missing_ok=True)
