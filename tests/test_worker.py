"""worker 队列 — 入队去重(历史 + 排队中)、任务执行(打桩网络/下载/解压)。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.db import Collection, HarvestHistory, HarvestJob, Model, Photo
from app.database import SessionLocal
from app.services.harvest import worker


@pytest.fixture()
def s():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


DETAIL = ('<html><head><meta property="og:title" content="Worker Import Album"></head><body>'
          '<div class="article-tags"><div class="tags">'
          '<a href="/tag/cosplay-10688"><span>Cosplay</span></a>'
          '<a href="/tag/workermodel-1"><span>WorkerModel</span></a>'
          '</div></div><a href="https://ouo.io/AbCdEf">x</a></body></html>')


def _stub_pipeline(monkeypatch, calls: list):
    """打桩网络/下载/解压:解压产物 = 两张图片。"""
    from PIL import Image

    from app.services.harvest import net as hnet
    from app.services.harvest import pipeline as hpipe

    monkeypatch.setattr(hnet, "fetch_html", lambda url, **kw: DETAIL)
    monkeypatch.setattr(hnet, "resolve_ouo",
                        lambda link, **kw: "https://www.mediafire.com/file/abc/x.rar")
    monkeypatch.setattr(hnet, "mediafire_info_from_url",
                        lambda u: {"direct_url": "https://x/y.rar", "filename": "y.rar",
                                   "size": 3, "sha256": None})

    def fake_download(url, dest, **kw):
        calls.append("download")
        Path(dest).write_bytes(b"rar")

    def fake_extract(archive, out, password=None):
        calls.append("extract")
        out.mkdir(parents=True, exist_ok=True)
        for i in (1, 2):
            Image.new("RGB", (400, 300), (5, 5, 5)).save(out / f"{i:03d}.jpg")
        return out

    monkeypatch.setattr(hpipe, "download_stream", fake_download)
    monkeypatch.setattr(hpipe, "extract_archive", fake_extract)


def _cleanup(serials: list[int], slug: str | None = None, model: str | None = None):
    """测试数据不入共享库:删任务/历史/写真/模特 + 文件。"""
    import shutil

    from app.config import settings
    from app.services.library_import import slugify

    s = SessionLocal()
    try:
        if slug:
            c = s.scalar(select(Collection).where(Collection.slug == slug))
            if c:
                s.delete(c)
        if model:
            m = s.scalar(select(Model).where(Model.name == model))
            if m:
                s.delete(m)
        for serial in serials:
            s.execute(delete(HarvestHistory).where(HarvestHistory.serial == serial))
            s.execute(delete(HarvestJob).where(HarvestJob.serial == serial))
        s.commit()
    finally:
        s.close()
    if slug:
        for root in (settings.media_dir, settings.library_dir):
            shutil.rmtree(Path(root) / slugify(model or ""), ignore_errors=True)


def test_enqueue_new(s):
    job = worker.enqueue(s, 990001, "https://www.buondua.com/a-990001-photos-x")
    assert job is not None and job.status == "queued"


def test_enqueue_history_dedup(s):
    s.add(HarvestHistory(serial=990002, status="done", title="t"))
    s.flush()
    assert worker.enqueue(s, 990002, "https://www.buondua.com/a-990002-photos-x") is None


def test_enqueue_inflight_dedup(s):
    worker.enqueue(s, 990003, "https://www.buondua.com/a-990003-photos-x")
    s.flush()
    assert worker.enqueue(s, 990003, "https://www.buondua.com/a-990003-photos-x") is None


def test_enqueue_manual_rejects_non_buondua():
    ok, msg = worker.enqueue_manual("https://example.com/x-123-photos-y")
    assert not ok and "buondua" in msg


def test_enqueue_manual_rejects_missing_serial():
    ok, _ = worker.enqueue_manual("https://www.buondua.com/just-a-page")
    assert not ok


def test_enqueue_manual_accepts_real_url(s):
    # 真实格式:<slug>-<hash>-<serial>
    ok, msg = worker.enqueue_manual(
        "https://www.buondua.com/yeha-yeha-school-nurse-219-photos-6746d2e27adfd5224746c047dfc7b9fe-56616")
    assert ok, msg


# ---- 任务执行(打桩网络/下载/解压) ------------------------------------------

SERIALS = [980001, 980002, 980003]
SLUG = "workermodel-worker-import-album"


def test_run_job_filters_by_tag(monkeypatch, s):
    """黑名单命中**标签**(标题里没有)→ 跳过不下载。"""
    from app.services import settings_store

    calls: list = []
    _stub_pipeline(monkeypatch, calls)
    old = settings_store.get_setting(s, "harvest.blacklist")
    settings_store.set_setting(s, "harvest.blacklist", "cosplay")
    s.commit()
    try:
        job = worker.enqueue(s, SERIALS[2], f"https://www.buondua.com/worker-import-album-{'0' * 32}-980003")
        s.commit()
        job_id = job.id
        worker._run_job(job_id)
        s.expire_all()
        job = s.get(HarvestJob, job_id)
        assert job.status == "skipped"
        assert "cosplay" in job.error
        assert calls == []  # 没有触发下载/解压
    finally:
        settings_store.set_setting(s, "harvest.blacklist", old or "")
        s.commit()
        _cleanup([SERIALS[2]])


def test_run_job_archives_and_imports(monkeypatch, s):
    """全链路:标签→模特名 → 归档 → 自动导入平台(建库 + 移动文件)。"""
    from app.config import settings

    calls: list = []
    _stub_pipeline(monkeypatch, calls)
    job = worker.enqueue(s, SERIALS[0], f"https://www.buondua.com/worker-import-album-{'0' * 32}-980001")
    s.commit()
    job_id = job.id
    worker._run_job(job_id)
    s.expire_all()

    job = s.get(HarvestJob, job_id)
    assert job.status == "done"
    assert job.model_name == "WorkerModel"        # 出品方 tag 被排除词跳过
    assert "2 张已入库" in job.error
    assert calls == ["download", "extract"]

    c = s.scalar(select(Collection).where(Collection.slug == SLUG))
    assert c is not None and c.status == "published"
    assert c.model is not None and c.model.name == "WorkerModel"
    assert len(c.photos) == 2
    assert (Path(settings.media_dir) / "workermodel" / "worker-import-album" / "001.jpg").exists()
    # 归档库已腾空
    assert not (Path(settings.library_dir) / "WorkerModel" / "Worker Import Album").exists()

    # 重试同名写真(新序号)→ 已存在预检命中,不再白下 1GB
    calls.clear()
    job2 = worker.enqueue(s, SERIALS[1], f"https://www.buondua.com/worker-import-album-{'0' * 32}-980002")
    s.commit()
    worker._run_job(job2.id)
    s.expire_all()
    assert s.get(HarvestJob, job2.id).status == "exists"
    assert calls == []

    _cleanup(SERIALS[:2], slug=SLUG, model="WorkerModel")
