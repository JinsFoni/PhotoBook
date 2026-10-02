"""短链落地到非 MediaFire 网盘 → 任务报「不支持××网盘下载」且重试无意义。"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db import HarvestHistory, HarvestJob
from app.database import SessionLocal
from app.services.harvest import net, worker


@pytest.fixture()
def s():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def _cleanup(serials: list[int]) -> None:
    ss = SessionLocal()
    try:
        for serial in serials:
            ss.execute(delete(HarvestHistory).where(HarvestHistory.serial == serial))
            ss.execute(delete(HarvestJob).where(HarvestJob.serial == serial))
        ss.commit()
    finally:
        ss.close()


def test_resolve_ouo_raises_on_known_host(monkeypatch):
    """落地 terabox → 抛 UnsupportedHostError(带平台名)。"""
    monkeypatch.setattr(net, "_ouo_step",
                        lambda s, url, **kw: "https://www.terabox.app/sharing/link?surl=abc")
    with pytest.raises(net.UnsupportedHostError) as ei:
        net.resolve_ouo("https://ouo.io/oHW468")
    assert ei.value.host == "TeraBox"
    assert "TeraBox" in str(ei.value)


def test_resolve_ouo_unknown_host_returns_none(monkeypatch):
    """完全未知的域 → 维持原行为返回 None(判短链坏)。"""
    monkeypatch.setattr(net, "_ouo_step",
                        lambda s, url, **kw: "https://some-random.example.com/x")
    assert net.resolve_ouo("https://ouo.io/oHW468") is None


def test_worker_records_unsupported_host(s, monkeypatch):
    """worker 捕获异常 → failed + 明确报错文案。"""
    monkeypatch.setattr(net, "resolve_ouo",
                        lambda link, **kw: (_ for _ in ()).throw(
                            net.UnsupportedHostError("TeraBox")))
    # 前置链路打桩: 详情页带短链即可
    from app.services.harvest import net as hnet
    html = ('<html><head><meta property="og:title" content="TeraBox Album"></head><body>'
            '<a href="https://ouo.io/AbCdEf">x</a></body></html>')
    monkeypatch.setattr(hnet, "fetch_html", lambda url, **kw: html)
    serial = 996001
    _cleanup([serial])
    job = worker.enqueue(s, serial, f"https://www.buondua.com/a-{serial}")
    s.commit()
    worker._run_job(job.id)
    s.expire_all()
    j = s.get(HarvestJob, job.id)
    try:
        assert j.status == "failed"
        assert j.error == "不支持TeraBox网盘下载"
    finally:
        _cleanup([serial])


def test_terabox_sibling_domains(monkeypatch):
    """TeraBox 姊妹域(1024tera/terasharelink 等)同样识别为 TeraBox。"""
    for url in ("https://www.1024tera.com/sharing/link?surl=abc",
                "https://terasharelink.com/s/abc",
                "https://teraboxapp.com/s/abc"):
        monkeypatch.setattr(net, "_ouo_step", lambda s, u, **kw: url)
        with pytest.raises(net.UnsupportedHostError) as ei:
            net.resolve_ouo("https://ouo.io/x")
        assert ei.value.host == "TeraBox", url
