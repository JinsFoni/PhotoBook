"""采集任务删除 — done 不碰文件;failed 清理归档库残留;运行中拒绝。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete

from app.db import HarvestHistory, HarvestJob
from app.database import SessionLocal
from app.services.harvest import worker


@pytest.fixture()
def s():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def _cleanup(serials: list[int]) -> None:
    s = SessionLocal()
    try:
        for serial in serials:
            s.execute(delete(HarvestHistory).where(HarvestHistory.serial == serial))
            s.execute(delete(HarvestJob).where(HarvestJob.serial == serial))
        s.commit()
    finally:
        s.close()


def _job(serial: int, status: str, archive_dir: str | None = None) -> HarvestJob:
    s = SessionLocal()
    try:
        j = HarvestJob(serial=serial, url=f"https://www.buondua.com/x-{serial}-photos-z",
                       status=status, archive_dir=archive_dir)
        s.add(j)
        s.commit()
        return j
    finally:
        s.close()


def test_delete_done_keeps_files(s, admin_client):
    """删除 done 任务:仅删记录,不碰 library/media 文件。"""
    _cleanup([993001])
    j = _job(993001, "done")
    try:
        r = admin_client.post(f"/admin/harvest/{j.id}/delete", follow_redirects=False)
        assert r.status_code == 303
        s.expire_all()
        from sqlalchemy import select
        assert s.get(HarvestJob, j.id) is None
    finally:
        _cleanup([993001])


def test_delete_failed_removes_residue(s, admin_client, tmp_path, monkeypatch):
    """删除 failed 任务:归档库残留目录一并删除。"""
    from app.config import settings

    _cleanup([993002])
    residue = Path(settings.library_dir) / "ResidueModel" / "residue-album"
    residue.mkdir(parents=True, exist_ok=True)
    (residue / "001.jpg").write_bytes(b"x")
    j = _job(993002, "failed", archive_dir=str(residue))
    try:
        r = admin_client.post(f"/admin/harvest/{j.id}/delete", follow_redirects=False)
        assert r.status_code == 303
        assert not residue.exists()
        s.expire_all()
        assert s.get(HarvestJob, j.id) is None
    finally:
        _cleanup([993002])
        import shutil
        shutil.rmtree(residue.parent, ignore_errors=True)


def test_delete_failed_outside_library_rejected(s, admin_client, tmp_path):
    """archive_dir 指向 library 之外 → 拒绝删目录,但任务记录仍删。"""
    _cleanup([993003])
    outside = tmp_path / "outside-album"
    outside.mkdir()
    (outside / "001.jpg").write_bytes(b"x")
    j = _job(993003, "failed", archive_dir=str(outside))
    try:
        r = admin_client.post(f"/admin/harvest/{j.id}/delete", follow_redirects=False)
        assert r.status_code == 303
        assert outside.exists()          # 库外文件不动
        s.expire_all()
        assert s.get(HarvestJob, j.id) is None  # 记录照删
    finally:
        _cleanup([993003])
        import shutil
        shutil.rmtree(outside, ignore_errors=True)


def test_delete_running_rejected(s, admin_client):
    """queued/downloading 等非终态不能删(应走取消)。"""
    _cleanup([993004, 993005])
    j1 = _job(993004, "queued")
    j2 = _job(993005, "downloading")
    try:
        for j in (j1, j2):
            r = admin_client.post(f"/admin/harvest/{j.id}/delete", follow_redirects=False)
            assert r.status_code == 303
            s.expire_all()
            assert s.get(HarvestJob, j.id) is not None  # 还在
    finally:
        _cleanup([993004, 993005])


def test_worker_records_residue_on_import_failure(s, monkeypatch):
    """import 失败 → job.archive_dir 记录归档目录。"""
    from app.config import settings

    _cleanup([993006])
    _stub_and_break_import(monkeypatch)
    job = worker.enqueue(s, 993006, "https://www.buondua.com/a-photos-993006")
    s.commit()
    worker._run_job(job.id)
    s.expire_all()
    j = s.get(HarvestJob, job.id)
    try:
        assert j.status == "failed"
        assert j.archive_dir and "ResidueModel" in j.archive_dir, f"err={j.error!r} status={j.status}"
        assert Path(j.archive_dir).is_dir()
    finally:
        import shutil
        if j.archive_dir:
            shutil.rmtree(j.archive_dir, ignore_errors=True)
        _cleanup([993006])


def _stub_and_break_import(monkeypatch) -> None:
    """网络链路打桩正常, import_album 打桩成抛异常(归档已完成)。"""
    from PIL import Image

    from app.services.harvest import net as hnet
    from app.services.harvest import pipeline as hpipe
    from app.services import library_import

    detail = ('<html><head><meta property="og:title" content="Residue Album"></head><body>'
              '<div class="article-tags"><div class="tags">'
              '<a href="/tag/residuemodel-1"><span>ResidueModel</span></a>'
              '</div></div><a href="https://ouo.io/AbCdEf">x</a></body></html>')
    monkeypatch.setattr(hnet, "fetch_html", lambda url, **kw: detail)
    monkeypatch.setattr(hnet, "resolve_ouo",
                        lambda link, **kw: "https://www.mediafire.com/file/abc/x.rar")
    monkeypatch.setattr(hnet, "mediafire_info_from_url",
                        lambda u: {"direct_url": "https://x/y.rar", "filename": "y.rar",
                                   "size": 3, "sha256": None})
    monkeypatch.setattr(hpipe, "download_stream",
                        lambda url, dest, **kw: Path(dest).write_bytes(b"rar"))
    def fake_extract(archive, out, password=None):
        out.mkdir(parents=True, exist_ok=True)
        for i in (1, 2):
            Image.new("RGB", (400, 300), (5, 5, 5)).save(out / f"{i:03d}.jpg")
        return out

    monkeypatch.setattr(hpipe, "extract_archive", fake_extract)

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(library_import, "import_album", boom)
