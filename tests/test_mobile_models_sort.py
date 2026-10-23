"""`/api/mobile/models` 的排序 = 按**最新入库那本写真**的模特(与 web 一致)。

2026-10-24 修: 手机端列表原来按 `Model.created_at`(模特行建立时间)排 —— 那是
「这个模特什么时候第一次被收录」, 不是「他/她的写真什么时候最后入库」。web 端
`/models` 的「排序: 最新」已经改成最新入库写真序, 两端必须同一把尺子, 否则同一个人
在手机和浏览器的位置不一样。

同时 `latestAt` / `latestCid`(精确到微秒的排序键)对齐 web payload, 详情页作品网格
也改成最新入库序(`_published_collections` 自身是发布日期序)。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.database import SessionLocal
from app.db import Collection, Model, Photo

PREFIX = "zz-mm"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _drop()


def _mk_model(s, slug: str, name: str, *, created: datetime | None = None) -> Model:
    m = Model(slug=f"{PREFIX}-{slug}", name=name, status="published",
              created_at=created or datetime(2020, 1, 1))
    s.add(m)
    s.flush()
    return m


def _mk_collection(s, *, slug: str, model_id: int, created: datetime,
                   published: str | None = None, n_photos: int = 1) -> int:
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
    s = SessionLocal()
    try:
        for c in s.query(Collection).filter(Collection.slug.like(f"{PREFIX}-%")).all():
            s.delete(c)
        for m in s.query(Model).filter(Model.slug.like(f"{PREFIX}-%")).all():
            s.delete(m)
        s.commit()
    finally:
        s.close()


def _items(client, **params) -> list[dict]:
    r = client.get("/api/mobile/models", params=params or None)
    assert r.status_code == 200
    return r.json()["items"]


def _ours(items: list[dict]) -> list[dict]:
    return [m for m in items if m["slug"].startswith(PREFIX)]


def test_mobile_models_ordered_by_newest_ingested_work(client):
    """入库更晚的写真所属模特在前, 与模特行建立时间/model 名无关。"""
    s = SessionLocal()
    try:
        early = _mk_model(s, "early", "Aaa Mm Early", created=datetime(2026, 10, 1))
        late = _mk_model(s, "late", "Zzz Mm Late", created=datetime(2020, 1, 1))
        _mk_collection(s, slug="c-early", model_id=early.id,
                       created=datetime(2026, 10, 23, 10, 0), published="2026.10.23")
        _mk_collection(s, slug="c-late", model_id=late.id,
                       created=datetime(2026, 10, 23, 20, 0), published="2026.10.23")
        s.commit()
    finally:
        s.close()

    ours = _ours(_items(client))
    # 旧实现按 Model.created_at → Aaa Mm Early(10-01) 在前; 现在该是入库更晚的 Zzz
    assert [m["slug"] for m in ours] == [f"{PREFIX}-late", f"{PREFIX}-early"]
    assert ours[0]["latestAt"] == "2026-10-23T20:00:00"
    assert ours[0]["latestCid"] > 0


def test_mobile_models_oldest_reverses_within_dated_group(client):
    """sort=oldest 把有作品的模特整体翻过来, 无作品的仍垫底。"""
    s = SessionLocal()
    try:
        for i in range(3):
            m = _mk_model(s, f"s{i}", f"Mm {i}")
            _mk_collection(s, slug=f"cs{i}", model_id=m.id,
                           created=datetime(2026, 10, 22, 10, i * 7))
        _mk_model(s, "nowork", "Aaa Mm Nowork")      # 名字最靠前, 但没有作品
        s.commit()
    finally:
        s.close()

    latest = [m["slug"] for m in _ours(_items(client, sort="latest"))]
    oldest = [m["slug"] for m in _ours(_items(client, sort="oldest"))]
    assert latest == [f"{PREFIX}-s2", f"{PREFIX}-s1", f"{PREFIX}-s0",
                      f"{PREFIX}-nowork"]
    assert oldest == [f"{PREFIX}-s0", f"{PREFIX}-s1", f"{PREFIX}-s2",
                      f"{PREFIX}-nowork"]      # 无作品的两个方向都垫底


def test_mobile_models_featured_still_pinned(client):
    """精选置顶的老规矩不变: featured 段在有作品的模特前面。"""
    s = SessionLocal()
    try:
        plain = _mk_model(s, "plain", "Zzz Mm Plain")
        feat = _mk_model(s, "feat", "Aaa Mm Featured")
        feat.featured = True
        _mk_collection(s, slug="c-plain", model_id=plain.id,
                       created=datetime(2026, 10, 23, 23, 0))
        _mk_collection(s, slug="c-feat", model_id=feat.id,
                       created=datetime(2020, 1, 2))
        s.commit()
    finally:
        s.close()

    ours = _ours(_items(client))
    assert ours[0]["slug"] == f"{PREFIX}-feat"      # 入库更早, 但精选置顶
    assert [m["slug"] for m in ours[1:]] == [f"{PREFIX}-plain"]


def test_mobile_model_detail_works_are_publish_date_desc(client):
    """详情页作品网格: 源站发布日期新→旧(与 web 模特页同序), 不看入库时间。"""
    s = SessionLocal()
    try:
        m = _mk_model(s, "detail", "Mm Detail")
        first = _mk_collection(s, slug="d-old", model_id=m.id,
                              created=datetime(2026, 1, 1), published="2026.10.22")
        second = _mk_collection(s, slug="d-new", model_id=m.id,
                                created=datetime(2026, 10, 23, 12, 0),
                                published="2022.01.05")
        s.commit()
        slug = m.slug
    finally:
        s.close()

    detail = client.get(f"/api/mobile/models/{slug}").json()
    # 入库更晚但出版更早的 d-new 排在后面
    assert [c["slug"] for c in detail["collections"]][:2] == [
        f"{PREFIX}-d-old", f"{PREFIX}-d-new"]
    assert {f"{PREFIX}-d-new", f"{PREFIX}-d-old"} == {
        c["slug"] for c in detail["collections"]}
    assert second > first
