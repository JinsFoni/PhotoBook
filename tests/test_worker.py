"""worker 队列 — 入队去重(历史 + 排队中)、任务执行(打桩网络/下载/解压)。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.db import (Collection, HarvestHistory, HarvestJob, Model, Photo,
                    VideoAlbum)
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


def _stub_pipeline(monkeypatch, calls: list, videos: int = 0):
    """打桩网络/下载/解压:解压产物 = 两张图片(+可选 N 个 mp4)。

    videos > 0 用来验证采集链路的图文分流:视频应建 video_albums、
    移入 video/,任务提示不再说「跳过视频」。
    """
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
        for i in range(videos):
            (out / f"clip{i}.mp4").write_bytes(b"v")
        return out

    monkeypatch.setattr(hpipe, "download_stream", fake_download)
    monkeypatch.setattr(hpipe, "extract_archive", fake_extract)


def _cleanup(serials: list[int], slug: str | None = None, model: str | None = None,
             video_slug: str | None = None):
    """测试数据不入共享库:删任务/历史/写真/视频专辑/模特 + 文件。"""
    import shutil

    from app.config import settings
    from app.services.library_import import slugify

    s = SessionLocal()
    try:
        if slug:
            c = s.scalar(select(Collection).where(Collection.slug == slug))
            if c:
                s.delete(c)
        if video_slug:
            va = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == video_slug))
            if va:
                s.delete(va)
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
        for root in (settings.media_dir, settings.video_dir, settings.library_dir):
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
    assert "2 张已入库" in job.error and "缩略图生成中" in job.error
    assert calls == ["download", "extract"]

    c = s.scalar(select(Collection).where(Collection.slug == SLUG))
    # 缩略图生成完才 published; 测试里后台线程可能未跑完, 直接驱动发布翻转
    assert c is not None
    from app.services import media as media_svc
    media_svc._publish_ready(SLUG)
    s.expire_all()
    c = s.scalar(select(Collection).where(Collection.slug == SLUG))
    assert c.status == "published"
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


VSLUG = "workermodel-worker-import-album"


def test_run_job_imports_videos_alongside_photos(monkeypatch, s):
    """图文混合目录(采集链路):视频必须走独立模块,不能只说「跳过 N 个视频」。

    这条链路曾断过:worker 只调 import_album,视频永远留在 library 里,
    video_albums 一条不建(任务 111 就是这样留下的 4 个 mp4)。
    目录名/标题沿用 DETAIL 的 og:title,与写真用例同一个 slug,互不干扰。
    """
    from app.config import settings
    from app.services import video as video_svc

    calls: list = []
    _stub_pipeline(monkeypatch, calls, videos=2)
    # 抽帧/probe 打桩:假 mp4 解不出真帧,不可让真实 ffmpeg 决定 poster
    monkeypatch.setattr(video_svc, "ffmpeg_available", lambda: False)

    job = worker.enqueue(s, 980004, f"https://www.buondua.com/worker-import-album-{'0' * 32}-980004")
    s.commit()
    worker._run_job(job.id)
    s.expire_all()

    job = s.get(HarvestJob, job.id)
    assert job.status == "done"
    # 提示文案要说清视频真的入库了,而不是「跳过 2 个视频」
    assert "2 段视频入库" in job.error
    assert "跳过" not in job.error
    assert job.collection_slug == VSLUG

    c = s.scalar(select(Collection).where(Collection.slug == VSLUG))
    assert c is not None and len(c.photos) == 2
    # 视频侧:专辑 + 2 条记录,文件已移入 video/,library 侧不留
    va = s.scalar(select(VideoAlbum).where(VideoAlbum.slug == VSLUG))
    assert va is not None and len(va.videos) == 2
    assert va.videos[0].filename.startswith("workermodel/worker-import-album/")
    assert (Path(settings.video_dir) / "workermodel" / "worker-import-album").is_dir()
    assert not (Path(settings.library_dir) / "WorkerModel" / "Worker Import Album").exists()
    # 采集 tag 同时挂到视频专辑上(与写真各一条线)
    assert [t.name for t in va.tags] == ["Cosplay", "WorkerModel"]

    _cleanup([980004], slug=VSLUG, model="WorkerModel", video_slug=VSLUG)


def test_cancel_running_job_interrupts_download(monkeypatch, s):
    """取消运行中任务:置 cancelled 终态 + close 下载流 + 撤销所有权。

    三个必须同时做到,少一个都会留下「取消不掉」或「取消后还乱写」的坑:
    - 不写 HarvestHistory → serial 之后还能重新入队续传(.part 保留)
    - 不 close 流 → 线程阻塞在网络读上,下载继续跑
    - 不撤 token → 线程复苏后把 cancelled 覆盖成 failed
    """
    from app.services.harvest import pipeline as hpipe

    calls: list = []
    monkeypatch.setattr(hpipe, "close_stream",
                        lambda key: calls.append(("close", key)) or True)

    # 造一个「运行中」任务:不走完整 _run_job,直接把状态改成 downloading
    job = worker.enqueue(s, 980005, f"https://www.buondua.com/cancel-me-{'0' * 32}-980005")
    s.commit()
    job_id = job.id
    job.status = "downloading"
    s.commit()

    ok, msg = worker.cancel_job(job_id)
    assert ok, msg
    assert "取消" in msg

    s.expire_all()
    job = s.get(HarvestJob, job_id)
    assert job.status == "cancelled"
    # 终态已落,future watchdog 不再当它是活动任务
    assert job.status not in worker.ACTIVE_JOB_STATES
    # 下载流被 close + 运行所有权被撤销(线程复苏后不得覆盖终态)
    assert calls == [("close", job_id)]
    assert job_id not in worker._run_tokens
    # 不写历史表 → 同一 serial 仍可重新入队(续传)
    assert s.get(HarvestHistory, 980005) is None

    # 幂等:再取消一次直接拒绝,不改状态
    ok2, msg2 = worker.cancel_job(job_id)
    assert not ok2 and "无需取消" in msg2

    _cleanup([980005])


def test_cancel_queued_job_deletes_record(monkeypatch, s):
    """排队中的任务:直接删记录(还没跑,无产物)。"""
    job = worker.enqueue(s, 980006, f"https://www.buondua.com/cancel-queued-{'0' * 32}-980006")
    s.commit()
    job_id = job.id

    ok, msg = worker.cancel_job(job_id)
    assert ok, msg
    s.expire_all()
    assert s.get(HarvestJob, job_id) is None
    assert s.get(HarvestHistory, 980006) is None

    _cleanup([980006])


def test_cancelled_job_serial_can_reenqueue(s):
    """取消不毒化 serial:重新入队能成功(contrast failed/done 会写 HarvestHistory)。

    全程用独立会话(与生产一致:API 请求会话 ≠ worker 会话),SQLite 写锁
    才不会互相卡住 —— 复用 fixture 会话会在 cancel_job 内部写时锁库。
    """
    from app.database import SessionLocal

    s1 = SessionLocal()
    job = worker.enqueue(s1, 980007,
                         f"https://www.buondua.com/reenqueue-after-cancel-{'0' * 32}-980007")
    s1.commit()
    job_id = job.id
    job.status = "downloading"
    s1.commit()
    s1.close()  # 先放开写锁:cancel_job 自己开会话写

    ok, _msg = worker.cancel_job(job_id)
    assert ok

    s2 = SessionLocal()
    try:
        assert s2.get(HarvestHistory, 980007) is None
        again = worker.enqueue(s2, 980007,
                               f"https://www.buondua.com/reenqueue-after-cancel-{'0' * 32}-980007")
        s2.commit()
        assert again is not None, "cancelled 之后 serial 必须还能入队"
        assert again.status == "queued"
    finally:
        s2.rollback()
        s2.close()

    _cleanup([980007])
