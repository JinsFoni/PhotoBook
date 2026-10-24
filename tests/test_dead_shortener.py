"""整页只剩已停用的第三方短链(shink.me / adf.ly)→ 任务失败文案要说清原因。

2026-10-24 实录:misskon 2017 年的视频帖把下载按钮挂在 shink.me 上,该服务已
关站、域名进了停放页,页面上一条能用的下载源都没有。以前只报「详情页未找到
下载短链」,看起来像解析器没认出链接;实际是源站自己把链接放废了。
"""

from __future__ import annotations

from sqlalchemy import delete

from app.db import HarvestHistory, HarvestJob
from app.database import SessionLocal
from app.services.harvest import net, worker

SERIAL = 996002
URL = f"https://misskon.com/{SERIAL}-feilin-video-no-031-model-mu-yu-qian/"

HTML = f"""
<html><head><title>FEILIN Video No.031 – MissKon.com</title></head>
<body class="single single-post postid-{SERIAL}">
  <h1 class="name post-title entry-title">FEILIN Video No.031</h1>
  <div class="entry">
    <p style="text-align: center;">Download video<br />
      <a href="http://shink.me/wyxfh" target="_blank"><i class="fa fa-download"></i>Download link: Google Drive</a></p>
  </div>
  <p class="post-tag">Tags<a href="https://misskon.com/tag/feilin/" rel="tag">FEILIN</a></p>
</body></html>
"""


def _cleanup() -> None:
    ss = SessionLocal()
    try:
        ss.execute(delete(HarvestHistory).where(HarvestHistory.serial == SERIAL))
        ss.execute(delete(HarvestJob).where(HarvestJob.serial == SERIAL))
        ss.commit()
    finally:
        ss.close()


def test_worker_reports_dead_shortener(monkeypatch):
    """只有 shink.me 一类的死链 → failed + 「源站短链已停用(shink.me)」。"""
    monkeypatch.setattr(net, "fetch_html", lambda url, **kw: HTML)
    _cleanup()
    s = SessionLocal()
    try:
        job = worker.enqueue(s, SERIAL, URL)
        s.commit()
        worker._run_job(job.id)
        s.expire_all()
        j = s.get(HarvestJob, job.id)
        assert j is not None and j.status == "failed"
        assert j.error == "源站短链已停用(shink.me),没有可用的下载源"
    finally:
        s.close()
        _cleanup()


def test_worker_plain_message_without_dead_links(monkeypatch):
    """没有任何链接的普通页面 → 维持原文案,不要凭空说「短链已停用」。"""
    monkeypatch.setattr(net, "fetch_html",
                        lambda url, **kw: (f'<html><body class="postid-{SERIAL}">'
                                           '<p>no links here</p></body></html>'))
    _cleanup()
    s = SessionLocal()
    try:
        job = worker.enqueue(s, SERIAL, URL)
        s.commit()
        worker._run_job(job.id)
        s.expire_all()
        j = s.get(HarvestJob, job.id)
        assert j is not None and j.status == "failed"
        assert j.error == "详情页未找到下载短链"
    finally:
        s.close()
        _cleanup()
