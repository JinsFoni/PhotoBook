"""`/models` 的「排序: 最新」= 按**最新入库那本写真**的模特往前排。

2026-10-24 修: 后端只给到「天」(`latest` 是日期字符串), 而一次采集会灌进
几十个模特 —— 生产上单日并列 46-48 个, 组内谁前谁后完全由 SQL 的 name 序
决定。实测「最新」榜单前 10 名变成字母序 (Ai Hongo / Airi Kijima / Fūka
Hanasaki …), 与真正的最新入库序重合仅 2 条。

现在 payload 带上精确时间 `latestAt`(created_at 原值) + 兜底 `latestCid`,
前端按 `latestAt desc, latestCid desc, name asc` 排 —— 与全站
`created_at desc, id desc` 同一把尺子。
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime

import pytest

from app.database import SessionLocal
from app.db import Collection, Model, Photo
from app.routers.web import _model_payload

PREFIX = "zz-msort"
TEMPLATE = pathlib.Path(__file__).resolve().parents[1] / "app/templates/models.html"


@pytest.fixture(autouse=True)
def _cleanup():
    """DB 是会话级共享的, 每个用例收尾都要把自建的行删干净。"""
    yield
    _drop()


def _pb_data(html: str) -> dict:
    m = re.search(r"window\.PB_DATA = (.*?);\nwindow\.PB_BOOT", html, re.S)
    assert m, "PB_DATA missing"
    return json.loads(m.group(1))


def _mk_model(s, slug: str, name: str) -> Model:
    m = Model(slug=f"{PREFIX}-{slug}", name=name, status="published")
    s.add(m)
    s.flush()
    return m


def _mk_collection(s, *, slug: str, model_id: int, created: datetime,
                   published: str | None, n_photos: int = 1) -> int:
    c = Collection(slug=f"{PREFIX}-{slug}", title=slug, model_id=model_id,
                   status="published", created_at=created, published_at=published)
    s.add(c)
    s.flush()
    for i in range(n_photos):
        s.add(Photo(collection_id=c.id, filename=f"{slug}/{i:03d}.jpg",
                    width=10, height=10, sort_order=i))
    s.flush()
    return c.id


def _drop() -> None:
    """DB 是会话级共享的, 自建的模特/合集必须当场清干净。"""
    s = SessionLocal()
    try:
        for c in s.query(Collection).filter(
                Collection.slug.like(f"{PREFIX}-%")).all():
            s.delete(c)                      # cascade 带走 photos
        for m in s.query(Model).filter(Model.slug.like(f"{PREFIX}-%")).all():
            s.delete(m)
        s.commit()
    finally:
        s.close()


def _js_order(models: list[dict]) -> list[dict]:
    """复刻前端 filtered() 的 latest 分支: 稳定排序 + name 升序兜底。"""
    by_name = sorted(models, key=lambda m: m["name"])
    return sorted(by_name,
                  key=lambda m: (m.get("latestAt") or "", m.get("latestCid") or 0),
                  reverse=True)


def test_payload_latest_at_is_ingest_time_not_publish_date():
    """最新那本按**入库时间**选, 不是源站发布日期。"""
    s = SessionLocal()
    try:
        m = _mk_model(s, "m1", "Msort One")
        _mk_collection(s, slug="c1", model_id=m.id, created=datetime(2026, 3, 1, 9, 0),
                       published="2026.10.22")          # 源站日期最新, 但早就入库了
        new_cid = _mk_collection(s, slug="c2", model_id=m.id,
                                 created=datetime(2026, 10, 23, 18, 25, 38, 394889),
                                 published="2022.01.05")  # 今天才入库的老作品
        s.commit()
        payload = _model_payload(s, m, [c for c in m.collections
                                       if c.status == "published"])
    finally:
        s.close()
    assert payload["latestCid"] == new_cid
    assert payload["latestAt"] == "2026-10-23T18:25:38.394889"
    assert payload["latest"] == "2026-10-23"             # 展示/手机端仍用日期


def test_latest_at_keeps_sub_day_precision():
    """同一天入库的两本, 时间不同 → latestAt 必须不同(旧实现只到「天」)。"""
    s = SessionLocal()
    try:
        m = _mk_model(s, "m2", "Msort Two")
        _mk_collection(s, slug="c3", model_id=m.id, created=datetime(2026, 10, 23, 6, 0),
                       published="2026.10.20")
        late = _mk_collection(s, slug="c4", model_id=m.id,
                              created=datetime(2026, 10, 23, 19, 30), published=None)
        s.commit()
        payload = _model_payload(s, m, [c for c in m.collections
                                       if c.status == "published"])
    finally:
        s.close()
    assert payload["latestAt"] == "2026-10-23T19:30:00"
    assert payload["latestCid"] == late
    assert payload["latest"] == "2026-10-23"             # 日期相同, 差异只在时间


def test_latest_cid_breaks_same_instant_tie():
    """极端情况: 同一微秒入库两本 → 按合集 id 大者在前(与全站 id desc 一致)。"""
    s = SessionLocal()
    try:
        m = _mk_model(s, "m3", "Msort Three")
        first = _mk_collection(s, slug="c5", model_id=m.id,
                               created=datetime(2026, 10, 22, 8, 0), published=None)
        second = _mk_collection(s, slug="c6", model_id=m.id,
                                created=datetime(2026, 10, 22, 8, 0), published=None)
        s.commit()
        assert second > first
        payload = _model_payload(s, m, [c for c in m.collections
                                       if c.status == "published"])
    finally:
        s.close()
    assert payload["latestCid"] == second


def test_models_page_orders_by_newest_ingested_works(admin_client):
    """页面 payload 的排列: 最新入库写真所在模特在前, 没有作品的排最后。"""
    s = SessionLocal()
    try:
        early = _mk_model(s, "m-early", "Aaa Msort Early")
        late = _mk_model(s, "m-late", "Zzz Msort Late")     # 名字靠后, 但入库更晚
        _mk_collection(s, slug="c7", model_id=early.id,
                       created=datetime(2026, 10, 23, 10, 0), published="2026.10.23")
        _mk_collection(s, slug="c8", model_id=late.id,
                       created=datetime(2026, 10, 23, 20, 0), published="2026.10.23")
        _mk_model(s, "m-nowork", "Mmm Msort Nowork")
        s.commit()
    finally:
        s.close()

    data = _pb_data(admin_client.get("/models").text)
    ours = [m for m in data["models"] if m["slug"].startswith(PREFIX)]
    ordered = [m["slug"] for m in _js_order(ours)]

    # 精确到时间 → 入库更晚的 Zzz 在前; 只比「天」的话这里会是 Aaa 在前
    assert ordered == [f"{PREFIX}-m-late", f"{PREFIX}-m-early", f"{PREFIX}-m-nowork"]
    assert _js_order(ours)[-1]["latestAt"] == ""


def test_models_page_same_day_models_do_not_fall_back_to_alphabetical(admin_client):
    """单日并列必须按入库先后分开 —— 旧实现整批退回字母序(生产实测 46-48 个)。"""
    names = ["Aaa Msort B1", "Mmm Msort B2", "Zzz Msort B3"]
    s = SessionLocal()
    try:
        for i, nm in enumerate(names):
            m = _mk_model(s, f"b{i}", nm)
            _mk_collection(s, slug=f"cb{i}", model_id=m.id,
                           created=datetime(2026, 10, 21, 10, i * 5),
                           published="2026.10.21")
        s.commit()
    finally:
        s.close()

    data = _pb_data(admin_client.get("/models").text)
    ours = [m for m in data["models"] if m["slug"].startswith(f"{PREFIX}-b")]
    day_only = sorted(ours, key=lambda m: m["name"])       # 旧实现: 同日 → name 序
    assert [m["name"] for m in day_only] == names
    assert [m["name"] for m in _js_order(ours)] == list(reversed(names))


def test_template_sorts_latest_by_latest_at():
    """前端 latest 分支必须用 latestAt(精确时间), 不能只用日期。"""
    src = TEMPLATE.read_text()
    start = src.index('f.sort === "latest"')
    branch = src[start:start + 400]
    assert "latestAt" in branch
    assert "latestCid" in branch


def test_model_detail_page_orders_works_by_publish_date(admin_client):
    """模特详情页作品网格 = 源站发布日期新→旧(作品目录按发行时间线看)。

    特意让「入库晚」和「出版晚」分属两本 —— 谁排第一能直接看出用的是哪把尺子。
    """
    s = SessionLocal()
    try:
        m = _mk_model(s, "m-detail", "Msort Detail")
        _mk_collection(s, slug="d-old-pub", model_id=m.id,
                       created=datetime(2026, 10, 23, 23, 0), published="2022.01.05")
        _mk_collection(s, slug="d-new-pub", model_id=m.id,
                       created=datetime(2026, 1, 1), published="2026.10.22")
        _mk_collection(s, slug="d-undated", model_id=m.id,
                       created=datetime(2026, 10, 24, 9, 0), published=None)
        s.commit()
        slug = m.slug
    finally:
        s.close()

    data = _pb_data(admin_client.get(f"/models/{slug}").text)
    assert [c["slug"].removeprefix(f"{PREFIX}-") for c in data["works"]] == [
        "d-new-pub", "d-old-pub", "d-undated"]
